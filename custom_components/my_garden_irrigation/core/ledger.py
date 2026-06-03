"""Fonctions pures de comptabilité hydrique — My Garden Irrigation.

Aucune dépendance envers homeassistant.* : testables directement avec pytest.

Modules associés :
  core/strategies.py — ADR-024 Strategy (calcul volume)
  core/journal.py    — ADR-026 Command (journal transactions)
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
    watering_applied_today: dict[str, float] | None = None,
) -> dict[str, float]:
    """Transfère le besoin journalier résiduel vers le bilan hydrique cumulé.

    Applique la Règle 1 : soustrait les arrosages du jour avant d'accumuler,
    avec plancher à 0 (le sol ne crédite pas d'eau négative).
    Opère sur des copies — ne mute pas les arguments.

    Args:
        cumulative_need: Bilan cumulé existant (crop_id → litres).
        daily_needs: Besoin journalier par culture (crop_id → litres).
        watering_applied_today: Volumes arrosés dans la journée (crop_id → litres).
            Si None, aucune déduction n'est appliquée (rétrocompatibilité).

    Returns:
        Nouveau bilan cumulé mis à jour.
    """
    _applied = watering_applied_today or {}
    result = dict(cumulative_need)
    for crop_id, daily in daily_needs.items():
        applied = _applied.get(crop_id, 0.0)
        result[crop_id] = max(0.0, result.get(crop_id, 0.0) + daily - applied)
    return result


class MidnightClosureOrchestrator:
    """Encode l'invariant algorithmique de la clôture comptable de minuit (ADR-023).

    Pattern Template Method : l'ordre des étapes est fixé et non substituable.
    L'appelant (coordinator) reste responsable de la persistance et du refresh HA.

    Usage :
        orch = MidnightClosureOrchestrator()
        new_cumulative = orch.execute(cumulative, daily_needs, watering_today)
        config.apply_midnight_result(new_cumulative)

    Testable sans aucun mock HA :
        result = MidnightClosureOrchestrator().execute({"c1": 5.0}, {"c1": 3.0})
        assert result["c1"] == 8.0
    """

    def execute(
        self,
        cumulative_need: dict[str, float],
        daily_needs: dict[str, float],
        watering_applied_today: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """Étape 2 de la clôture : équilibrage absolu selon la Règle 1.

        Retourne le nouveau bilan cumulé. N'a aucun effet de bord.
        """
        return midnight_transfer(cumulative_need, daily_needs, watering_applied_today)
