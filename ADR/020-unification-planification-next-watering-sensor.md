# 020 — Unification de la logique de planification temporelle pour NextWateringSensor

**Date** : 2026-06-01  
**Statut** : Proposé  
**Décideurs** : Équipe projet

---

## Contexte

La plateforme `sensor.py` intègre sa propre logique d'estimation temporelle pour calculer la valeur de l'entité `NextWateringSensor`. Cette réimplémentation duplique le code du module `scheduler.py`.

En cas d'absence de date de dernier arrosage (`last_auto_watering_date = None`), le capteur extrapole une date future alors que le planificateur déclenche une exécution immédiate. Cette divergence produit un affichage incohérent pour l'utilisateur : l'interface indique une date qui ne correspond pas à l'échéance réelle gérée par la tâche de fond Home Assistant.

## Décision

Centraliser le calcul de la prochaine échéance au sein du composant `IrrigationScheduler`. Le scheduler devient la source unique de vérité et expose une propriété publique `next_trigger` lue directement par l'entité Home Assistant.

### Modifications du code source

Dans `custom_components/my_garden_irrigation/scheduler.py` :

```python
class IrrigationScheduler:
    def __init__(self, ...) -> None:
        # ...
        self.next_trigger: datetime | None = None  # Source de vérité

    def reschedule_auto_irrigation(self) -> None:
        # ... extraction hour, minute ...
        now = dt_util.now()
        next_trigger = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_trigger <= now:
            next_trigger += timedelta(days=1)

        # Sauvegarde de la date calculée par le planificateur officiel
        self.next_trigger = next_trigger
        self._auto_unsub = async_track_point_in_time(self._hass, ..., next_trigger)
```

Dans `custom_components/my_garden_irrigation/sensor.py` :

```python
class NextWateringSensor(CoordinatorEntity[IrrigationCoordinator], SensorEntity):
    @property
    def native_value(self) -> datetime | None:
        """Consomme la propriété unifiée du scheduler."""
        if self.coordinator._scheduler is not None:
            return self.coordinator._scheduler.next_trigger
        return None
```

Toute logique de calcul de date résiduelle dans `sensor.py` est supprimée.

## Justification

- **Source unique de vérité** : l'entité `async_track_point_in_time` enregistrée dans HA et la valeur affichée dans l'interface référencent désormais exactement le même objet `datetime`.
- **Suppression de la duplication** : la logique de calcul `now.replace(hour=...) + timedelta(days=1)` n'existe plus qu'en un seul endroit, réduisant le risque de divergence lors d'évolutions futures.
- **Comportement bord correctement géré** : si `scheduler` est `None` (intégration non encore initialisée), le capteur retourne `None` sans erreur — comportement plus sûr que l'extrapolation précédente.

## Conséquences

- **Positives** : suppression définitive des divergences d'affichage entre l'interface et l'état réel des tâches de fond HA ; réduction de la surface de code à maintenir.
- **Négatives** : l'entité sensor dépend désormais de la disponibilité du sous-module `scheduler` lors des cycles de rafraîchissement ; un `scheduler` non encore initialisé expose `None` le temps du démarrage.
- **Relation** : dépend de ADR-012 (injection de `IrrigationScheduler` par callbacks) ; s'applique après ADR-018 (suppression de `_irrigation_sequence_task` du scheduler).
