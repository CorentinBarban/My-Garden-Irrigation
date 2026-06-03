"""ADR-024 — Strategy : Calcul adaptatif du volume d'arrosage.

Aucune dépendance homeassistant.* — testable directement avec pytest.
"""
from __future__ import annotations

from typing import Protocol

from ..const import EVENING_IRRIGATION_HOUR_THRESHOLD


class WateringVolumeStrategy(Protocol):
    """Protocole de calcul du volume d'arrosage cible."""

    def calculate_target_volume(
        self, cumulative_need: float, daily_need: float
    ) -> float: ...


class StandardMorningStrategy:
    """Arrosage matinal : rembourse uniquement la dette historique.

    Le besoin journalier en cours sera comptabilisé à minuit (Règle 1).
    """

    def calculate_target_volume(self, cumulative_need: float, daily_need: float) -> float:
        return cumulative_need


class InclusiveEveningStrategy:
    """Arrosage tardif : anticipe la clôture de minuit (Règle 2).

    Inclut le besoin journalier pour éviter une dette fantôme à 00h01.
    """

    def calculate_target_volume(self, cumulative_need: float, daily_need: float) -> float:
        return cumulative_need + daily_need


class WateringStrategyFactory:
    """Sélectionne la stratégie de volume adaptée à l'heure d'arrosage (ADR-024).

    Centralise la logique de sélection hors du coordinator — extensible
    sans modifier fire_irrigation_event (principe Open/Closed).
    """

    @staticmethod
    def from_irrigation_time(irrigation_time: str) -> WateringVolumeStrategy:
        """Retourne la stratégie correspondant à l'heure HH:MM:SS configurée."""
        try:
            hour = int(irrigation_time.split(":")[0])
            if hour >= EVENING_IRRIGATION_HOUR_THRESHOLD:
                return InclusiveEveningStrategy()
        except (ValueError, AttributeError, IndexError):
            pass
        return StandardMorningStrategy()
