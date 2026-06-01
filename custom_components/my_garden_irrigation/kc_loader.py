"""Chargement des coefficients culturaux Kc (ADR-001).

Charge le fichier JSON embarqué (FAO-56) et met le résultat en cache dans
hass.data pour éviter des lectures disque répétées.
"""
from __future__ import annotations

import json
from pathlib import Path

from homeassistant.core import HomeAssistant

from .const import KC_CACHE_KEY

_DATA_PATH = Path(__file__).parent / "data" / "kc_fao56.json"


def _read_data() -> dict:
    with _DATA_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


async def async_load_kc_data(hass: HomeAssistant) -> dict:
    """Retourne les données Kc, depuis le cache hass.data ou en les chargeant."""
    if KC_CACHE_KEY in hass.data:
        return hass.data[KC_CACHE_KEY]

    data: dict = await hass.async_add_executor_job(_read_data)
    hass.data[KC_CACHE_KEY] = data
    return data


def invalidate_kc_cache(hass: HomeAssistant) -> None:
    """Invalide le cache Kc (utile pour les tests ou un rechargement forcé)."""
    hass.data.pop(KC_CACHE_KEY, None)
