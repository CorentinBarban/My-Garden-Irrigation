"""Planificateur temporel — My Garden Irrigation.

Gère :
- L'accumulation à minuit (ADR-008) via async_track_point_in_time.
- Le déclenchement quotidien de l'arrosage automatique.

Ne connaît pas IrrigationCoordinator — reçoit RuntimeConfigState (état pur)
et deux callbacks async pour déléguer les effets de bord au coordinator.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.util import dt as dt_util

from .config_state import RuntimeConfigState
from .const import WATERING_FREQUENCY_INTERVAL

_LOGGER = logging.getLogger(__name__)


class IrrigationScheduler:
    """Planifie l'accumulation à minuit et l'arrosage automatique.

    on_midnight()              — appelé chaque nuit à 00:00:05 par le scheduler.
    on_trigger(date_iso: str)  — appelé quand les conditions d'arrosage sont remplies.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config: RuntimeConfigState,
        on_midnight: Callable[[], Awaitable[None]],
        on_trigger: Callable[[str], Awaitable[None]],
    ) -> None:
        self._hass = hass
        self._config = config
        self._on_midnight = on_midnight
        self._on_trigger = on_trigger
        self._midnight_unsub: Callable | None = None
        self._auto_unsub: Callable | None = None
        self.next_trigger: datetime | None = None

    def setup(self) -> Callable:
        """Initialise les listeners et retourne le callback de nettoyage."""
        self._schedule_midnight()
        self.reschedule_auto_irrigation()

        @callback
        def _cleanup() -> None:
            if self._midnight_unsub is not None:
                self._midnight_unsub()
            if self._auto_unsub is not None:
                self._auto_unsub()

        return _cleanup

    def reschedule_auto_irrigation(self, reanchor: bool = False) -> None:
        """Annule le déclenchement planifié et en recalcule un nouveau.

        reanchor=True : recale le prochain arrosage sur N jours pleins à partir de
        maintenant (utilisé quand l'utilisateur change l'intervalle ou la fréquence).
        reanchor=False : conserve le cycle ancré sur la dernière date d'arrosage
        (setup, redémarrage, post-arrosage).
        """
        if self._auto_unsub is not None:
            self._auto_unsub()
            self._auto_unsub = None

        if not self._config.auto_irrigation_enabled:
            return

        time_str = self._config.irrigation_time
        try:
            parts = time_str.split(":")
            hour, minute = int(parts[0]), int(parts[1])
        except (ValueError, AttributeError, IndexError):
            hour, minute = 6, 0

        now = dt_util.now()
        next_trigger = self._compute_next_trigger(now, hour, minute, reanchor)

        if reanchor:
            # Persiste la date cible pour qu'elle survive aux redémarrages.
            self._config.set_next_watering_override(next_trigger.isoformat())

        self.next_trigger = next_trigger
        self._auto_unsub = async_track_point_in_time(
            self._hass, self._handle_auto_irrigation, next_trigger
        )
        _LOGGER.debug("Arrosage automatique planifié à %s", next_trigger)

    def _compute_next_trigger(
        self, now: datetime, hour: int, minute: int, reanchor: bool = False
    ) -> datetime:
        """Calcule la prochaine date de déclenchement selon le mode de fréquence."""
        if self._config.watering_frequency == WATERING_FREQUENCY_INTERVAL:
            interval_days = self._config.watering_interval_days

            if reanchor:
                # Vise N jours pleins après maintenant, à l'heure du créneau. Si le
                # créneau du jour cible est déjà passé, décale d'un jour pour que la
                # durée restante affichée corresponde à l'intervalle choisi.
                target = now + timedelta(days=interval_days)
                next_trigger = target.replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )
                if next_trigger < target:
                    next_trigger += timedelta(days=1)
                return next_trigger

            # Date cible persistée par un ré-ancrage antérieur : prioritaire tant
            # qu'elle est future, à l'heure du créneau courant. Survit aux redémarrages.
            override = self._config.next_watering_override
            if override:
                override_dt = datetime.fromisoformat(override).replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )
                if override_dt > now:
                    return override_dt

            # Ancrage sur la dernière date d'arrosage (ou aujourd'hui à défaut) +
            # interval_days, à l'heure du créneau.
            last_date_str = self._config.last_auto_watering_date
            anchor = date.fromisoformat(last_date_str) if last_date_str else now.date()
            next_date = anchor + timedelta(days=interval_days)
            next_trigger = now.replace(
                year=next_date.year,
                month=next_date.month,
                day=next_date.day,
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0,
            )
            if next_trigger > now:
                return next_trigger
        # Mode daily, ou date d'intervalle déjà passée : prochain créneau horaire.
        next_trigger = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_trigger <= now:
            next_trigger += timedelta(days=1)
        return next_trigger

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _handle_midnight(self, _now: datetime) -> None:
        """Transfère le besoin journalier résiduel au bilan cumulé."""
        try:
            await self._on_midnight()
        except Exception as exc:
            _LOGGER.error("Erreur lors du transfert de minuit : %s", exc)
        finally:
            self._schedule_midnight()

    async def _handle_auto_irrigation(self, _now: datetime) -> None:
        """Vérifie les conditions de fréquence puis déclenche l'arrosage."""
        if self._config.watering_frequency == WATERING_FREQUENCY_INTERVAL:
            interval_days = self._config.watering_interval_days
            today = dt_util.now().date()
            last_date_str = self._config.last_auto_watering_date
            if last_date_str:
                days_since = (today - date.fromisoformat(last_date_str)).days
                if days_since < interval_days:
                    _LOGGER.debug(
                        "Arrosage auto ignoré — intervalle %dj, dernier il y a %dj.",
                        interval_days,
                        days_since,
                    )
                    self.reschedule_auto_irrigation()
                    return

        await self._on_trigger(dt_util.now().date().isoformat())
        self.reschedule_auto_irrigation()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _schedule_midnight(self) -> None:
        now = dt_util.now()
        next_midnight = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=5, microsecond=0
        )
        self._midnight_unsub = async_track_point_in_time(
            self._hass, self._handle_midnight, next_midnight
        )
