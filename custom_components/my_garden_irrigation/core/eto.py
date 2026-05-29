"""Calcul de l'évapotranspiration de référence ETo via PyETo (FAO Paper 56).

Ce module est pur Python — aucune dépendance HA.
Il expose deux méthodes de calcul issues du FAO Paper 56 :

  - Penman-Monteith (recommandée) : méthode complète, nécessite T, HR, vent,
    ensoleillement, latitude, altitude.
  - Hargreaves-Samani (simplifiée) : ne nécessite que T min/max et la latitude.
    Moins précise mais utile quand les données météo sont incomplètes.

Contexte (ADR-002) :
  En v1, l'ETo est fournie par une entité HA existante (Open-Meteo…).
  Ce module prépare la v2 où l'intégration calculera l'ETo elle-même
  à partir des sensors météo individuels (station locale, etc.).
"""
from __future__ import annotations

from datetime import date

from .._pyeto import convert, fao

from .models import EToInput


def compute_eto_penman_monteith(inputs: EToInput, day: date) -> float:
    """ETo Penman-Monteith FAO-56 (mm/jour).

    Implémentation complète selon FAO Irrigation and Drainage Paper 56,
    équation 6 (Allen et al., 1998).

    Args:
        inputs: données météorologiques journalières (voir EToInput)
        day:    date du calcul (pour la position solaire)

    Returns:
        ETo en mm/jour, arrondi à 2 décimales.
    """
    lat_rad = convert.deg2rad(inputs.latitude)
    doy = day.timetuple().tm_yday  # day of year [1-366]

    # --- Pression atmosphérique et psychrométrie ---
    atm_pres = fao.atm_pressure(inputs.altitude)  # kPa
    psy = fao.psy_const(atm_pres)             # kPa/°C

    # --- Pression de vapeur ---
    svp_min = fao.svp_from_t(inputs.t_min)   # kPa
    svp_max = fao.svp_from_t(inputs.t_max)   # kPa
    svp = fao.mean_svp(svp_min, svp_max)     # kPa

    avp = fao.avp_from_rhmin_rhmax(
        svp_min, svp_max, inputs.humidity_min, inputs.humidity_max
    )  # kPa

    delta = fao.delta_svp(inputs.t_mean)     # kPa/°C

    # --- Rayonnement solaire ---
    ird = fao.inv_rel_dist_earth_sun(doy)
    sol_dec = fao.sol_dec(doy)               # radians
    sha = fao.sunset_hour_angle(lat_rad, sol_dec)  # radians

    et_rad = fao.et_rad(lat_rad, sol_dec, sha, ird)  # MJ m-2 j-1
    cs_rad = fao.cs_rad(inputs.altitude, et_rad)      # MJ m-2 j-1

    dl_hours = fao.daylight_hours(sha)       # heures de clarté théorique
    sol_rad = fao.sol_rad_from_sun_hours(
        dl_hours, inputs.sunshine_hours, et_rad
    )  # MJ m-2 j-1

    # --- Rayonnement net ---
    ns_rad = fao.net_in_sol_rad(sol_rad)     # MJ m-2 j-1
    nl_rad = fao.net_out_lw_rad(
        convert.celsius2kelvin(inputs.t_min),
        convert.celsius2kelvin(inputs.t_max),
        sol_rad,
        cs_rad,
        avp,
    )  # MJ m-2 j-1
    net_r = fao.net_rad(ns_rad, nl_rad)     # MJ m-2 j-1

    # --- ETo Penman-Monteith ---
    eto = fao.fao56_penman_monteith(
        net_r,
        convert.celsius2kelvin(inputs.t_mean),  # API 0.2.0 prend des Kelvin
        inputs.wind_speed_2m,
        svp,
        avp,
        delta,
        psy,
    )
    return round(eto, 2)


def compute_eto_hargreaves(
    t_min: float,
    t_max: float,
    latitude: float,
    day: date,
) -> float:
    """ETo Hargreaves-Samani (mm/jour).

    Méthode simplifiée (FAO Paper 56, équation 52) : ne nécessite que
    les températures min/max et la localisation géographique.

    À utiliser quand les données d'humidité, de vent ou d'ensoleillement
    ne sont pas disponibles. Précision moindre que Penman-Monteith.

    Args:
        t_min:     température minimale journalière (°C)
        t_max:     température maximale journalière (°C)
        latitude:  latitude en degrés décimaux
        day:       date du calcul

    Returns:
        ETo en mm/jour, arrondi à 2 décimales.
    """
    lat_rad = convert.deg2rad(latitude)
    doy = day.timetuple().tm_yday

    ird = fao.inv_rel_dist_earth_sun(doy)
    sol_dec = fao.sol_dec(doy)
    sha = fao.sunset_hour_angle(lat_rad, sol_dec)
    et_rad = fao.et_rad(lat_rad, sol_dec, sha, ird)  # MJ m-2 j-1

    tmean = (t_min + t_max) / 2.0
    return round(fao.hargreaves(t_min, t_max, tmean, et_rad), 2)
