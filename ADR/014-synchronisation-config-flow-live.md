# 014 — Synchronisation du formulaire de configuration depuis les valeurs live

**Date** : 2026-05-31  
**Statut** : Accepté  
**Décideurs** : Équipe projet

---

## Contexte

Les entités HA de configuration (ex. `GlobalFlowRateNumber`, `CyclesCountNumber`, `IrrigationTimeEntity`) permettent à l'utilisateur de modifier les valeurs de configuration directement depuis le tableau de bord HA, sans passer par le formulaire de configuration. Ces modifications mettent à jour `RuntimeConfigState` et sont persistées dans le Store HA (`.storage/`).

Cependant, `IrrigationOptionsFlowHandler.__init__` initialisait ses variables internes **depuis `entry.options`** :

```python
self._flow_rate: float = entry.options.get(CONF_GLOBAL_FLOW_RATE, 0.0)
```

`entry.options` ne change que lorsque l'utilisateur sauvegarde le formulaire. Entre deux passages par le formulaire, toute modification via une entité HA était invisible dans le formulaire : rouvrir la configuration affichait l'ancienne valeur.

## Décision

Dans `IrrigationOptionsFlowHandler.async_step_init()`, synchroniser les variables d'instance depuis `coordinator.config` (la source de vérité live) avant d'afficher le menu :

```python
async def async_step_init(self, user_input=None):
    coordinator = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
    if coordinator is not None:
        cfg = coordinator.config
        self._flow_rate = cfg.flow_rate
        self._valve_entity_id = cfg.valve_entity_id
        self._watering_frequency = cfg.watering_frequency
        self._watering_mode = cfg.watering_mode
        self._watering_interval_days = cfg.watering_interval_days
        self._irrigation_time = cfg.irrigation_time
        self._cycles_count = cfg.cycles_count
        self._soak_duration = cfg.soak_duration_minutes
        self._crops = list(cfg.crops)
    
    return self.async_show_menu(...)
```

Si le coordinator n'est pas encore disponible (intégration en cours d'initialisation), les valeurs de `entry.options` sont conservées en fallback.

## Justification

- **Source de vérité unique** : `RuntimeConfigState` est la représentation authoritative de la configuration courante. La synchronisation dans `async_step_init` garantit que le formulaire reflète toujours l'état réel, quelle que soit la façon dont les valeurs ont été modifiées (formulaire ou entité HA).
- **Pas de rechargement parasite** : mettre à jour `entry.options` à chaque modification d'entité déclencherait un rechargement complet de l'intégration (comportement de `OptionsFlowWithReload`). La synchronisation au moment de l'ouverture du formulaire évite ce rechargement inutile.
- **Cohérence lors de la sauvegarde** : quand l'utilisateur sauvegarde via le formulaire après avoir modifié des valeurs via les entités, `_save()` écrit les valeurs live dans `entry.options`, réconciliant les deux sources.

## Conséquences

- **Positives** : le formulaire affiche toujours les valeurs courantes, quel que soit le chemin de modification utilisé.
- **Négatives** : il existe une fenêtre de désynchronisation si l'utilisateur ouvre le formulaire pendant qu'une modification d'entité est en cours (race condition extrêmement improbable en pratique, car `async_step_init` est appelé sur la boucle asyncio principale).
