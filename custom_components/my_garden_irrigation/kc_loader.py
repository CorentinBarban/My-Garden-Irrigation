"""Chargement des coefficients culturaux Kc (ADR-001).

Stratégie : téléchargement depuis GitHub au démarrage, fallback sur le JSON
embarqué si le réseau est indisponible. Résultat mis en cache dans hass.data.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import KC_CACHE_KEY, KC_FETCH_TIMEOUT, KC_REMOTE_URL

_LOGGER = logging.getLogger(__name__)
_FALLBACK_PATH = Path(__file__).parent / "data" / "kc_fao56.json"


def _read_fallback() -> dict:
    with _FALLBACK_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


async def async_load_kc_data(hass: HomeAssistant) -> dict:
    """Retourne les données Kc, depuis le cache hass.data ou en les chargeant."""
    if KC_CACHE_KEY in hass.data:
        return hass.data[KC_CACHE_KEY]

    session = async_get_clientsession(hass)
    try:
        async with session.get(KC_REMOTE_URL, timeout=KC_FETCH_TIMEOUT) as resp:
            resp.raise_for_status()
            data: dict = await resp.json(content_type=None)
            _LOGGER.debug(
                "Données Kc chargées depuis GitHub (version %s)", data.get("version")
            )
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning(
            "Impossible de récupérer les données Kc depuis GitHub (%s) — "
            "utilisation du fichier embarqué.",
            exc,
        )
        data = await hass.async_add_executor_job(_read_fallback)

    hass.data[KC_CACHE_KEY] = data
    return data


def invalidate_kc_cache(hass: HomeAssistant) -> None:
    """Invalide le cache Kc (utile pour les tests ou un rechargement forcé)."""
    hass.data.pop(KC_CACHE_KEY, None)
