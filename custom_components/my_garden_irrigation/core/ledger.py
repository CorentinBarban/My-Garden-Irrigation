"""Fonctions pures de comptabilité hydrique — My Garden Irrigation.

Aucune dépendance envers homeassistant.* : testables directement avec pytest.
"""
from __future__ import annotations


def allocate_volume_by_surface(
    total_volume: float,
    surfaces: dict[str, float],
) -> dict[str, float]:
    """Répartit un volume d'eau total entre cultures proportionnellement à leur surface.

    Volume attribué = Volume Global × (Surface culture / Surface totale)

    Args:
        total_volume: Volume total distribué par la vanne globale (litres).
        surfaces: Mapping crop_id → surface (m²).

    Returns:
        Mapping crop_id → volume attribué (litres). Vide si total_surface == 0.
    """
    total_surface = sum(surfaces.values())
    if total_surface <= 0 or total_volume <= 0:
        return {}
    return {
        crop_id: total_volume * (surface / total_surface)
        for crop_id, surface in surfaces.items()
    }


def midnight_transfer(
    cumulative_need: dict[str, float],
    daily_needs: dict[str, float],
) -> dict[str, float]:
    """Transfère le besoin journalier résiduel vers le bilan hydrique cumulé.

    Appelé à minuit : le besoin non satisfait de la journée s'accumule.
    Opère sur des copies — ne mute pas les arguments.

    Args:
        cumulative_need: Bilan cumulé existant (crop_id → litres).
        daily_needs: Besoin journalier par culture (crop_id → litres).

    Returns:
        Nouveau bilan cumulé mis à jour.
    """
    result = dict(cumulative_need)
    for crop_id, daily in daily_needs.items():
        result[crop_id] = result.get(crop_id, 0.0) + daily
    return result
