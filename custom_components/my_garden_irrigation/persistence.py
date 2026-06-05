"""Gestion de la persistance HA — My Garden Irrigation.

Wrapper fin autour de homeassistant.helpers.storage.Store.
Toute la logique de sérialisation/désérialisation vit dans RuntimeConfigState
(config_state.py) — ce module ne fait que le I/O.
"""
from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)


class PersistenceManager:
    """Encapsule le Store HA : charge et sauvegarde le bilan hydrique.

    Module d'I/O quasi-muet : la journalisation des échecs de sauvegarde vit
    dans le coordinateur (point d'entrée unique de la persistance) ; ici, seuls
    des DEBUG tracent le flux. Le logger d'instance est injecté (ADR-012).
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        logger: logging.Logger | logging.LoggerAdapter = _LOGGER,
    ) -> None:
        self._log = logger
        self._store = Store(
            hass,
            STORAGE_VERSION,
            f"{DOMAIN}.{entry_id}.water_balance",
        )

    async def async_load(self) -> dict:
        """Charge les données depuis le Store HA. Retourne {} si rien n'est stocké."""
        data = await self._store.async_load() or {}
        self._log.debug("État chargé depuis le Store (%d clés).", len(data))
        return data

    async def async_save(self, data: dict) -> None:
        """Sauvegarde les données dans le Store HA."""
        await self._store.async_save(data)
        self._log.debug("État sauvegardé dans le Store (%d clés).", len(data))
