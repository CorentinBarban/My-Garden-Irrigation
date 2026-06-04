"""ADR-026 — Command : Journal de transactions hydriques pour la résilience.

Aucune dépendance homeassistant.* — testable directement avec pytest.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


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
    """Accumule les transactions hydriques du jour et calcule leur solde net.

    Chaque rafraîchissement météo enregistre une transaction ETO (+).
    Chaque fermeture de vanne enregistre une transaction IRRIGATION (−).
    À minuit, replay() fournit le solde net du jour ; from_storage() restaure
    l'état intra-journée au redémarrage.
    """

    def __init__(self) -> None:
        self._transactions: list[WaterTransaction] = []

    def record(self, tx: WaterTransaction) -> None:
        self._transactions.append(tx)

    def set_daily_need(self, crop_id: str, need: float, recorded_at: datetime) -> None:
        """Enregistre (ou remplace) l'apport ETo journalier d'une culture.

        Idempotent par culture : une seule transaction ETO est conservée par jour,
        quel que soit le nombre de rafraîchissements météo horaires.
        """
        self._transactions = [
            tx
            for tx in self._transactions
            if not (tx.crop_id == crop_id and tx.source == WaterSource.ETO)
        ]
        self._transactions.append(
            WaterTransaction(crop_id, need, WaterSource.ETO, recorded_at)
        )

    def replay(self) -> dict[str, float]:
        """Recalcule le solde net par culture depuis zéro (plancher 0)."""
        balance: dict[str, float] = {}
        for tx in self._transactions:
            balance[tx.crop_id] = balance.get(tx.crop_id, 0.0) + tx.volume_liters
        return {k: max(0.0, v) for k, v in balance.items()}

    def applied_volumes(self) -> dict[str, float]:
        """Volumes arrosés aujourd'hui par culture (litres positifs).

        Somme des transactions IRRIGATION (dont le volume est négatif), ramenée en
        valeurs positives.
        """
        applied: dict[str, float] = {}
        for tx in self._transactions:
            if tx.source == WaterSource.IRRIGATION:
                applied[tx.crop_id] = applied.get(tx.crop_id, 0.0) - tx.volume_liters
        return applied

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
