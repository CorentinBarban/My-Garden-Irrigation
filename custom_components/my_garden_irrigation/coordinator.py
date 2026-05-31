"""Coordinateur de données — My Garden Irrigation.

Responsabilité unique : récupérer l'ETo via Open-Meteo et calculer
IrrigationData. Le suivi de la vanne et la planification temporelle
sont délégués à valve_tracker.py et scheduler.py.

ADR-008 : bilan hydrique cumulé — persisté via Store.
ADR-009 : vanne globale — géré par ValveTracker.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CROP_ID,
    CONF_CROPS,
    CONF_CYCLES_COUNT,
    CONF_DENSITY,
    CONF_GLOBAL_FLOW_RATE,
    CONF_GLOBAL_VALVE_ENTITY_ID,
    CONF_IRRIGATION_TIME,
    CONF_NB_PLANTS,
    CONF_SOAK_DURATION,
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

# Clés de config globale persistées hors entry.options (runtime overrides)
_RUNTIME_CONFIG_KEYS = (
    CONF_GLOBAL_FLOW_RATE,
    CONF_WATERING_INTERVAL_DAYS,
    CONF_WATERING_FREQUENCY,
    CONF_WATERING_MODE,
    CONF_IRRIGATION_TIME,
    CONF_CYCLES_COUNT,
    CONF_SOAK_DURATION,
)


def _options_hash(options: dict) -> str:
    """Hash stable des clés de config globale dans entry.options.

    Permet de détecter si entry.options a changé depuis le dernier save
    runtime (i.e. l'utilisateur a soumis le formulaire entre-temps).
    Si le hash diffère, les overrides entity sont ignorés : le formulaire
    fait autorité.
    """
    relevant = {k: options.get(k) for k in _RUNTIME_CONFIG_KEYS}
    return hashlib.md5(
        json.dumps(relevant, sort_keys=True, default=str).encode()
    ).hexdigest()


class IrrigationCoordinator(DataUpdateCoordinator[IrrigationData]):
    """Calcule les besoins en eau depuis Open-Meteo et le bilan hydrique.

    La logique vanne et la planification sont déléguées à ValveTracker
    et IrrigationScheduler qui sont instanciés dans async_setup().
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self._entry = entry

        # Données Kc et stockage persisté
        self._kc_data: dict = {}
        self._store: Store | None = None

        # Bilan hydrique (ADR-008)
        self._watering_applied_today: dict[str, float] = {}
        self._cumulative_need: dict[str, float] = {}

        # État de l'arrosage automatique
        self._auto_enabled: bool = False
        self._last_auto_watering_date: str | None = None

        # Temps d'ouverture de la vanne (persisté pour la réconciliation au redémarrage)
        self._valve_open_time: datetime | None = None

        # Configuration mutable en mémoire (mise à jour par les entités via RestoreEntity)
        self._crop_data: list[dict] = list(entry.options.get(CONF_CROPS, []))
        self._flow_rate: float = float(entry.options.get(CONF_GLOBAL_FLOW_RATE, 0.0))
        self._watering_interval_days: int = int(entry.options.get(CONF_WATERING_INTERVAL_DAYS, 2))
        self._watering_frequency: str = entry.options.get(CONF_WATERING_FREQUENCY, "daily")
        self._watering_mode: str = entry.options.get(CONF_WATERING_MODE, "continuous")
        self._irrigation_time: str = entry.options.get(CONF_IRRIGATION_TIME, DEFAULT_IRRIGATION_TIME)
        self._cycles_count: int = int(entry.options.get(CONF_CYCLES_COUNT, DEFAULT_CYCLES_COUNT))
        self._soak_duration_minutes: int = int(
            entry.options.get(CONF_SOAK_DURATION, DEFAULT_SOAK_DURATION_MINUTES)
        )

        # Sous-modules (instanciés dans async_setup)
        self._scheduler: Any = None

    # ------------------------------------------------------------------
    # Propriétés — lecture du runtime config
    # ------------------------------------------------------------------

    @property
    def crops(self) -> list[dict]:
        return self._crop_data

    @property
    def auto_irrigation_enabled(self) -> bool:
        return self._auto_enabled

    @property
    def last_auto_watering_date(self) -> str | None:
        return self._last_auto_watering_date

    @property
    def flow_rate(self) -> float:
        return self._flow_rate

    @property
    def watering_frequency(self) -> str:
        return self._watering_frequency

    @property
    def watering_interval_days(self) -> int:
        return self._watering_interval_days

    @property
    def watering_mode(self) -> str:
        return self._watering_mode

    @property
    def irrigation_time(self) -> str:
        return self._irrigation_time

    @property
    def cycles_count(self) -> int:
        return self._cycles_count

    @property
    def soak_duration_minutes(self) -> int:
        return self._soak_duration_minutes

    @property
    def valve_entity_id(self) -> str | None:
        return self._entry.options.get(CONF_GLOBAL_VALVE_ENTITY_ID)

    # ------------------------------------------------------------------
    # Mutateurs — appelés par les entités RestoreEntity
    # ------------------------------------------------------------------

    def update_crop_field(self, crop_id: str, field: str, value: object) -> None:
        """Met à jour un champ d'une culture dans la copie en mémoire."""
        for crop in self._crop_data:
            if crop[CONF_CROP_ID] == crop_id:
                crop[field] = value
                return

    def set_flow_rate(self, value: float) -> None:
        self._flow_rate = value
        self._schedule_config_save()

    def set_watering_interval_days(self, value: int) -> None:
        self._watering_interval_days = value
        self._schedule_config_save()

    def set_watering_frequency(self, value: str) -> None:
        self._watering_frequency = value
        self._schedule_config_save()

    def set_watering_mode(self, value: str) -> None:
        self._watering_mode = value
        self._schedule_config_save()

    def set_irrigation_time(self, value: str) -> None:
        self._irrigation_time = value
        if self._scheduler is not None:
            self._scheduler.reschedule_auto_irrigation()
        self._schedule_config_save()

    def set_cycles_count(self, value: int) -> None:
        self._cycles_count = value
        self._schedule_config_save()

    def set_soak_duration_minutes(self, value: int) -> None:
        self._soak_duration_minutes = value
        self._schedule_config_save()

    def _schedule_config_save(self) -> None:
        """Planifie une sauvegarde du runtime config sans bloquer le thread."""
        if self._store is not None:
            self.hass.async_create_task(self._save_state())

    # ------------------------------------------------------------------
    # API pour ValveTracker
    # ------------------------------------------------------------------

    def get_valve_open_time(self) -> datetime | None:
        return self._valve_open_time

    def set_valve_open_time(self, time: datetime | None) -> None:
        self._valve_open_time = time

    def get_crop_surfaces(self) -> dict[str, float]:
        return {
            crop[CONF_CROP_ID]: compute_surface_m2(crop[CONF_NB_PLANTS], crop[CONF_DENSITY])
            for crop in self._crop_data
        }

    async def apply_watering_volumes(self, volumes: dict[str, float]) -> None:
        """Impute les volumes distribués par culture et remet le cumulé à zéro."""
        for crop_id, vol in volumes.items():
            self._watering_applied_today[crop_id] = (
                self._watering_applied_today.get(crop_id, 0.0) + vol
            )
        for crop_id in self._get_crop_ids():
            self._cumulative_need[crop_id] = 0.0
        await self._save_state()
        await self.async_refresh()

    # ------------------------------------------------------------------
    # API pour IrrigationScheduler
    # ------------------------------------------------------------------

    async def handle_midnight_transfer(self) -> None:
        """Accumule le besoin journalier au cumulé et remet le suivi du jour à zéro."""
        from .core.ledger import midnight_transfer

        if self.data is not None:
            daily_needs = {
                crop_id: result.daily_need_liters
                for crop_id, result in self.data.crops.items()
            }
            self._cumulative_need = midnight_transfer(self._cumulative_need, daily_needs)
            _LOGGER.debug(
                "Accumulation minuit — bilan cumulé : %s",
                {k: round(v, 1) for k, v in self._cumulative_need.items()},
            )

        self._watering_applied_today = {}
        await self._save_state()
        await self.async_refresh()

    async def async_set_auto_irrigation(self, enabled: bool) -> None:
        """Active ou désactive l'arrosage automatique depuis le switch HA."""
        self._auto_enabled = enabled
        if enabled and self._last_auto_watering_date is None:
            self._last_auto_watering_date = dt_util.now().date().isoformat()
        await self._save_state()
        if self._scheduler is not None:
            self._scheduler.reschedule_auto_irrigation()
        await self.async_refresh()

    def fire_irrigation_event(self) -> None:
        """Émet l'événement HA que le blueprint d'automatisation écoute.

        Le payload contient tous les paramètres nécessaires au blueprint pour
        piloter la vanne physique de manière sécurisée via le moteur natif HA.
        """
        data = self.data
        if data is None:
            return

        total_cumulative = sum(data.cumulative_need.values())
        if total_cumulative <= 0:
            _LOGGER.debug("Arrosage auto : besoin cumulé = 0 L — événement non émis.")
            return

        if self._flow_rate <= 0:
            _LOGGER.warning(
                "Arrosage auto : débit non configuré (%.1f L/h) — événement non émis.",
                self._flow_rate,
            )
            return

        duration_minutes = round((total_cumulative / self._flow_rate) * 60, 1)
        is_fractioned = self._watering_mode == WATERING_MODE_FRACTIONED

        payload: dict[str, Any] = {
            "entry_id": self._entry.entry_id,
            "valve_entity_id": self.valve_entity_id,
            "total_volume_liters": round(total_cumulative, 1),
            "recommended_duration_minutes": duration_minutes,
            "is_fractioned": is_fractioned,
        }
        if is_fractioned:
            payload["cycles_count"] = self._cycles_count
            payload["duration_per_cycle_minutes"] = round(
                duration_minutes / self._cycles_count, 1
            )
            payload["soak_duration_minutes"] = self._soak_duration_minutes

        self.hass.bus.async_fire(f"{DOMAIN}_irrigation_requested", payload)
        _LOGGER.info(
            "Événement %s_irrigation_requested émis — durée=%.1f min, mode=%s.",
            DOMAIN,
            duration_minutes,
            self._watering_mode,
        )

    async def update_last_watering_date(self, date_iso: str) -> None:
        """Met à jour la date du dernier arrosage et persiste l'état."""
        self._last_auto_watering_date = date_iso
        await self._save_state()

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
    # Cycle de vie
    # ------------------------------------------------------------------

    async def async_setup(self) -> None:
        """Charge Kc, restaure l'état persisté, initialise les sous-modules."""
        from .scheduler import IrrigationScheduler
        from .valve_tracker import ValveTracker

        self._kc_data = await async_load_kc_data(self.hass)

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

            # Restaure les overrides de config globale faits via les entités HA.
            # Le hash garantit que si l'utilisateur a soumis le formulaire entre-temps
            # (entry.options a changé), les anciennes valeurs runtime sont ignorées
            # et les nouvelles valeurs du formulaire restent autoritaires.
            runtime = stored.get("runtime_config", {})
            if runtime and runtime.get("options_hash") == _options_hash(self._entry.options):
                if CONF_GLOBAL_FLOW_RATE in runtime:
                    self._flow_rate = float(runtime[CONF_GLOBAL_FLOW_RATE])
                if CONF_WATERING_INTERVAL_DAYS in runtime:
                    self._watering_interval_days = int(runtime[CONF_WATERING_INTERVAL_DAYS])
                if CONF_WATERING_FREQUENCY in runtime:
                    self._watering_frequency = str(runtime[CONF_WATERING_FREQUENCY])
                if CONF_WATERING_MODE in runtime:
                    self._watering_mode = str(runtime[CONF_WATERING_MODE])
                if CONF_IRRIGATION_TIME in runtime:
                    self._irrigation_time = str(runtime[CONF_IRRIGATION_TIME])
                if CONF_CYCLES_COUNT in runtime:
                    self._cycles_count = int(runtime[CONF_CYCLES_COUNT])
                if CONF_SOAK_DURATION in runtime:
                    self._soak_duration_minutes = int(runtime[CONF_SOAK_DURATION])
                _LOGGER.debug("Runtime config restauré depuis le Store.")

        if self._auto_enabled and self._last_auto_watering_date is None:
            self._last_auto_watering_date = dt_util.now().date().isoformat()

        tracker = ValveTracker(self.hass, self)
        scheduler = IrrigationScheduler(self.hass, self)
        self._scheduler = scheduler

        self._entry.async_on_unload(tracker.setup())
        self._entry.async_on_unload(scheduler.setup())

        await self.async_config_entry_first_refresh()

        if not self._cumulative_need and self.data is not None:
            for crop_id, result in self.data.crops.items():
                self._cumulative_need[crop_id] = result.daily_need_liters
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
                "valve_open_time": (
                    self._valve_open_time.isoformat() if self._valve_open_time else None
                ),
                # Overrides de config globale faits via les entités HA (sans formulaire).
                # Le hash permet de détecter si entry.options a changé depuis ce save.
                "runtime_config": {
                    "options_hash": _options_hash(self._entry.options),
                    CONF_GLOBAL_FLOW_RATE: self._flow_rate,
                    CONF_WATERING_INTERVAL_DAYS: self._watering_interval_days,
                    CONF_WATERING_FREQUENCY: self._watering_frequency,
                    CONF_WATERING_MODE: self._watering_mode,
                    CONF_IRRIGATION_TIME: self._irrigation_time,
                    CONF_CYCLES_COUNT: self._cycles_count,
                    CONF_SOAK_DURATION: self._soak_duration_minutes,
                },
            }
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_crop_ids(self) -> list[str]:
        return [crop[CONF_CROP_ID] for crop in self._crop_data]

    def _warn_unreasonable_surfaces(self) -> None:
        for crop in self._crop_data:
            nb_plants = crop.get(CONF_NB_PLANTS, 0)
            density = crop.get(CONF_DENSITY, 1)
            if density > 0 and (nb_plants / density) > MAX_REASONABLE_SURFACE_M2:
                _LOGGER.warning(
                    "Surface calculée (%s m²) anormalement élevée pour '%s' — "
                    "vérifiez nb_plants (%s) et densité (%s).",
                    round(nb_plants / density),
                    crop.get("crop_type"),
                    nb_plants,
                    density,
                )

    # ------------------------------------------------------------------
    # Calcul principal
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> IrrigationData:
        """Récupère ETo et précipitations puis calcule les besoins nets."""
        eto_mm, precipitation_mm = await self._fetch_weather()
        self._warn_unreasonable_surfaces()
        return compute_irrigation_data(
            crops=self._crop_data,
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
