"""Coordinateur de données — My Garden Irrigation.

Responsabilité unique : récupérer l'ETo via Open-Meteo et retourner
IrrigationData. L'état mutable (config, bilan hydrique) vit dans
RuntimeConfigState. La persistance est déléguée à PersistenceManager.
ValveTracker et IrrigationScheduler reçoivent des callbacks — ils ne
connaissent pas ce coordinateur.

ADR-008 : bilan hydrique cumulé.
ADR-009 : vanne globale — géré par ValveTracker.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .config_state import RuntimeConfigState
from .const import (
    CONF_DENSITY,
    CONF_NB_PLANTS,
    DOMAIN,
    OPEN_METEO_TIMEOUT,
    OPEN_METEO_URL,
    WATERING_MODE_FRACTIONED,
)

_SURFACE_FIELDS = frozenset({CONF_NB_PLANTS, CONF_DENSITY})
from .core.calculations import compute_irrigation_data
from .core.kc_data import get_kc
from .core.models import IrrigationData
from .kc_loader import async_load_kc_data
from .persistence import PersistenceManager

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(hours=1)


class IrrigationCoordinator(DataUpdateCoordinator[IrrigationData]):
    """Orchestre la récupération météo, le calcul et les sous-modules.

    Seul point d'entrée HA pour les entités. Délègue l'état à self.config
    (RuntimeConfigState) et la persistance à self._persistence
    (PersistenceManager).
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self._entry = entry
        self.config = RuntimeConfigState.from_entry(entry)
        self._persistence = PersistenceManager(hass, entry.entry_id)
        self._kc_data: dict = {}
        self._scheduler: Any = None
        self._last_daily_needs: dict[str, float] = {}
        self._save_unsub: Any = None

    # ------------------------------------------------------------------
    # Cycle de vie
    # ------------------------------------------------------------------

    async def async_setup(self) -> None:
        """Charge Kc, restaure l'état persisté, initialise les sous-modules."""
        from .scheduler import IrrigationScheduler
        from .valve_tracker import ValveTracker

        self._kc_data = await async_load_kc_data(self.hass)

        stored = await self._persistence.async_load()
        self.config.restore_from_storage(stored, dt_util.now().date().isoformat())
        self.config.cleanup_stale_crops()

        if self.config.auto_irrigation_enabled and self.config.last_auto_watering_date is None:
            self.config.set_auto_irrigation(True, dt_util.now().date().isoformat())

        tracker = ValveTracker(self.hass, self.config, self._on_volumes_applied)
        scheduler = IrrigationScheduler(
            self.hass, self.config, self._on_midnight, self._on_trigger
        )
        self._scheduler = scheduler

        self._entry.async_on_unload(tracker.setup())
        self._entry.async_on_unload(scheduler.setup())

        @callback
        def _cancel_pending_save() -> None:
            if self._save_unsub is not None:
                self._save_unsub()
                self._save_unsub = None

        self._entry.async_on_unload(_cancel_pending_save)

        await self.async_config_entry_first_refresh()

        if not self.config.cumulative_need and self.data is not None:
            self.config.init_cumulative_need(
                {cid: r.daily_need_liters for cid, r in self.data.crops.items()}
            )
            await self._persistence.async_save(
                self.config.to_storage(dt_util.now().date().isoformat())
            )
            await self.async_refresh()

    # ------------------------------------------------------------------
    # Callbacks internes (appelés par ValveTracker et IrrigationScheduler)
    # ------------------------------------------------------------------

    async def _on_volumes_applied(self, volumes: dict[str, float]) -> None:
        self.config.apply_watering_volumes(volumes)
        await self._persistence.async_save(
            self.config.to_storage(dt_util.now().date().isoformat())
        )
        await self.async_refresh()

    async def _on_midnight(self) -> None:
        if self.data is not None:
            daily_needs = {
                cid: r.daily_need_liters for cid, r in self.data.crops.items()
            }
        elif self._last_daily_needs:
            _LOGGER.warning(
                "Données météo indisponibles au transfert de minuit — "
                "utilisation du dernier besoin journalier connu."
            )
            daily_needs = self._last_daily_needs
        else:
            _LOGGER.warning("Aucune donnée météo disponible pour le transfert de minuit.")
            daily_needs = {}
        self.config.apply_midnight_transfer(daily_needs)
        await self._persistence.async_save(
            self.config.to_storage(dt_util.now().date().isoformat())
        )
        await self.async_refresh()

    async def _on_trigger(self, date_iso: str) -> None:
        self.fire_irrigation_event()
        await self.update_last_watering_date(date_iso)

    # ------------------------------------------------------------------
    # API publique — appelée par les entités HA
    # Thin delegates vers self.config + persistance + refresh si besoin.
    # ------------------------------------------------------------------

    def update_crop_field(self, crop_id: str, field: str, value: object) -> None:
        """Mise à jour silencieuse — réservée à async_added_to_hass (restauration boot)."""
        self.config.update_crop_field(crop_id, field, value)
        self._schedule_config_save()

    async def async_update_crop_field(
        self, crop_id: str, field: str, value: object
    ) -> None:
        """Action utilisateur : met à jour un champ, rescale le cumulatif, rafraîchit."""
        if field in _SURFACE_FIELDS and crop_id in self.config.cumulative_need:
            old_surface = self.config.get_crop_surfaces().get(crop_id, 0.0)
            self.config.update_crop_field(crop_id, field, value)
            new_surface = self.config.get_crop_surfaces().get(crop_id, 0.0)
            if old_surface > 0 and new_surface > 0:
                scale = new_surface / old_surface
                self.config._cumulative_need[crop_id] = round(
                    self.config.cumulative_need[crop_id] * scale, 3
                )
        else:
            self.config.update_crop_field(crop_id, field, value)
        await self._persistence.async_save(
            self.config.to_storage(dt_util.now().date().isoformat())
        )
        await self.async_refresh()

    def set_flow_rate(self, value: float) -> None:
        self.config.set_flow_rate(value)
        self._schedule_config_save()

    def set_watering_interval_days(self, value: int) -> None:
        self.config.set_watering_interval_days(value)
        self._schedule_config_save()

    def set_watering_frequency(self, value: str) -> None:
        self.config.set_watering_frequency(value)
        self._schedule_config_save()

    def set_watering_mode(self, value: str) -> None:
        self.config.set_watering_mode(value)
        self._schedule_config_save()

    def set_irrigation_time(self, value: str) -> None:
        self.config.set_irrigation_time(value)
        if self._scheduler is not None:
            self._scheduler.reschedule_auto_irrigation()
        self._schedule_config_save()

    def set_cycles_count(self, value: int) -> None:
        self.config.set_cycles_count(value)
        self._schedule_config_save()

    def set_soak_duration_minutes(self, value: int) -> None:
        self.config.set_soak_duration_minutes(value)
        self._schedule_config_save()

    async def async_set_auto_irrigation(self, enabled: bool) -> None:
        self.config.set_auto_irrigation(enabled, dt_util.now().date().isoformat())
        await self._persistence.async_save(
            self.config.to_storage(dt_util.now().date().isoformat())
        )
        if self._scheduler is not None:
            self._scheduler.reschedule_auto_irrigation()
        await self.async_refresh()

    async def async_reset_irrigation(self) -> None:
        self.config.reset_irrigation()
        await self._persistence.async_save(
            self.config.to_storage(dt_util.now().date().isoformat())
        )
        await self.async_refresh()

    async def update_last_watering_date(self, date_iso: str) -> None:
        self.config.update_last_watering_date(date_iso)
        await self._persistence.async_save(
            self.config.to_storage(dt_util.now().date().isoformat())
        )

    def fire_irrigation_event(self) -> None:
        """Émet l'événement HA que le blueprint d'automatisation écoute."""
        data = self.data
        if data is None:
            _LOGGER.warning(
                "Arrosage impossible : les données météo ne sont pas encore disponibles. "
                "Attendez le premier cycle de mise à jour (toutes les heures) avant de déclencher l'arrosage."
            )
            return

        total_cumulative = sum(data.cumulative_need.values())
        if total_cumulative <= 0:
            _LOGGER.debug("Arrosage auto : besoin cumulé = 0 L — événement non émis.")
            return

        flow_rate = self.config.flow_rate
        if flow_rate <= 0:
            _LOGGER.warning(
                "Arrosage auto : débit non configuré (%.1f L/h) — événement non émis.",
                flow_rate,
            )
            return

        duration_minutes = round((total_cumulative / flow_rate) * 60, 1)
        is_fractioned = self.config.watering_mode == WATERING_MODE_FRACTIONED

        payload: dict[str, Any] = {
            "entry_id": self._entry.entry_id,
            "valve_entity_id": self.config.valve_entity_id,
            "total_volume_liters": round(total_cumulative, 1),
            "recommended_duration_minutes": duration_minutes,
            "is_fractioned": is_fractioned,
        }
        if is_fractioned:
            cycles = max(1, self.config.cycles_count)
            payload["cycles_count"] = cycles
            payload["duration_per_cycle_minutes"] = round(duration_minutes / cycles, 1)
            payload["soak_duration_minutes"] = self.config.soak_duration_minutes

        self.hass.bus.async_fire(f"{DOMAIN}_irrigation_requested", payload)
        _LOGGER.info(
            "Événement %s_irrigation_requested émis — durée=%.1f min, mode=%s.",
            DOMAIN,
            duration_minutes,
            self.config.watering_mode,
        )

    # ------------------------------------------------------------------
    # Calcul principal
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> IrrigationData:
        """Récupère ETo et précipitations puis calcule les besoins nets."""
        eto_mm, precipitation_mm = await self._fetch_weather()
        self.config.warn_unreasonable_surfaces()
        data = compute_irrigation_data(
            crops=self.config.crops,
            kc_data=self._kc_data,
            eto_mm=eto_mm,
            precipitation_mm=precipitation_mm,
            kc_getter=get_kc,
            watering_applied_today=self.config.watering_applied_today,
            cumulative_need=self.config.cumulative_need,
        )
        self._last_daily_needs = {cid: r.daily_need_liters for cid, r in data.crops.items()}
        return data

    async def _fetch_weather(self) -> tuple[float, float]:
        """Appelle Open-Meteo pour obtenir l'ETo et les précipitations du jour."""
        lat = self.hass.config.latitude
        lon = self.hass.config.longitude
        _LOGGER.debug("Récupération météo Open-Meteo (lat=%s, lon=%s)", lat, lon)

        session = async_get_clientsession(self.hass)
        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": "et0_fao_evapotranspiration_sum,precipitation_sum",
            "timezone": "auto",
            "forecast_days": 1,
        }

        try:
            async with session.get(
                OPEN_METEO_URL, params=params, timeout=OPEN_METEO_TIMEOUT
            ) as resp:
                resp.raise_for_status()
                data = await resp.json(content_type=None)
        except Exception as exc:
            raise UpdateFailed(
                f"Erreur Open-Meteo (lat={lat}, lon={lon}) : {exc}"
            ) from exc

        try:
            daily = data["daily"]
            eto_mm = daily["et0_fao_evapotranspiration_sum"][0]
            precipitation_mm = daily["precipitation_sum"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise UpdateFailed(f"Réponse Open-Meteo invalide : {data!r}") from exc

        if eto_mm is None:
            raise UpdateFailed("L'ETo retourné par Open-Meteo est None.")

        precipitation_mm = float(precipitation_mm) if precipitation_mm is not None else 0.0
        _LOGGER.debug(
            "Open-Meteo — ETo=%.2f mm/j, précipitations=%.2f mm",
            float(eto_mm),
            precipitation_mm,
        )
        return float(eto_mm), precipitation_mm

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _schedule_config_save(self) -> None:
        """Planifie une sauvegarde avec debounce 0.5 s et gestion d'erreur."""
        if self._save_unsub is not None:
            self._save_unsub()

        @callback
        def _trigger(_now=None) -> None:
            self._save_unsub = None
            self.hass.async_create_task(
                self._persist_config(), name=f"{DOMAIN}_config_save"
            )

        self._save_unsub = async_call_later(self.hass, 0.5, _trigger)

    async def _persist_config(self) -> None:
        try:
            await self._persistence.async_save(
                self.config.to_storage(dt_util.now().date().isoformat())
            )
        except Exception as exc:
            _LOGGER.warning("Échec de la sauvegarde de la configuration : %s", exc)

