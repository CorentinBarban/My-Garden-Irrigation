"""Gestion de la persistance HA — My Garden Irrigation.

Wrapper fin autour de homeassistant.helpers.storage.Store.
Toute la logique de sérialisation/désérialisation vit dans RuntimeConfigState
(config_state.py) — ce module ne fait que le I/O.
"""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_VERSION


class PersistenceManager:
    """Encapsule le Store HA : charge et sauvegarde le bilan hydrique."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store = Store(
            hass,
            STORAGE_VERSION,
            f"{DOMAIN}.{entry_id}.water_balance",
        )

    async def async_load(self) -> dict:
        """Charge les données depuis le Store HA. Retourne {} si rien n'est stocké."""
        return await self._store.async_load() or {}

    async def async_save(self, data: dict) -> None:
        """Sauvegarde les données dans le Store HA."""
        await self._store.async_save(data)
