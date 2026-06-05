# 026 — Command : Journal de transactions hydriques pour la résilience

**Date** : 2026-06-03  
**Statut** : Proposé — **amendé par ADR-028** (`replay()` exclut l'arrosage et n'est plus planché : il fournit le bilan signé ETo/pluie du jour)  
**Décideurs** : Équipe projet

---

## Contexte

Le bilan hydrique repose sur deux mutations de l'état en mémoire survenant en cours de journée :

1. **Ajout d'une entrée de débit** (évapotranspiration + besoin journalier) : calculé à chaque rafraîchissement météo dans `coordinator.py::_async_update_data`.
2. **Imputation d'un volume d'arrosage** : appliqué via `config_state.py::apply_watering_volumes` lorsque le Blueprint signale la fin d'un cycle de vanne.

Ces deux mutations sont des **effets de bord directs** sur les dictionnaires `_cumulative_need` et `_watering_applied_today` de `RuntimeConfigState`. La persistance sur disque ne se produit qu'à la clôture de minuit ou lors d'un événement d'arrosage.

### Risque de perte de données

En cas de redémarrage de Home Assistant entre deux persistances (panne de courant, mise à jour, crash), l'état in-memory est perdu :

- Les arrosages du jour déjà appliqués par la vanne mais pas encore propagés dans `_cumulative_need` peuvent être oubliés, créant une dette fantôme au prochain cycle.
- Le bilan intermédiaire de la journée ne peut pas être reconstitué si la clôture de minuit ne s'est pas exécutée.

### Absence de traçabilité

Actuellement, il est impossible de répondre à la question : "Quelle a été la séquence exacte des événements hydriques du 2 juin ?" sans croiser les logs et la persistance.

## Décision

Introduire un objet valeur `WaterTransaction` et un journal quotidien de transactions `DailyWaterLedger` permettant de reconstituer l'état exact du bilan à tout instant par replay.

### Objet valeur `WaterTransaction`

Dans `core/ledger.py` :

```python
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

class WaterSource(StrEnum):
    ETO = "eto"          # évapotranspiration (débit)
    RAIN = "rain"        # pluie efficace (crédit)
    IRRIGATION = "irrigation"  # arrosage vanne (crédit)

@dataclass(frozen=True)
class WaterTransaction:
    crop_id: str
    volume_liters: float   # positif = besoin (débit), négatif = apport (crédit)
    source: WaterSource
    recorded_at: datetime
```

### Journal quotidien

```python
class DailyWaterLedger:
    """Accumule les transactions de la journée et permet leur replay."""

    def __init__(self) -> None:
        self._transactions: list[WaterTransaction] = []

    def record(self, tx: WaterTransaction) -> None:
        self._transactions.append(tx)

    def replay(self) -> dict[str, float]:
        """Recalcule le solde net par culture depuis zéro.

        Retourne crop_id → volume net résiduel (plafonné à 0 par le bas).
        """
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
    def from_storage(cls, data: list[dict]) -> "DailyWaterLedger":
        ledger = cls()
        for item in data:
            ledger.record(WaterTransaction(
                crop_id=item["crop_id"],
                volume_liters=item["volume_liters"],
                source=WaterSource(item["source"]),
                recorded_at=datetime.fromisoformat(item["recorded_at"]),
            ))
        return ledger
```

### Intégration dans le cycle de vie

- À chaque rafraîchissement météo : enregistrer une `WaterTransaction(source=ETO, volume_liters=+daily_need)` par culture.
- À chaque imputation d'arrosage : enregistrer une `WaterTransaction(source=IRRIGATION, volume_liters=-distributed)`.
- Le journal est persisté à chaque nouvelle entrée (I/O différé via `_schedule_config_save`).
- À la clôture de minuit : `DailyWaterLedger.replay()` remplace `midnight_transfer()` comme source de vérité, puis le journal est vidé.
- Au redémarrage : si `daily_ledger` est présent dans `.storage` avec la date du jour, le rejouer immédiatement pour restaurer l'état in-memory.

## Justification

- **Résilience au redémarrage** : un restart en cours de journée ne crée plus de dette fantôme ; les transactions persistées sont rejouées pour retrouver l'état exact.
- **Audit et débogage** : la liste des transactions permet de répondre précisément à "pourquoi le capteur affiche-t-il 6,3 L de dette ?" en listant les événements de la journée.
- **Composabilité** : le pattern Command découple la *décision* d'appliquer de l'eau de son *effet comptable*. Une transaction peut être annulée (en insérant une transaction inverse) sans corrompre l'historique.

## Conséquences

- **Positives** : résilience complète aux redémarrages intra-journée ; traçabilité auditale du bilan ; fondation pour un futur historique multi-jours sans rupture architecturale.
- **Négatives** : surcharge de persistance augmentée (un write `.storage` supplémentaire à chaque apport d'eau) ; complexité accrue par rapport à la mutation directe. Cette ADR est **optionnelle** — la livrer après la stabilisation des Règles 1, 2 et 3 (ADR-023 à 025).
- **Prérequis** : ADR-023 (Template Method) doit être en place pour que `DailyWaterLedger.replay()` puisse remplacer `midnight_transfer()` proprement dans le squelette de `_on_midnight`.
- **Relation** : s'appuie sur `core/ledger.py` ; renforce la testabilité établie par ADR-013 (fonctions pures) ; les transactions `WaterTransaction` sont les entités comptables dont ADR-008 (bilan hydrique cumulé) posait le principe.
