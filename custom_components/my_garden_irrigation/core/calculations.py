"""Calculs agronomiques FAO Paper 56 — ETc = Kc × ETo.

Fonctions pures, sans état, sans dépendance externe.
Testables directement avec pytest standard.
"""
from __future__ import annotations

from .models import CropResult, IrrigationData


def compute_surface_m2(nb_plants: int, density: float) -> float:
    """Surface occupée en m² : nb_plants ÷ densité (plants/m²).

    ADR-003 : le nombre de plants pilote le calcul, la surface est dérivée.
    """
    return nb_plants / density


def compute_etc_liters(kc: float, eto_mm: float, surface_m2: float) -> float:
    """Besoin en eau journalier en litres.

    ETc (mm/j) = Kc × ETo (mm/j)
    ETc (L/j)  = ETc (mm/j) × surface (m²)   ← 1 mm sur 1 m² = 1 L
    """
    return kc * eto_mm * surface_m2


def compute_crop_result(
    *,
    nb_plants: int,
    density: float,
    kc: float,
    eto_mm: float,
    crop_type: str,
    stage: str,
) -> CropResult:
    """Calcule tous les indicateurs pour une culture en un appel.

    Paramètres nommés obligatoires pour éviter les erreurs d'ordre.
    """
    surface_m2 = compute_surface_m2(nb_plants, density)
    liters = compute_etc_liters(kc, eto_mm, surface_m2)
    return CropResult(
        liters=round(liters, 1),
        surface_m2=round(surface_m2, 2),
        kc=kc,
        eto_mm=eto_mm,
        liters_per_plant=round(liters / nb_plants, 2) if nb_plants else 0.0,
        weekly_projection_l=round(liters * 7, 1),
        crop_type=crop_type,
        stage=stage,
        nb_plants=nb_plants,
        density=density,
    )


def compute_irrigation_data(
    crops: list[dict],
    kc_data: dict,
    eto_mm: float,
    *,
    kc_getter,  # callable(kc_data, crop_type, stage) -> float | None
) -> IrrigationData:
    """Calcule IrrigationData pour toutes les cultures d'un potager.

    Découplé de tout I/O : reçoit les données déjà chargées.
    Appelé par le coordinator, testable sans HA.

    Args:
        crops:      liste de dicts (CONF_CROP_ID, CONF_CROP_TYPE, CONF_STAGE,
                    CONF_NB_PLANTS, CONF_DENSITY) — structure Options HA
        kc_data:    dict brut du kc_fao56.json
        eto_mm:     valeur ETo du jour (mm/j)
        kc_getter:  fonction d'accès au Kc (injectable pour les tests)
    """
    from .kc_data import get_kc as _default_getter  # import local pour éviter la circularité

    _get_kc = kc_getter if kc_getter is not None else _default_getter

    results: dict[str, CropResult] = {}
    total = 0.0

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
            crop_type=crop_type,
            stage=stage,
        )
        results[crop_id] = result
        total += result.liters

    return IrrigationData(crops=results, total_liters=round(total, 1), eto_mm=eto_mm)
