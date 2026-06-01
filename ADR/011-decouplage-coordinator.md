# 011 — Découplage du Coordinator : RuntimeConfigState et PersistenceManager

**Date** : 2026-05-31  
**Statut** : Accepté  
**Décideurs** : Équipe projet

---

## Contexte

`IrrigationCoordinator` avait évolué en un objet-dieu de 525 lignes assurant simultanément cinq responsabilités :

1. Polling météo Open-Meteo et calcul des besoins nets (rôle légitime du `DataUpdateCoordinator`)
2. Stockage de tout l'état mutable de configuration (17 variables d'instance dans `__init__`)
3. Persistance I/O via `homeassistant.helpers.storage.Store`
4. Orchestration de `ValveTracker`
5. Orchestration de `IrrigationScheduler`

Le graphe de dépendances montrait 119 arêtes sur ce seul nœud, bridgeant 17 communautés. Toute modification de la logique métier nécessitait d'importer `IrrigationCoordinator`, entraînant une dépendance circulaire de fait sur `homeassistant.*` dans tous les modules. L'écriture de tests unitaires était impossible sans instancier un environnement HA complet.

## Décision

Extraire deux nouvelles responsabilités dans des modules dédiés :

### 1. `config_state.py` — RuntimeConfigState (Python pur)

Classe Python ordinaire contenant tout l'état mutable de configuration précédemment éparpillé dans `coordinator.__init__`. Contrainte absolue : **zéro import `homeassistant.*` au runtime**. Le module est donc testable avec `pytest` seul, sans infrastructure HA.

Responsabilités :
- Lecture initiale depuis `ConfigEntry.options` via `from_entry(entry)`
- Restauration depuis le Store via `restore_from_storage(stored, date_iso)` avec garde `options_hash` : si les options ont changé depuis le dernier redémarrage, les surcharges runtime (débit, heure) sont ignorées
- Sérialisation via `to_storage(date_iso)` 
- Tous les setters de configuration (`set_flow_rate`, `set_irrigation_time`, etc.)
- Logique métier pure : `apply_watering_volumes()`, `apply_midnight_transfer()`, `reset_irrigation()`, `get_crop_surfaces()`, `cleanup_stale_crops()`

### 2. `persistence.py` — PersistenceManager (wrapper HA Store)

Wrapper fin autour de `homeassistant.helpers.storage.Store`. Deux méthodes seulement : `async_load() → dict` et `async_save(data: dict) → None`. Toute la logique de sérialisation reste dans `RuntimeConfigState`.

### 3. `coordinator.py` réduit à ~130 lignes

Le coordinator conserve uniquement :
- Instanciation de `RuntimeConfigState` et `PersistenceManager`
- Chargement des données Kc et restauration de l'état au démarrage
- `_async_update_data()` : fetch Open-Meteo + calcul `compute_irrigation_data()`
- Delegates minces vers `self.config.*` pour l'API publique des entités
- Callbacks internes (`_on_volumes_applied`, `_on_midnight`, `_on_trigger`) comme point d'orchestration

## Justification

- **Testabilité** : `RuntimeConfigState` et `core/` sont des modules Python purs. La suite de tests passe sans aucun mock HA (89+ tests, 0 dépendance `homeassistant.*` dans les tests).
- **Lisibilité** : le coordinator exprime clairement son rôle HA — la logique d'état est dans `config_state.py`, la logique métier dans `core/`.
- **Sécurité des modifications** : modifier le calcul des surfaces ou la sérialisation du Store ne nécessite plus de toucher au coordinator.

## Conséquences

- **Positives** : coordinator réduit à sa responsabilité unique (`DataUpdateCoordinator`), 17 variables d'instance remplacées par 2 (`self.config` + `self._persistence`), couverture de tests complète sur toute la logique métier.
- **Négatives** : les entités HA accèdent désormais à `coordinator.config.flow_rate` au lieu de `coordinator.flow_rate` (migration mécanique, aucun impact fonctionnel).
