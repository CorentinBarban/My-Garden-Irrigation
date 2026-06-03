"""Fonctions pures de comptabilité hydrique — My Garden Irrigation.

Aucune dépendance envers homeassistant.* : testables directement avec pytest.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol


# ---------------------------------------------------------------------------
# ADR-024 — Strategy : Calcul adaptatif du volume d'arrosage
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# ADR-026 — Command : Journal de transactions hydriques
# ---------------------------------------------------------------------------

class WaterSource(StrEnum):
    ETO = "eto"
    RAIN = "rain"
    IRRIGATION = "irrigation"


@dataclass(frozen=True)
class WaterTransaction:
    crop_id: str
    volume_liters: float   # positif = besoin (débit), négatif = apport (crédit)
    source: WaterSource
    recorded_at: datetime


class DailyWaterLedger:
    """Accumule les transactions hydriques du jour et permet leur replay."""

    def __init__(self) -> None:
        self._transactions: list[WaterTransaction] = []

    def record(self, tx: WaterTransaction) -> None:
        self._transactions.append(tx)

    def replay(self) -> dict[str, float]:
        """Recalcule le solde net par culture depuis zéro (≥ 0)."""
        balance: dict[str, float] = {}
        for tx in self._transactions:
            balance[tx.crop_id] = balance.get(tx.crop_id, 0.0) + tx.volume_liters
        return {k: max(0.0, v) for k, v in balance.items()}

    def to_storage(self) -> list[dict]:
        return [
            {
                "crop_id": tx.crop_id,
                "volume_liters": tx.volume_liters,
                "source": tx.source,
                "recorded_at": tx.recorded_at.isoformat(),
            }
            for tx in self._transactions
        ]

    @classmethod
    def from_storage(cls, data: list[dict]) -> DailyWaterLedger:
        ledger = cls()
        for item in data:
            ledger.record(WaterTransaction(
                crop_id=item["crop_id"],
                volume_liters=item["volume_liters"],
                source=WaterSource(item["source"]),
                recorded_at=datetime.fromisoformat(item["recorded_at"]),
            ))
        return ledger

    def __bool__(self) -> bool:
        return bool(self._transactions)


# ---------------------------------------------------------------------------
# Fonctions pures existantes
# ---------------------------------------------------------------------------

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
