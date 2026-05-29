"""Coordinateur de données — My Garden Irrigation (ADR-005).

Pattern : DataUpdateCoordinator sans SCAN_INTERVAL.
La mise à jour est déclenchée par les changements d'état de l'entité ETo
(async_track_state_change_event), et non par un polling périodique.

Ce module est la couture entre Home Assistant (I/O, états, événements)
et le package core/ (logique métier pure).
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_CROPS,
    CONF_ETO_ENTITY_ID,
    DOMAIN,
    MAX_REASONABLE_SURFACE_M2,
)
from .core.calculations import compute_irrigation_data
from .core.kc_data import get_kc
from .core.models import IrrigationData
from .kc_loader import async_load_kc_data

_LOGGER = logging.getLogger(__name__)


class IrrigationCoordinator(DataUpdateCoordinator[IrrigationData]):
    """Calcule les besoins en eau de toutes les cultures configurées.

    Délègue la logique métier à core.calculations.compute_irrigation_data.
    Gère uniquement les interactions HA : lecture d'états, événements, I/O async.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN)
        self._entry = entry
        self._kc_data: dict = {}
        self._unsubscribe_eto: callable | None = None

    # ------------------------------------------------------------------
    # Propriétés HA
    # ------------------------------------------------------------------

    @property
    def eto_entity_id(self) -> str:
        return self._entry.options[CONF_ETO_ENTITY_ID]

    @property
    def crops(self) -> list[dict]:
        return self._entry.options.get(CONF_CROPS, [])

    # ------------------------------------------------------------------
    # Cycle de vie
    # ------------------------------------------------------------------

    async def async_setup(self) -> None:
        """Charge les données Kc et s'abonne aux changements de l'entité ETo."""
        self._kc_data = await async_load_kc_data(self.hass)
        self._subscribe_eto()
        await self.async_config_entry_first_refresh()

    def _subscribe_eto(self) -> None:
        if self._unsubscribe_eto is not None:
            self._unsubscribe_eto()

        @callback
        def _on_eto_state_changed(_event) -> None:
            self.hass.async_create_task(self.async_request_refresh())

        self._unsubscribe_eto = async_track_state_change_event(
            self.hass, self.eto_entity_id, _on_eto_state_changed
        )
        _LOGGER.debug("Abonné aux changements de %s", self.eto_entity_id)

    def async_unsubscribe(self) -> None:
        """Désabonne l'écouteur ETo (appelé lors du déchargement de l'entrée)."""
        if self._unsubscribe_eto is not None:
            self._unsubscribe_eto()
            self._unsubscribe_eto = None

    # ------------------------------------------------------------------
    # Calcul principal — pont HA → core/
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> IrrigationData:
        """Lit l'ETo depuis HA, délègue le calcul ETc à core/calculations."""
        eto_state = self.hass.states.get(self.eto_entity_id)

        if eto_state is None or eto_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            raise UpdateFailed(
                f"L'entité ETo '{self.eto_entity_id}' est indisponible."
            )

        try:
            eto_mm = float(eto_state.state)
        except ValueError as exc:
            raise UpdateFailed(
                f"Valeur ETo invalide : {eto_state.state!r}"
            ) from exc

        self._warn_unreasonable_surfaces(eto_mm)

        return compute_irrigation_data(
            crops=self.crops,
            kc_data=self._kc_data,
            eto_mm=eto_mm,
            kc_getter=get_kc,
        )

    def _warn_unreasonable_surfaces(self, _eto_mm: float) -> None:
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
