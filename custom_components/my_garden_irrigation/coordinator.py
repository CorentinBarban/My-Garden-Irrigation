"""Coordinateur de données — My Garden Irrigation.

L'ETo est récupéré depuis l'API Open-Meteo (gratuite, sans clé API) en utilisant
la latitude/longitude configurée dans Home Assistant (hass.config).
La mise à jour se fait toutes les heures via SCAN_INTERVAL.

ADR-008 : bilan hydrique cumulé — persisté via Store, accumulé à minuit.
ADR-009 : vanne globale — écoute les changements d'état, calcule le volume distribué.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_point_in_time, async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CROP_ID,
    CONF_CROPS,
    CONF_DENSITY,
    CONF_GLOBAL_FLOW_RATE,
    CONF_GLOBAL_VALVE_ENTITY_ID,
    CONF_IRRIGATION_TIME,
    CONF_NB_PLANTS,
    CONF_WATERING_FREQUENCY,
    CONF_WATERING_INTERVAL_DAYS,
    CONF_WATERING_MODE,
    DEFAULT_CYCLES_COUNT,
    DEFAULT_IRRIGATION_TIME,
    DEFAULT_SOAK_DURATION_MINUTES,
    DOMAIN,
    MAX_REASONABLE_SURFACE_M2,
    OPEN_METEO_TIMEOUT,
    OPEN_METEO_URL,
    STORAGE_VERSION,
    WATERING_FREQUENCY_INTERVAL,
    WATERING_MODE_FRACTIONED,
)
from .core.calculations import compute_irrigation_data, compute_surface_m2
from .core.kc_data import get_kc
from .core.models import IrrigationData
from .kc_loader import async_load_kc_data

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(hours=1)

_OPEN_STATES = {"on", "open"}
_CLOSED_STATES = {"off", "closed"}


class IrrigationCoordinator(DataUpdateCoordinator[IrrigationData]):
    """Calcule les besoins en eau de toutes les cultures configurées.

    L'ETo est obtenu depuis Open-Meteo à partir des coordonnées HA.
    Délègue la logique métier à core.calculations.compute_irrigation_data.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self._entry = entry
        self._kc_data: dict = {}
        # Bilan hydrique (ADR-008)
        self._watering_applied_today: dict[str, float] = {}
        self._cumulative_need: dict[str, float] = {}
        self._store: Store | None = None
        # Vanne globale (ADR-009)
        self._valve_open_time: datetime | None = None
        self._valve_listener_unsub: Callable | None = None
        self._midnight_unsub: Callable | None = None
        # Arrosage automatique
        self._auto_enabled: bool = False
        self._last_auto_watering_date: str | None = None
        self._auto_irrigation_unsub: Callable | None = None
        self._irrigation_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Propriétés HA
    # ------------------------------------------------------------------

    @property
    def crops(self) -> list[dict]:
        return self._entry.options.get(CONF_CROPS, [])

    # ------------------------------------------------------------------
    # Cycle de vie
    # ------------------------------------------------------------------

    async def async_setup(self) -> None:
        """Charge les données Kc, restaure l'état persisté et configure les listeners."""
        self._kc_data = await async_load_kc_data(self.hass)

        # Restauration du bilan hydrique depuis le stockage HA
        self._store = Store(
            self.hass,
            STORAGE_VERSION,
            f"{DOMAIN}.{self._entry.entry_id}.water_balance",
        )
        stored = await self._store.async_load()
        if stored:
            self._cumulative_need = stored.get("cumulative_need", {})
            stored_date = stored.get("watering_date")
            today = dt_util.now().date().isoformat()
            if stored_date == today:
                self._watering_applied_today = stored.get("watering_applied_today", {})
            self._auto_enabled = stored.get("auto_irrigation_enabled", False)
            self._last_auto_watering_date = stored.get("last_auto_watering_date")
            valve_open_time_str: str | None = stored.get("valve_open_time")
            if valve_open_time_str:
                self._valve_open_time = datetime.fromisoformat(valve_open_time_str)

        if self._auto_enabled and self._last_auto_watering_date is None:
            self._last_auto_watering_date = dt_util.now().date().isoformat()

        await self._restore_valve_state()
        self._setup_valve_listener()
        self._schedule_midnight_update()
        self._setup_auto_irrigation()

        @callback
        def _cleanup() -> None:
            if self._valve_listener_unsub is not None:
                self._valve_listener_unsub()
            if self._midnight_unsub is not None:
                self._midnight_unsub()
            if self._auto_irrigation_unsub is not None:
                self._auto_irrigation_unsub()
            if self._irrigation_task and not self._irrigation_task.done():
                self._irrigation_task.cancel()

        self._entry.async_on_unload(_cleanup)

        await self.async_config_entry_first_refresh()

        # Amorçage du cumulé au premier démarrage (aucune donnée persistée).
        # Sans ceci, le total cumulé resterait 0 jusqu'à minuit alors que les
        # plantes ont déjà un besoin journalier calculé depuis l'ETo du jour.
        if not self._cumulative_need and self.data is not None:
            for crop_id, result in self.data.crops.items():
                self._cumulative_need[crop_id] = result.daily_need_liters
            await self._save_state()
            await self.async_refresh()

    # ------------------------------------------------------------------
    # Vanne globale (ADR-009)
    # ------------------------------------------------------------------

    async def _restore_valve_state(self) -> None:
        """Réconcilie _valve_open_time avec l'état réel de la vanne après redémarrage."""
        valve_id: str | None = self._entry.options.get(CONF_GLOBAL_VALVE_ENTITY_ID)
        if not valve_id:
            return
        state = self.hass.states.get(valve_id)
        if state is None:
            return
        current = state.state
        if current in _OPEN_STATES:
            if self._valve_open_time is None:
                self._valve_open_time = dt_util.utcnow()
                _LOGGER.warning(
                    "Vanne %s ouverte au démarrage sans heure d'ouverture connue — "
                    "décompte du volume depuis maintenant.",
                    valve_id,
                )
        elif current in _CLOSED_STATES and self._valve_open_time is not None:
            _LOGGER.info(
                "Vanne %s fermée pendant le redémarrage — comptabilisation du volume.",
                valve_id,
            )
            await self._handle_valve_close()

    def _setup_valve_listener(self) -> None:
        valve_entity_id = self._entry.options.get(CONF_GLOBAL_VALVE_ENTITY_ID)
        if not valve_entity_id:
            return
        self._valve_listener_unsub = async_track_state_change_event(
            self.hass, [valve_entity_id], self._handle_valve_state_change
        )
        _LOGGER.debug("Écoute de la vanne globale : %s", valve_entity_id)

    async def _handle_valve_state_change(self, event: Event) -> None:
        """Détecte l'ouverture/fermeture de la vanne globale et met à jour le bilan."""
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")
        if old_state is None or new_state is None:
            return

        old = old_state.state
        new = new_state.state

        if old in _CLOSED_STATES and new in _OPEN_STATES:
            self._valve_open_time = dt_util.utcnow()
            _LOGGER.debug("Vanne ouverte à %s", self._valve_open_time)

        elif old in _OPEN_STATES and new in _CLOSED_STATES:
            await self._handle_valve_close()

    async def _handle_valve_close(self) -> None:
        """Calcule le volume distribué, l'impute par culture, remet le cumulé à zéro."""
        if self._valve_open_time is None:
            return

        flow_rate: float = self._entry.options.get(CONF_GLOBAL_FLOW_RATE, 0.0)
        duration_s = (dt_util.utcnow() - self._valve_open_time).total_seconds()
        total_volume = (duration_s / 3600.0) * flow_rate
        self._valve_open_time = None

        _LOGGER.debug(
            "Vanne fermée — durée=%.0fs, débit=%.1fL/h → volume distribué=%.1fL",
            duration_s,
            flow_rate,
            total_volume,
        )

        if total_volume > 0:
            surfaces = self._get_crop_surfaces()
            total_surface = sum(surfaces.values())
            if total_surface > 0:
                for crop_id, surface in surfaces.items():
                    volume_for_crop = total_volume * (surface / total_surface)
                    self._watering_applied_today[crop_id] = (
                        self._watering_applied_today.get(crop_id, 0.0) + volume_for_crop
                    )

        # Remise à zéro du cumulé après arrosage (ADR-008)
        for crop_id in self._get_crop_ids():
            self._cumulative_need[crop_id] = 0.0

        await self._save_state()
        await self.async_refresh()

    # ------------------------------------------------------------------
    # Accumulation à minuit (ADR-008)
    # ------------------------------------------------------------------

    def _schedule_midnight_update(self) -> None:
        now = dt_util.now()
        next_midnight = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=5, microsecond=0
        )
        self._midnight_unsub = async_track_point_in_time(
            self.hass, self._handle_midnight, next_midnight
        )

    async def _handle_midnight(self, _now: datetime) -> None:
        """Ajoute le besoin journalier résiduel au cumulé et replanifie."""
        if self.data is not None:
            for crop_id, result in self.data.crops.items():
                self._cumulative_need[crop_id] = (
                    self._cumulative_need.get(crop_id, 0.0) + result.daily_need_liters
                )
            _LOGGER.debug(
                "Accumulation minuit — bilan cumulé : %s",
                {k: round(v, 1) for k, v in self._cumulative_need.items()},
            )

        self._watering_applied_today = {}
        await self._save_state()
        await self.async_refresh()
        self._schedule_midnight_update()

    # ------------------------------------------------------------------
    # Arrosage automatique
    # ------------------------------------------------------------------

    @property
    def auto_irrigation_enabled(self) -> bool:
        return self._auto_enabled

    @property
    def last_auto_watering_date(self) -> str | None:
        return self._last_auto_watering_date

    def _setup_auto_irrigation(self) -> None:
        """Planifie (ou annule) le déclenchement quotidien de l'arrosage automatique."""
        if self._auto_irrigation_unsub is not None:
            self._auto_irrigation_unsub()
            self._auto_irrigation_unsub = None

        if not self._auto_enabled:
            return

        time_str: str = self._entry.options.get(CONF_IRRIGATION_TIME, DEFAULT_IRRIGATION_TIME)
        try:
            parts = time_str.split(":")
            hour, minute = int(parts[0]), int(parts[1])
        except (ValueError, AttributeError, IndexError):
            hour, minute = 6, 0

        now = dt_util.now()
        next_trigger = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_trigger <= now:
            next_trigger += timedelta(days=1)

        self._auto_irrigation_unsub = async_track_point_in_time(
            self.hass, self._handle_auto_irrigation, next_trigger
        )
        _LOGGER.debug("Arrosage automatique planifié à %s", next_trigger)

    async def _handle_auto_irrigation(self, _now: datetime) -> None:
        """Appelé à l'heure planifiée : vérifie les conditions puis lance la séquence."""
        frequency: str = self._entry.options.get(CONF_WATERING_FREQUENCY, "daily")
        if frequency == WATERING_FREQUENCY_INTERVAL:
            interval_days: int = self._entry.options.get(CONF_WATERING_INTERVAL_DAYS, 2)
            today = dt_util.now().date()
            if self._last_auto_watering_date:
                from datetime import date as _date
                days_since = (today - _date.fromisoformat(self._last_auto_watering_date)).days
                if days_since < interval_days:
                    _LOGGER.debug(
                        "Arrosage auto ignoré — intervalle %dj, dernier arrosage il y a %dj.",
                        interval_days, days_since,
                    )
                    self._setup_auto_irrigation()
                    return

        await self.async_run_irrigation_sequence()
        self._setup_auto_irrigation()

    async def async_set_auto_irrigation(self, enabled: bool) -> None:
        """Active ou désactive l'arrosage automatique depuis le switch HA."""
        self._auto_enabled = enabled
        if enabled and self._last_auto_watering_date is None:
            self._last_auto_watering_date = dt_util.now().date().isoformat()
        await self._save_state()
        self._setup_auto_irrigation()
        await self.async_refresh()

    async def async_run_irrigation_sequence(self) -> None:
        """Lance la séquence d'arrosage (utilise le bilan cumulé de la centrale)."""
        if self._irrigation_task and not self._irrigation_task.done():
            _LOGGER.debug("Séquence d'arrosage déjà en cours.")
            return
        self._irrigation_task = self.hass.async_create_task(
            self._irrigation_sequence_task(),
            "my_garden_irrigation_sequence",
        )

    async def async_stop_irrigation(self) -> None:
        """Annule la séquence en cours et ferme la vanne."""
        if self._irrigation_task and not self._irrigation_task.done():
            self._irrigation_task.cancel()
            try:
                await self._irrigation_task
            except asyncio.CancelledError:
                pass

    async def _irrigation_sequence_task(self) -> None:
        """Tâche asyncio : ouvre la vanne, attend, ferme — gère le mode fractionné."""
        data = self.data
        if data is None:
            return

        total_cumulative = sum(data.cumulative_need.values())
        if total_cumulative <= 0:
            _LOGGER.debug("Arrosage auto : besoin cumulé = 0 L — ignoré.")
            self._last_auto_watering_date = dt_util.now().date().isoformat()
            await self._save_state()
            return

        flow_rate: float = self._entry.options.get(CONF_GLOBAL_FLOW_RATE, 0.0)
        valve_id: str | None = self._entry.options.get(CONF_GLOBAL_VALVE_ENTITY_ID)
        if not valve_id or flow_rate <= 0:
            _LOGGER.warning(
                "Arrosage auto : vanne ou débit non configuré (vanne=%s, débit=%.1f L/h).",
                valve_id, flow_rate,
            )
            return

        duration_s = (total_cumulative / flow_rate) * 3600
        watering_mode: str = self._entry.options.get(CONF_WATERING_MODE, "continuous")

        _LOGGER.info(
            "Arrosage automatique démarré — besoin=%.1fL, durée=%.0fs, mode=%s.",
            total_cumulative, duration_s, watering_mode,
        )

        async def _open() -> None:
            await self.hass.services.async_call(
                "homeassistant", "turn_on", {"entity_id": valve_id}, blocking=True
            )

        async def _close() -> None:
            await self.hass.services.async_call(
                "homeassistant", "turn_off", {"entity_id": valve_id}, blocking=True
            )

        try:
            if watering_mode == WATERING_MODE_FRACTIONED:
                cycle_s = duration_s / DEFAULT_CYCLES_COUNT
                soak_s = DEFAULT_SOAK_DURATION_MINUTES * 60
                for i in range(DEFAULT_CYCLES_COUNT):
                    await _open()
                    await asyncio.sleep(cycle_s)
                    await _close()
                    if i < DEFAULT_CYCLES_COUNT - 1:
                        await asyncio.sleep(soak_s)
            else:
                await _open()
                await asyncio.sleep(duration_s)
                await _close()
        except asyncio.CancelledError:
            _LOGGER.info("Séquence d'arrosage annulée — fermeture de la vanne.")
            await _close()
            raise

        self._last_auto_watering_date = dt_util.now().date().isoformat()
        await self._save_state()
        _LOGGER.info("Arrosage automatique terminé.")

    # ------------------------------------------------------------------
    # Reset manuel (bouton centrale)
    # ------------------------------------------------------------------

    async def async_reset_irrigation(self) -> None:
        """Remet le bilan hydrique cumulé et les arrosages du jour à zéro."""
        self._cumulative_need = {}
        self._watering_applied_today = {}
        await self._save_state()
        await self.async_refresh()

    # ------------------------------------------------------------------
    # Persistance (ADR-008)
    # ------------------------------------------------------------------

    async def _save_state(self) -> None:
        if self._store is None:
            return
        await self._store.async_save(
            {
                "cumulative_need": self._cumulative_need,
                "watering_applied_today": self._watering_applied_today,
                "watering_date": dt_util.now().date().isoformat(),
                "auto_irrigation_enabled": self._auto_enabled,
                "last_auto_watering_date": self._last_auto_watering_date,
                "valve_open_time": self._valve_open_time.isoformat() if self._valve_open_time else None,
            }
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_crop_surfaces(self) -> dict[str, float]:
        return {
            crop[CONF_CROP_ID]: compute_surface_m2(crop[CONF_NB_PLANTS], crop[CONF_DENSITY])
            for crop in self.crops
        }

    def _get_crop_ids(self) -> list[str]:
        return [crop[CONF_CROP_ID] for crop in self.crops]

    # ------------------------------------------------------------------
    # Calcul principal — pont HA → core/
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> IrrigationData:
        """Récupère ETo et précipitations depuis Open-Meteo et calcule les besoins nets."""
        eto_mm, precipitation_mm = await self._fetch_weather()
        self._warn_unreasonable_surfaces()
        return compute_irrigation_data(
            crops=self.crops,
            kc_data=self._kc_data,
            eto_mm=eto_mm,
            precipitation_mm=precipitation_mm,
            kc_getter=get_kc,
            watering_applied_today=self._watering_applied_today,
            cumulative_need=self._cumulative_need,
        )

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
            raise UpdateFailed(
                f"Réponse Open-Meteo invalide : {data!r}"
            ) from exc

        if eto_mm is None:
            raise UpdateFailed("L'ETo retourné par Open-Meteo est None.")

        precipitation_mm = float(precipitation_mm) if precipitation_mm is not None else 0.0
        _LOGGER.debug(
            "Open-Meteo — ETo=%.2f mm/j, précipitations=%.2f mm",
            float(eto_mm),
            precipitation_mm,
        )
        return float(eto_mm), precipitation_mm

    def _warn_unreasonable_surfaces(self) -> None:
        """Log un avertissement si une culture a une surface anormalement grande."""
        for crop in self.crops:
            nb_plants = crop.get("nb_plants", 0)
            density = crop.get("density", 1)
            if density > 0 and (nb_plants / density) > MAX_REASONABLE_SURFACE_M2:
                _LOGGER.warning(
                    "Surface calculée (%s m²) anormalement élevée pour '%s' — "
                    "vérifiez nb_plants (%s) et densité (%s).",
                    round(nb_plants / density),
                    crop.get("crop_type"),
                    nb_plants,
                    density,
                )
