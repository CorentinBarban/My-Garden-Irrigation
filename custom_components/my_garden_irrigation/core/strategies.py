"""ADR-028 — Calcul du volume d'arrosage : décision toujours inclusive.

Aucune dépendance homeassistant.* — testable directement avec pytest.

Remplace ADR-024 (distinction matin/soir) : depuis que le bilan hydrique est signé
et que l'arrosage n'est imputé qu'une fois (apply_watering_volumes), arroser le besoin
du jour à n'importe quelle heure est cohérent — le pré-paiement fait simplement passer
le cumulé sous zéro (réserve), que la clôture de minuit ré-équilibre.
"""
from __future__ import annotations

from typing import Protocol


class WateringVolumeStrategy(Protocol):
    """Protocole de calcul du volume d'arrosage cible."""

    def calculate_target_volume(
        self, cumulative_need: float, daily_balance: float
    ) -> float: ...


class InclusiveWateringStrategy:
    """Arrosage = dette historique + bilan net du jour (Règle 2 généralisée).

    Inclut le besoin du jour pour anticiper la clôture de minuit, à toute heure.
    Un bilan du jour négatif (surplus de pluie) réduit le volume cible — voire
    l'annule si la réserve cumulée couvre le besoin.
    """

    def calculate_target_volume(self, cumulative_need: float, daily_balance: float) -> float:
        return cumulative_need + daily_balance


class WateringStrategyFactory:
    """Fournit la stratégie de volume (ADR-028) — unique et indépendante de l'heure."""

    @staticmethod
    def from_irrigation_time(irrigation_time: str) -> WateringVolumeStrategy:
        """Retourne la stratégie inclusive. L'argument est conservé pour compatibilité."""
        return InclusiveWateringStrategy()
