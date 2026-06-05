"""Calculs agronomiques FAO Paper 56 — ETc = Kc × ETo.

Fonctions pures, sans état, sans dépendance externe.
Testables directement avec pytest standard.
"""
from __future__ import annotations

from .models import CropResult, IrrigationData

EFFECTIVE_RAINFALL_FACTOR = 0.8
"""Part des précipitations brutes retenue par le sol (ADR-007)."""


def compute_surface_m2(nb_plants: int, density: float) -> float:
    """Surface occupée en m² : nb_plants ÷ densité (plants/m²).

    ADR-003 : le nombre de plants pilote le calcul, la surface est dérivée.
    """
    return nb_plants / density


def compute_etc_liters(kc: float, eto_mm: float, surface_m2: float) -> float:
    """Besoin en eau journalier brut en litres.

    ETc (mm/j) = Kc × ETo (mm/j)
    ETc (L/j)  = ETc (mm/j) × surface (m²)   ← 1 mm sur 1 m² = 1 L
    """
    return kc * eto_mm * surface_m2


def compute_effective_rainfall_mm(precipitation_mm: float) -> float:
    """Pluie efficace (mm) = précipitations brutes × 0,8 (ADR-007).

    Le facteur 0,8 exclut le ruissellement et l'évaporation directe.
    """
    return precipitation_mm * EFFECTIVE_RAINFALL_FACTOR


def compute_balance_liters(etc_liters: float, effective_rainfall_mm: float, surface_m2: float) -> float:
    """Bilan hydrique signé du jour en litres (ADR-028).

    Bilan (mm) = ETc_mm − Pluie Efficace_mm   (peut être négatif = surplus de pluie)
    Converti en litres : × surface_m2

    Contrairement à compute_net_liters, ce bilan n'est PAS planché : un surplus de
    pluie produit une valeur négative qui alimente la réserve hydrique cumulée.
    """
    etc_mm = etc_liters / surface_m2 if surface_m2 else 0.0
    return (etc_mm - effective_rainfall_mm) * surface_m2


def compute_net_liters(etc_liters: float, effective_rainfall_mm: float, surface_m2: float) -> float:
    """Besoin net en litres après déduction de la pluie efficace (ADR-007).

    Besoin Net (mm) = max(0, ETc_mm − Pluie Efficace_mm)
    Converti en litres : × surface_m2

    Valeur d'affichage plancher 0 ; la version signée pour la comptabilité est
    fournie par compute_balance_liters.
    """
    return max(0.0, compute_balance_liters(etc_liters, effective_rainfall_mm, surface_m2))


def compute_crop_result(
    *,
    nb_plants: int,
    density: float,
    kc: float,
    eto_mm: float,
    precipitation_mm: float,
    crop_type: str,
    stage: str,
    watering_applied_today_liters: float = 0.0,
) -> CropResult:
    """Calcule tous les indicateurs pour une culture en un appel.

    Paramètres nommés obligatoires pour éviter les erreurs d'ordre.
    """
    surface_m2 = compute_surface_m2(nb_plants, density)
    etc_liters = compute_etc_liters(kc, eto_mm, surface_m2)
    effective_rainfall_mm = compute_effective_rainfall_mm(precipitation_mm)
    balance_liters = compute_balance_liters(etc_liters, effective_rainfall_mm, surface_m2)
    net_liters = max(0.0, balance_liters)
    daily_need_liters = net_liters
    return CropResult(
        liters=round(net_liters, 1),
        etc_liters=round(etc_liters, 1),
        effective_rainfall_mm=round(effective_rainfall_mm, 2),
        surface_m2=round(surface_m2, 2),
        kc=kc,
        eto_mm=eto_mm,
        liters_per_plant=round(net_liters / nb_plants, 2) if nb_plants else 0.0,
        weekly_projection_l=round(net_liters * 7, 1),
        crop_type=crop_type,
        stage=stage,
        nb_plants=nb_plants,
        density=density,
        watering_applied_today_liters=round(watering_applied_today_liters, 1),
        daily_need_liters=round(daily_need_liters, 1),
        daily_balance_liters=round(balance_liters, 1),
    )


def compute_irrigation_data(
    crops: list[dict],
    kc_data: dict,
    eto_mm: float,
    precipitation_mm: float = 0.0,
    *,
    kc_getter,  # callable(kc_data, crop_type, stage) -> float | None
    watering_applied_today: dict[str, float] | None = None,
    cumulative_need: dict[str, float] | None = None,
) -> IrrigationData:
    """Calcule IrrigationData pour toutes les cultures d'un potager.

    Découplé de tout I/O : reçoit les données déjà chargées.
    Appelé par le coordinator, testable sans HA.

    Args:
        crops:                   liste de dicts (CONF_CROP_ID, CONF_CROP_TYPE, CONF_STAGE,
                                 CONF_NB_PLANTS, CONF_DENSITY) — structure Options HA
        kc_data:                 dict brut du kc_fao56.json
        eto_mm:                  valeur ETo du jour (mm/j)
        precipitation_mm:        précipitations brutes du jour (mm) — ADR-007
        kc_getter:               fonction d'accès au Kc (injectable pour les tests)
        watering_applied_today:  crop_id → litres arrosés aujourd'hui (ADR-009)
        cumulative_need:         crop_id → bilan cumulé persisté (ADR-008)
    """
    from .kc_data import get_kc as _default_getter  # import local pour éviter la circularité

    _get_kc = kc_getter if kc_getter is not None else _default_getter
    _watering = watering_applied_today or {}
    _cumulative = cumulative_need or {}

    results: dict[str, CropResult] = {}
    total = 0.0
    total_daily_need = 0.0
    total_daily_balance = 0.0

    for crop in crops:
        crop_id: str = crop["crop_id"]
        crop_type: str = crop["crop_type"]
        stage: str = crop["stage"]
        nb_plants: int = crop["nb_plants"]
        density: float = crop["density"]

        kc = _get_kc(kc_data, crop_type, stage)
        if kc is None:
            continue

        result = compute_crop_result(
            nb_plants=nb_plants,
            density=density,
            kc=kc,
            eto_mm=eto_mm,
            precipitation_mm=precipitation_mm,
            crop_type=crop_type,
            stage=stage,
            watering_applied_today_liters=_watering.get(crop_id, 0.0),
        )
        results[crop_id] = result
        total += result.liters
        total_daily_need += result.daily_need_liters
        total_daily_balance += result.daily_balance_liters

    return IrrigationData(
        crops=results,
        total_liters=round(total, 1),
        total_daily_need_liters=round(total_daily_need, 1),
        total_daily_balance_liters=round(total_daily_balance, 1),
        eto_mm=eto_mm,
        precipitation_mm=precipitation_mm,
        cumulative_need=dict(_cumulative),
    )
