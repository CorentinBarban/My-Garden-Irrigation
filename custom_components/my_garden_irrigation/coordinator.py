"""Coordinateur de données — My Garden Irrigation.

L'ETo est récupéré depuis l'API Open-Meteo (gratuite, sans clé API) en utilisant
la latitude/longitude configurée dans Home Assistant (hass.config).
La mise à jour se fait toutes les heures via SCAN_INTERVAL.

ADR-008 : bilan hydrique cumulé — persisté via Store, accumulé à minuit.
ADR-009 : vanne globale — écoute les changements d'état, calcule le volume distribué.
"""
from __future__ import annotations

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
    CONF_NB_PLANTS,
    DOMAIN,
    MAX_REASONABLE_SURFACE_M2,
    OPEN_METEO_TIMEOUT,
    OPEN_METEO_URL,
    STORAGE_VERSION,
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

        self._setup_valve_listener()
        self._schedule_midnight_update()

        @callback
        def _cleanup() -> None:
            if self._valve_listener_unsub is not None:
                self._valve_listener_unsub()
            if self._midnight_unsub is not None:
                self._midnight_unsub()

        self._entry.async_on_unload(_cleanup)

        await self.async_config_entry_first_refresh()

    # ------------------------------------------------------------------
    # Vanne globale (ADR-009)
    # ------------------------------------------------------------------

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
