"""Suivi de la vanne globale — My Garden Irrigation (ADR-009).

Écoute les changements d'état de la vanne globale, calcule le volume
distribué à la fermeture et le ventile par culture via core.ledger.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .core.ledger import allocate_volume_by_surface

if TYPE_CHECKING:
    from .coordinator import IrrigationCoordinator

_LOGGER = logging.getLogger(__name__)

_OPEN_STATES = {"on", "open"}
_CLOSED_STATES = {"off", "closed"}


class ValveTracker:
    """Écoute la vanne globale et impute les volumes distribués au coordinateur."""

    def __init__(self, hass: HomeAssistant, coordinator: IrrigationCoordinator) -> None:
        self._hass = hass
        self._coordinator = coordinator

    def setup(self) -> Callable:
        """Inscrit le listener et restaure l'état de la vanne.

        Returns:
            Callable de nettoyage à passer à entry.async_on_unload().
        """
        self._hass.async_create_task(self._restore_valve_state())

        valve_id: str | None = self._coordinator.valve_entity_id
        if not valve_id:
            return lambda: None

        unsub = async_track_state_change_event(
            self._hass, [valve_id], self._handle_valve_state_change
        )
        _LOGGER.debug("Écoute de la vanne globale : %s", valve_id)

        @callback
        def _cleanup() -> None:
            unsub()

        return _cleanup

    async def _restore_valve_state(self) -> None:
        """Réconcilie _valve_open_time avec l'état réel de la vanne après redémarrage."""
        valve_id: str | None = self._coordinator.valve_entity_id
        if not valve_id:
            return
        state = self._hass.states.get(valve_id)
        if state is None:
            return

        current = state.state
        if current in _OPEN_STATES:
            if self._coordinator.get_valve_open_time() is None:
                self._coordinator.set_valve_open_time(dt_util.utcnow())
                _LOGGER.warning(
                    "Vanne %s ouverte au démarrage sans heure d'ouverture connue — "
                    "décompte du volume depuis maintenant.",
                    valve_id,
                )
        elif current in _CLOSED_STATES and self._coordinator.get_valve_open_time() is not None:
            _LOGGER.info(
                "Vanne %s fermée pendant le redémarrage — comptabilisation du volume.",
                valve_id,
            )
            await self._handle_valve_close()

    @callback
    def _handle_valve_state_change(self, event: Event) -> None:
        """Détecte l'ouverture/fermeture et délègue au coordinateur."""
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")
        if old_state is None or new_state is None:
            return

        old = old_state.state
        new = new_state.state

        if old in _CLOSED_STATES and new in _OPEN_STATES:
            self._coordinator.set_valve_open_time(dt_util.utcnow())
            _LOGGER.debug("Vanne ouverte à %s", self._coordinator.get_valve_open_time())

        elif old in _OPEN_STATES and new in _CLOSED_STATES:
            self._hass.async_create_task(self._handle_valve_close())

    async def _handle_valve_close(self) -> None:
        """Calcule le volume distribué, le ventile par culture et met à jour le coordinateur."""
        open_time = self._coordinator.get_valve_open_time()
        if open_time is None:
            return

        flow_rate = self._coordinator.flow_rate
        duration_s = (dt_util.utcnow() - open_time).total_seconds()
        total_volume = (duration_s / 3600.0) * flow_rate
        self._coordinator.set_valve_open_time(None)

        _LOGGER.debug(
            "Vanne fermée — durée=%.0fs, débit=%.1fL/h → volume distribué=%.1fL",
            duration_s,
            flow_rate,
            total_volume,
        )

        if total_volume > 0:
            surfaces = self._coordinator.get_crop_surfaces()
            volumes = allocate_volume_by_surface(total_volume, surfaces)
            await self._coordinator.apply_watering_volumes(volumes)
        else:
            await self._coordinator.apply_watering_volumes({})
