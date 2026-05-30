"""Coordinateur de données — My Garden Irrigation.

L'ETo est récupéré depuis l'API Open-Meteo (gratuite, sans clé API) en utilisant
la latitude/longitude configurée dans Home Assistant (hass.config).
La mise à jour se fait toutes les heures via SCAN_INTERVAL.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_CROPS,
    DOMAIN,
    MAX_REASONABLE_SURFACE_M2,
    OPEN_METEO_TIMEOUT,
    OPEN_METEO_URL,
)
from .core.calculations import compute_irrigation_data
from .core.kc_data import get_kc
from .core.models import IrrigationData
from .kc_loader import async_load_kc_data

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(hours=1)


class IrrigationCoordinator(DataUpdateCoordinator[IrrigationData]):
    """Calcule les besoins en eau de toutes les cultures configurées.

    L'ETo est obtenu depuis Open-Meteo à partir des coordonnées HA.
    Délègue la logique métier à core.calculations.compute_irrigation_data.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self._entry = entry
        self._kc_data: dict = {}

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
        """Charge les données Kc et effectue le premier calcul."""
        self._kc_data = await async_load_kc_data(self.hass)
        await self.async_config_entry_first_refresh()

    # ------------------------------------------------------------------
    # Calcul principal — pont HA → core/
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> IrrigationData:
        """Récupère l'ETo depuis Open-Meteo et calcule les besoins en eau."""
        eto_mm = await self._fetch_eto()
        self._warn_unreasonable_surfaces(eto_mm)
        return compute_irrigation_data(
            crops=self.crops,
            kc_data=self._kc_data,
            eto_mm=eto_mm,
            kc_getter=get_kc,
        )

    async def _fetch_eto(self) -> float:
        """Appelle Open-Meteo pour obtenir l'ETo du jour (mm/j) via les coordonnées HA."""
        lat = self.hass.config.latitude
        lon = self.hass.config.longitude
        _LOGGER.debug("Récupération ETo Open-Meteo (lat=%s, lon=%s)", lat, lon)

        session = async_get_clientsession(self.hass)
        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": "et0_fao_evapotranspiration",
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
            eto_mm = data["daily"]["et0_fao_evapotranspiration"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise UpdateFailed(
                f"Réponse Open-Meteo invalide : {data!r}"
            ) from exc

        if eto_mm is None:
            raise UpdateFailed("L'ETo retourné par Open-Meteo est None.")

        _LOGGER.debug("ETo Open-Meteo = %.2f mm/j", float(eto_mm))
        return float(eto_mm)

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
