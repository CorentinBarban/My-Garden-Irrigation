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

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .config_state import RuntimeConfigState
from .core.journal import DailyWaterLedger, WaterSource, WaterTransaction
from .core.ledger import MidnightClosureOrchestrator
from .core.strategies import WateringStrategyFactory, WateringVolumeStrategy
from .core.watering_plan import compute_watering_plan
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
from .logging_util import instance_logger
from .persistence import PersistenceManager

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(hours=1)
WEATHER_RETRY_INTERVAL = timedelta(minutes=15)


class IrrigationCoordinator(DataUpdateCoordinator[IrrigationData]):
    """Orchestre la récupération météo, le calcul et les sous-modules.

    Seul point d'entrée HA pour les entités. Délègue l'état à self.config
    (RuntimeConfigState) et la persistance à self._persistence
    (PersistenceManager).
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        log = instance_logger(_LOGGER, entry)
        super().__init__(hass, log, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self._log = log
        self._entry = entry
        self.config = RuntimeConfigState.from_entry(entry)
        self._persistence = PersistenceManager(hass, entry.entry_id, log)
        self._kc_data: dict = {}
        self._scheduler: Any = None
        self._last_daily_needs: dict[str, float] = {}
        self._last_weather: tuple[float, float] | None = None
        self._save_unsub: Any = None
        self._weather_retry_unsub: Any = None
        self._daily_ledger: DailyWaterLedger = DailyWaterLedger()

    # ------------------------------------------------------------------
    # Cycle de vie
    # ------------------------------------------------------------------

    async def async_setup(self) -> None:
        """Charge Kc, restaure l'état persisté, initialise les sous-modules."""
        from .scheduler import IrrigationScheduler
        from .valve_tracker import ValveTracker

        self._kc_data = await async_load_kc_data(self.hass)

        stored = await self._persistence.async_load()
        today = dt_util.now().date().isoformat()
        self.config.restore_from_storage(stored, today)
        self.config.cleanup_stale_crops()
        if stored and stored.get("daily_ledger_date") == today:
            self._daily_ledger = DailyWaterLedger.from_storage(
                stored.get("daily_ledger", [])
            )

        if self.config.auto_irrigation_enabled and self.config.last_auto_watering_date is None:
            self.config.set_auto_irrigation(True, dt_util.now().date().isoformat())

        tracker = ValveTracker(
            self.hass, self.config, self._on_volumes_applied, self._log
        )
        scheduler = IrrigationScheduler(
            self.hass, self.config, self._on_midnight, self._on_trigger, self._log
        )
        self._scheduler = scheduler

        self._entry.async_on_unload(await tracker.setup())
        self._entry.async_on_unload(scheduler.setup())

        @callback
        def _cancel_pending_save() -> None:
            if self._save_unsub is not None:
                self._save_unsub()
                self._save_unsub = None
            self._cancel_weather_retry()

        self._entry.async_on_unload(_cancel_pending_save)

        await self.async_config_entry_first_refresh()

        if self.data is not None:
            daily_needs = {cid: r.daily_need_liters for cid, r in self.data.crops.items()}
            new_crops_added = self.config.init_missing_crops(daily_needs)
            # Sauvegarde systématique : aligne l'options_hash persisté sur
            # entry.options courant pour préserver les overrides entity au rechargement.
            await self._async_save()
            if new_crops_added:
                await self._async_recompute_from_cache()

    # ------------------------------------------------------------------
    # Callbacks internes (appelés par ValveTracker et IrrigationScheduler)
    # ------------------------------------------------------------------

    async def _on_volumes_applied(self, volumes: dict[str, float]) -> None:
        self.config.apply_watering_volumes(volumes)
        now = dt_util.now()
        for crop_id, vol in volumes.items():
            self._daily_ledger.record(
                WaterTransaction(crop_id, -vol, WaterSource.IRRIGATION, now)
            )
        await self._async_save()
        await self.async_refresh()

    async def _on_midnight(self) -> None:
        """Clôt la journée : ajoute le solde du journal au bilan cumulé et le réinitialise.

        replay() fournit le solde net du jour (apport ETo − arrosages, planché à 0) ;
        un journal vide donne un solde {} qui laisse le cumulé inchangé (ADR-023/026).
        """
        daily_balance = self._daily_ledger.replay()
        new_cumulative = MidnightClosureOrchestrator().execute(
            self.config.cumulative_need, daily_balance
        )
        self.config.apply_midnight_result(new_cumulative)
        self._daily_ledger = DailyWaterLedger()
        await self._async_save()
        await self.async_refresh()

    async def _on_trigger(self, date_iso: str) -> None:
        """Évalue l'arrosage, puis réancre le cycle d'intervalle si — et seulement si —
        un arrosage a été effectivement émis (ADR-028, remplace la Règle 3 d'ADR-025).

        Un saut (réserve cumulée ou pluie qui annule le besoin du jour) ne réancre PAS
        le cycle : le planificateur réévalue dès le lendemain jusqu'à ce qu'un arrosage
        réel ait lieu. Sans données météo, tout est reporté au lendemain.
        """
        if self.data is None:
            self._log.warning(
                "Données météo indisponibles — arrosage et calendrier reportés, "
                "nouvelle tentative demain."
            )
            return
        if self.fire_irrigation_event():
            await self.update_last_watering_date(date_iso)
        else:
            self._log.info(
                "Aucun arrosage (réserve suffisante ou pluie) — cycle non réancré, "
                "réévaluation demain."
            )

    # ------------------------------------------------------------------
    # API publique — appelée par les entités HA
    # Thin delegates vers self.config + persistance + refresh si besoin.
    # ------------------------------------------------------------------

    async def async_update_crop_field(
        self, crop_id: str, field: str, value: object
    ) -> None:
        """Action utilisateur : met à jour un champ, rescale le cumulatif, rafraîchit."""
        self._log.debug("Réglage culture %s : %s = %s", crop_id, field, value)
        if field in _SURFACE_FIELDS and crop_id in self.config.cumulative_need:
            old_surface = self.config.get_crop_surfaces().get(crop_id, 0.0)
            self.config.update_crop_field(crop_id, field, value)
            new_surface = self.config.get_crop_surfaces().get(crop_id, 0.0)
            if old_surface > 0 and new_surface > 0:
                scale = new_surface / old_surface
                self.config.scale_cumulative_need(crop_id, scale)
        else:
            self.config.update_crop_field(crop_id, field, value)
        await self._async_save()
        await self.async_refresh()

    def set_flow_rate(self, value: float) -> None:
        self._log.debug("Réglage débit global = %s L/h", value)
        self.config.set_flow_rate(value)
        self._schedule_config_save()
        self._notify_listeners()

    def set_watering_interval_days(self, value: int) -> None:
        self._log.debug("Réglage intervalle d'arrosage = %s j", value)
        self.config.set_watering_interval_days(value)
        if self._scheduler is not None:
            # Ré-ancrage : l'utilisateur change l'intervalle → prochain arrosage
            # recalé sur N jours pleins depuis maintenant.
            self._scheduler.reschedule_auto_irrigation(reanchor=True)
        self._schedule_config_save()
        self._notify_listeners()

    def set_watering_frequency(self, value: str) -> None:
        self._log.debug("Réglage fréquence d'arrosage = %s", value)
        self.config.set_watering_frequency(value)
        if self._scheduler is not None:
            self._scheduler.reschedule_auto_irrigation(reanchor=True)
        self._schedule_config_save()
        self._notify_listeners()

    def set_watering_mode(self, value: str) -> None:
        self._log.debug("Réglage mode d'arrosage = %s", value)
        self.config.set_watering_mode(value)
        self._schedule_config_save()
        self._notify_listeners()

    def set_irrigation_time(self, value: str) -> None:
        self._log.debug("Réglage heure d'arrosage = %s", value)
        self.config.set_irrigation_time(value)
        if self._scheduler is not None:
            self._scheduler.reschedule_auto_irrigation()
        self._schedule_config_save()
        self._notify_listeners()

    def set_cycles_count(self, value: int) -> None:
        self._log.debug("Réglage nombre de cycles = %s", value)
        self.config.set_cycles_count(value)
        self._schedule_config_save()
        self._notify_listeners()

    def set_soak_duration_minutes(self, value: int) -> None:
        self._log.debug("Réglage durée de repos = %s min", value)
        self.config.set_soak_duration_minutes(value)
        self._schedule_config_save()
        self._notify_listeners()

    async def async_set_auto_irrigation(self, enabled: bool) -> None:
        self._log.info("Arrosage automatique %s.", "activé" if enabled else "désactivé")
        self.config.set_auto_irrigation(enabled, dt_util.now().date().isoformat())
        await self._async_save()
        if self._scheduler is not None:
            self._scheduler.reschedule_auto_irrigation()
        await self.async_refresh()

    async def async_reset_irrigation(self) -> None:
        self._log.info("Réinitialisation du bilan hydrique cumulé (action utilisateur).")
        self.config.reset_irrigation()
        self._daily_ledger = DailyWaterLedger()
        await self._async_save()
        await self.async_refresh()

    async def update_last_watering_date(self, date_iso: str) -> None:
        self.config.update_last_watering_date(date_iso)
        await self._async_save()

    @property
    def next_watering(self) -> datetime | None:
        """Date et heure du prochain arrosage automatique, ou None si non planifié."""
        if self._scheduler is None:
            return None
        return self._scheduler.next_trigger

    def _resolve_watering_strategy(self) -> WateringVolumeStrategy:
        """Sélectionne la stratégie de calcul du volume selon l'heure d'arrosage (ADR-024)."""
        return WateringStrategyFactory.from_irrigation_time(self.config.irrigation_time)

    def fire_irrigation_event(self) -> bool:
        """Émet l'événement HA que le blueprint d'automatisation écoute.

        Retourne True si l'événement a été effectivement émis, False sinon.
        L'appelant ne doit comptabiliser le déclenchement que si True est retourné.
        """
        data = self.data
        if data is None:
            self._log.warning(
                "Arrosage impossible : les données météo ne sont pas encore disponibles. "
                "Attendez le premier cycle de mise à jour (toutes les heures) avant de déclencher l'arrosage."
            )
            return False

        total_cumulative = sum(data.cumulative_need.values())

        # Décision inclusive (ADR-028) : dette/réserve cumulée + bilan net du jour.
        # Le bilan du jour peut être négatif (surplus de pluie) et la réserve cumulée
        # négative — le volume cible plafonné à 0 annule alors l'arrosage.
        strategy = self._resolve_watering_strategy()
        total_volume = strategy.calculate_target_volume(
            total_cumulative, data.total_daily_balance_liters
        )

        if total_volume <= 0:
            self._log.debug(
                "Arrosage auto : volume cible ≤ 0 L (cumulé=%.1fL, bilan jour=%.1fL) — "
                "réserve suffisante, événement non émis.",
                total_cumulative,
                data.total_daily_balance_liters,
            )
            return False

        flow_rate = self.config.flow_rate
        if flow_rate <= 0:
            self._log.warning(
                "Arrosage auto : débit non configuré (%.1f L/h) — événement non émis.",
                flow_rate,
            )
            return False

        is_fractioned = self.config.watering_mode == WATERING_MODE_FRACTIONED
        plan = compute_watering_plan(
            target_volume_liters=total_volume,
            flow_rate_lph=flow_rate,
            is_fractioned=is_fractioned,
            cycles_count=self.config.cycles_count,
            soak_duration_minutes=self.config.soak_duration_minutes,
        )

        payload: dict[str, Any] = {
            "entry_id": self._entry.entry_id,
            "valve_entity_id": self.config.valve_entity_id,
            "total_volume_liters": plan.target_volume_liters,
            "recommended_duration_minutes": plan.duration_minutes,
            "is_fractioned": plan.is_fractioned,
        }
        if is_fractioned:
            payload["cycles_count"] = plan.cycles_count
            payload["duration_per_cycle_minutes"] = plan.duration_per_cycle_minutes
            payload["soak_duration_minutes"] = plan.soak_duration_minutes

        # Une session continue compte une seule fermeture ; en mode fractionné, autant
        # de fermetures que de cycles (le ValveTracker ne comptabilise qu'à la dernière).
        self.config.begin_irrigation_session(plan.cycles_count if is_fractioned else 1)
        self.hass.bus.async_fire(f"{DOMAIN}_irrigation_requested", payload)
        self._log.info(
            "Événement %s_irrigation_requested émis — volume=%.1fL "
            "(cumulé=%.1fL + bilan jour=%.1fL), durée=%.1f min, mode=%s.",
            DOMAIN,
            total_volume,
            total_cumulative,
            data.total_daily_balance_liters,
            plan.duration_minutes,
            self.config.watering_mode,
        )
        return True

    # ------------------------------------------------------------------
    # Calcul principal
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> IrrigationData:
        """Récupère ETo et précipitations puis calcule les besoins nets."""
        try:
            eto_mm, precipitation_mm = await self._fetch_weather()
            self._last_weather = (eto_mm, precipitation_mm)
        except UpdateFailed as exc:
            if self.data is not None:
                self._log.warning(
                    "Open-Meteo inaccessible, nouvelle tentative dans %d min : %s",
                    WEATHER_RETRY_INTERVAL.seconds // 60,
                    exc,
                )
                self._schedule_weather_retry()
                return self.data
            raise
        self._cancel_weather_retry()
        self.config.warn_unreasonable_surfaces()
        data = compute_irrigation_data(
            crops=self.config.crops,
            kc_data=self._kc_data,
            eto_mm=eto_mm,
            precipitation_mm=precipitation_mm,
            kc_getter=get_kc,
            watering_applied_today=self._daily_ledger.applied_volumes(),
            cumulative_need=self.config.cumulative_need,
        )
        now = dt_util.now()
        self._last_daily_needs = {cid: r.daily_need_liters for cid, r in data.crops.items()}
        # Le journal porte le bilan hydrique signé du jour (ADR-028) — distinct du
        # besoin affiché (≥ 0) ; un surplus de pluie (valeur négative) alimente la réserve.
        for crop_id, result in data.crops.items():
            self._daily_ledger.set_daily_need(crop_id, result.daily_balance_liters, now)
        return data

    async def _async_recompute_from_cache(self) -> None:
        """Recalcule IrrigationData depuis le cache météo, sans appel HTTP.

        Utilisé après init_missing_crops pour éviter un second appel Open-Meteo
        au premier démarrage. Met à jour self.data et notifie les listeners.
        """
        if self._last_weather is None:
            return
        eto_mm, precipitation_mm = self._last_weather
        self.config.warn_unreasonable_surfaces()
        data = compute_irrigation_data(
            crops=self.config.crops,
            kc_data=self._kc_data,
            eto_mm=eto_mm,
            precipitation_mm=precipitation_mm,
            kc_getter=get_kc,
            watering_applied_today=self._daily_ledger.applied_volumes(),
            cumulative_need=self.config.cumulative_need,
        )
        now = dt_util.now()
        self._last_daily_needs = {cid: r.daily_need_liters for cid, r in data.crops.items()}
        # Le journal porte le bilan hydrique signé du jour (ADR-028) — distinct du
        # besoin affiché (≥ 0) ; un surplus de pluie (valeur négative) alimente la réserve.
        for crop_id, result in data.crops.items():
            self._daily_ledger.set_daily_need(crop_id, result.daily_balance_liters, now)
        self.async_set_updated_data(data)

    @callback
    def _schedule_weather_retry(self) -> None:
        """Planifie une nouvelle tentative météo si aucune n'est déjà en attente."""
        if self._weather_retry_unsub is not None:
            return

        @callback
        def _do_retry(_now: object = None) -> None:
            self._weather_retry_unsub = None
            self.hass.async_create_task(self.async_refresh())

        self._weather_retry_unsub = async_call_later(
            self.hass, WEATHER_RETRY_INTERVAL.total_seconds(), _do_retry
        )

    @callback
    def _cancel_weather_retry(self) -> None:
        if self._weather_retry_unsub is not None:
            self._weather_retry_unsub()
            self._weather_retry_unsub = None

    async def _fetch_weather(self) -> tuple[float, float]:
        """Appelle Open-Meteo pour obtenir l'ETo et les précipitations du jour."""
        lat = self.hass.config.latitude
        lon = self.hass.config.longitude
        self._log.debug("Récupération météo Open-Meteo (lat=%s, lon=%s)", lat, lon)

        session = async_get_clientsession(self.hass)
        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": "et0_fao_evapotranspiration_sum,precipitation_sum",
            "timezone": "auto",
            "forecast_days": 1,
        }

        response_data: dict | None = None
        for attempt in range(3):
            try:
                async with session.get(
                    OPEN_METEO_URL, params=params, timeout=OPEN_METEO_TIMEOUT
                ) as resp:
                    resp.raise_for_status()
                    response_data = await resp.json(content_type=None)
                break
            except aiohttp.ClientResponseError as exc:
                if exc.status in (502, 503, 504) and attempt < 2:
                    delay = 10 * (attempt + 1)
                    self._log.warning(
                        "Open-Meteo indisponible (HTTP %s), nouvelle tentative dans %ds (%d/3)…",
                        exc.status,
                        delay,
                        attempt + 1,
                    )
                    await asyncio.sleep(delay)
                else:
                    raise UpdateFailed(
                        f"Erreur Open-Meteo (lat={lat}, lon={lon}) : {exc}"
                    ) from exc
            except Exception as exc:
                raise UpdateFailed(
                    f"Erreur Open-Meteo (lat={lat}, lon={lon}) : {exc}"
                ) from exc

        if response_data is None:
            raise UpdateFailed(
                f"Open-Meteo inaccessible après 3 tentatives (lat={lat}, lon={lon})"
            )

        try:
            daily = response_data["daily"]
            eto_mm = daily["et0_fao_evapotranspiration_sum"][0]
            precipitation_mm = daily["precipitation_sum"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise UpdateFailed(f"Réponse Open-Meteo invalide : {response_data!r}") from exc

        if eto_mm is None:
            raise UpdateFailed("L'ETo retourné par Open-Meteo est None.")

        precipitation_mm = float(precipitation_mm) if precipitation_mm is not None else 0.0
        self._log.debug(
            "Open-Meteo — ETo=%.2f mm/j, précipitations=%.2f mm",
            float(eto_mm),
            precipitation_mm,
        )
        return float(eto_mm), precipitation_mm

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_storage(self) -> dict:
        """Sérialise config + journal de transactions pour la persistance (ADR-026)."""
        storage = self.config.to_storage(dt_util.now().date().isoformat())
        ledger_data = self._daily_ledger.to_storage()
        if ledger_data:
            storage["daily_ledger"] = ledger_data
            storage["daily_ledger_date"] = dt_util.now().date().isoformat()
        return storage

    async def _async_save(self) -> None:
        """Sérialise et persiste l'état courant ; journalise toute erreur sans la propager.

        Point d'entrée unique de la persistance. Les actions async l'appellent
        directement ; les setters synchrones passent par _schedule_config_save (debounce).
        """
        try:
            await self._persistence.async_save(self._build_storage())
        except Exception as exc:
            self._log.warning("Échec de la sauvegarde de l'état : %s", exc)

    @callback
    def _notify_listeners(self) -> None:
        """Rafraîchit les entités après un changement de config, sans appel météo.

        Appelé par les setters synchrones. Contrairement à async_set_updated_data,
        ne réinitialise pas le timer de polling horaire.
        """
        if self.data is not None:
            self.async_update_listeners()

    def _schedule_config_save(self) -> None:
        """Planifie une sauvegarde avec debounce 0.5 s (coalesce les réglages UI rapides)."""
        if self._save_unsub is not None:
            self._save_unsub()

        @callback
        def _trigger(_now=None) -> None:
            self._save_unsub = None
            self.hass.async_create_task(
                self._async_save(), name=f"{DOMAIN}_config_save"
            )

        self._save_unsub = async_call_later(self.hass, 0.5, _trigger)

