# 012 — Injection par callbacks : ValveTracker et IrrigationScheduler

**Date** : 2026-05-31  
**Statut** : Accepté  
**Décideurs** : Équipe projet

---

## Contexte

Avant le refactoring (ADR-011), `ValveTracker` et `IrrigationScheduler` recevaient une référence directe à `IrrigationCoordinator` dans leur constructeur. Cette dépendance créait un couplage fort :

- Toute modification du coordinator pouvait casser silencieusement les deux modules
- Les deux classes ne pouvaient pas être instanciées dans un test sans un coordinator complet
- Le coordinator ne pouvait pas être remplacé ou mocké partiellement

## Décision

Remplacer la référence au coordinator par **injection de dépendances via callbacks async** :

### ValveTracker

```python
# Avant
ValveTracker(hass, coordinator)

# Après
ValveTracker(
    hass,
    config: RuntimeConfigState,        # état pur Python
    on_volumes_applied: Callable[[dict[str, float]], Awaitable[None]],
)
```

`ValveTracker` lit et écrit `config` directement (setters purs Python) et appelle `on_volumes_applied(volumes)` quand la vanne se ferme. Il n'a plus aucune connaissance du coordinator.

### IrrigationScheduler

```python
# Avant
IrrigationScheduler(hass, coordinator)

# Après
IrrigationScheduler(
    hass,
    config: RuntimeConfigState,
    on_midnight: Callable[[], Awaitable[None]],
    on_trigger: Callable[[str], Awaitable[None]],
)
```

`IrrigationScheduler` lit `config` directement pour planifier les déclenchements (`irrigation_time`, `watering_frequency`, etc.) et appelle les callbacks à minuit et lors du déclenchement automatique.

### Côté coordinator

Le coordinator instancie les deux modules avec ses propres méthodes comme callbacks :

```python
tracker = ValveTracker(hass, self.config, self._on_volumes_applied)
scheduler = IrrigationScheduler(hass, self.config, self._on_midnight, self._on_trigger)
```

Les callbacks `_on_volumes_applied` et `_on_midnight` dans le coordinator font le lien entre la logique pure (mise à jour du bilan) et les effets de bord HA (save Store, async_refresh).

## Justification

- **Inversion de dépendance** : les modules métier (`ValveTracker`, `IrrigationScheduler`) dépendent de l'abstraction (callbacks + config pure) et non du concret (coordinator HA).
- **Testabilité directe** : les deux modules peuvent être instanciés dans un test avec `MagicMock()` pour `hass`, une `RuntimeConfigState` réelle, et des `AsyncMock()` pour les callbacks — aucune infrastructure HA requise.
- **Découplage temporel** : `ValveTracker` et `IrrigationScheduler` ne savent pas si le coordinator existe ou non ; ils signalent leur résultat via callback et laissent l'orchestrateur décider de la réaction.

## Conséquences

- **Positives** : les deux modules sont réutilisables indépendamment, la surface de couplage se réduit aux signatures des callbacks (interfaces stables).
- **Négatives** : le coordinator doit conserver une référence à `_scheduler` pour pouvoir appeler `reschedule_auto_irrigation()` quand `irrigation_time` ou `auto_enabled` changent — ce cas particulier impose une référence sortante minimale du coordinator vers le scheduler.
