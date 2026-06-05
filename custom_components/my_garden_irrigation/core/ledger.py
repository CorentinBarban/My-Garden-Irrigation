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
    daily_balance: dict[str, float],
) -> dict[str, float]:
    """Ajoute le bilan hydrique signé du jour au bilan cumulé, par culture (ADR-028).

    Le bilan du jour (apport ETo − pluie efficace, signé) est fourni par
    DailyWaterLedger.replay() ; l'arrosage en est exclu car déjà imputé en temps
    réel par apply_watering_volumes. Le résultat n'est **pas planché** : un cumulé
    négatif représente une réserve d'eau reportée. Opère sur une copie : les
    dictionnaires d'entrée ne sont pas mutés.

    Args:
        cumulative_need: Bilan cumulé signé existant (crop_id → litres).
        daily_balance: Bilan signé du jour par culture (crop_id → litres).

    Returns:
        Nouveau bilan cumulé signé.
    """
    result = dict(cumulative_need)
    for crop_id, daily in daily_balance.items():
        result[crop_id] = result.get(crop_id, 0.0) + daily
    return result


class MidnightClosureOrchestrator:
    """Applique la clôture comptable de minuit (ADR-023).

    Pattern Template Method : l'ordre des étapes est fixé et non substituable.
    L'appelant (coordinator) reste responsable de la persistance et du refresh HA.

    Usage :
        orch = MidnightClosureOrchestrator()
        new_cumulative = orch.execute(cumulative, daily_balance)
        config.apply_midnight_result(new_cumulative)
    """

    def execute(
        self,
        cumulative_need: dict[str, float],
        daily_balance: dict[str, float],
    ) -> dict[str, float]:
        """Retourne le bilan cumulé signé après ajout du bilan du jour. Sans effet de bord."""
        return midnight_transfer(cumulative_need, daily_balance)
