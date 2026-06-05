# 024 — Strategy : Calcul adaptatif du volume d'arrosage (matin vs soir)

**Date** : 2026-06-03  
**Statut** : **Remplacé par ADR-028** (décision de volume désormais toujours inclusive, sans distinction matin/soir)  
**Décideurs** : Équipe projet

---

## Contexte

La Règle 2 de la spécification impose que le volume commandé à la vanne varie selon le moment de la journée :

- **Arrosage matinal** (avant `EVENING_IRRIGATION_HOUR_THRESHOLD = 12`) : le volume cible est égal au seul bilan cumulé historique, car le besoin journalier du jour en cours sera transféré dans le stock à minuit selon la Règle 1.
- **Arrosage tardif** (≥ 12h) : le volume cible doit inclure le besoin journalier de la journée en cours pour éviter qu'il soit enregistré comme une dette à minuit (Anomalie B de la spécification).

Ce comportement existe déjà dans `coordinator.py::fire_irrigation_event` (L266-272) sous la forme d'un bloc conditionnel inline :

```python
is_evening = hour >= EVENING_IRRIGATION_HOUR_THRESHOLD
total_volume = total_cumulative + (data.total_daily_need_liters if is_evening else 0.0)
```

Ce code fonctionne mais présente trois fragilités :

1. **Extension difficile** : ajouter un troisième mode (ex. arrosage en après-midi, coefficient d'évaporation vent, mode canicule) impose de modifier `fire_irrigation_event`, qui est aussi responsable de la validation du débit, de la construction du payload et de l'émission de l'événement HA.
2. **Testabilité limitée** : pour tester les deux formules de calcul, il faut instancier tout le contexte de `IrrigationCoordinator` avec `self.config`, `self.data`, etc.
3. **Violation du principe Single Responsibility** : `fire_irrigation_event` décide à la fois *combien* arroser (logique agronomique) et *comment* le commander (logique infrastructure).

## Décision

Extraire le calcul du volume dans une hiérarchie de classes `WateringVolumeStrategy`, séparant la logique de décision agronomique de l'infrastructure d'émission d'événements.

### Définition du protocole

Dans `core/ledger.py` ou un nouveau fichier `core/strategies.py` :

```python
from typing import Protocol

class WateringVolumeStrategy(Protocol):
    """Stratégie de calcul du volume d'arrosage cible."""

    def calculate_target_volume(
        self,
        cumulative_need: float,
        daily_need: float,
    ) -> float:
        """Retourne le volume (litres) à commander à la vanne."""
        ...


class StandardMorningStrategy:
    """Arrosage matinal : rembourse uniquement la dette historique.

    Le besoin journalier en cours sera comptabilisé à minuit via la Règle 1.
    """

    def calculate_target_volume(self, cumulative_need: float, daily_need: float) -> float:
        return cumulative_need


class InclusiveEveningStrategy:
    """Arrosage tardif : anticipe la clôture de minuit en incluant le flux du jour.

    Évite qu'une dette fantôme apparaisse à 00h01 après un arrosage de soirée.
    """

    def calculate_target_volume(self, cumulative_need: float, daily_need: float) -> float:
        return cumulative_need + daily_need
```

### Injection dans le coordinator

Dans `coordinator.py::fire_irrigation_event` :

```python
def _resolve_watering_strategy(self) -> WateringVolumeStrategy:
    """Sélectionne la stratégie de calcul selon l'heure d'arrosage configurée."""
    try:
        hour = int(self.config.irrigation_time.split(":")[0])
        if hour >= EVENING_IRRIGATION_HOUR_THRESHOLD:
            return InclusiveEveningStrategy()
    except (ValueError, AttributeError, IndexError):
        pass
    return StandardMorningStrategy()

def fire_irrigation_event(self) -> bool:
    ...
    strategy = self._resolve_watering_strategy()
    total_volume = strategy.calculate_target_volume(
        total_cumulative,
        data.total_daily_need_liters,
    )
    ...
```

### Tests unitaires purs

```python
def test_morning_strategy_ignores_daily_need():
    s = StandardMorningStrategy()
    assert s.calculate_target_volume(cumulative_need=8.0, daily_need=4.0) == 8.0

def test_evening_strategy_includes_daily_need():
    s = InclusiveEveningStrategy()
    assert s.calculate_target_volume(cumulative_need=8.0, daily_need=4.0) == 12.0
```

Ces tests couvrent directement les Scénarios I et II de `spec.md` sans aucun mock HA.

## Justification

- **Open/Closed** : l'ajout d'un nouveau mode de calcul (ex. `AfternoonWithWindFactorStrategy`) se fait par création d'une nouvelle classe, sans modification de `fire_irrigation_event`.
- **Testabilité pure** : les stratégies sont des fonctions mathématiques pures — pas de dépendance à `HomeAssistant`, `ConfigEntry` ou aux timers.
- **Lisibilité** : `fire_irrigation_event` reste concentré sur son rôle de constructeur de payload et d'émetteur d'événement HA ; le *quoi arroser* est délégué.

## Conséquences

- **Positives** : Scénarios I et II de la spécification sont entièrement couverts par des tests unitaires sans infrastructure ; l'extension future (mode canicule, humidité sol) est non-invasive.
- **Négatives** : introduction d'un niveau d'indirection supplémentaire pour ce qui était une ligne de code. Justifié par la criticité agronomique de la formule et la nécessité de la tester isolément.
- **Relation** : applique la Règle 2 de `spec.md` ; complète ADR-013 (testabilité des modules purs) ; s'intègre dans `fire_irrigation_event` dont le flux de volume est régi par ADR-019 et dont la condition de déclenchement (calendrier/intervalle) est régie par ADR-025 (ADR-021 obsolète).
