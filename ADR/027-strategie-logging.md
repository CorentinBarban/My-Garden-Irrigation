# 027 — Stratégie de journalisation : préoccupation transverse de la couche HA

**Date** : 2026-06-05  
**Statut** : Accepté  
**Décideurs** : Équipe projet

---

## Contexte

La journalisation existait mais de façon ad-hoc. Chaque module HA déclarait son `logging.getLogger(__name__)` et émettait des messages au jugé — bonnes bases (logger hiérarchique, formatage `%` paresseux, aucun f-string dans les logs), mais trois faiblesses :

1. **Pas de corrélation d'instance.** Avec plusieurs potagers (plusieurs `ConfigEntry`), rien dans un message n'indiquait *quelle* instance l'émettait. Diagnostic ambigu en multi-jardins.
2. **Couverture inégale.** `config_flow.py`, les plateformes d'entités et `persistence.py` n'émettaient aucun log ; les actions utilisateur (réglage via une entité, ajout/suppression de culture) ne laissaient aucune trace.
3. **Niveaux non formalisés.** DEBUG/INFO/WARNING/ERROR étaient employés sans convention écrite, alors que chaque décision du projet est documentée par ADR.

La contrainte structurante : ne pas compromettre la pureté du paquet `core/` (ADR-013), qui doit rester sans `import logging` pour être testable hors HA.

## Décision

Traiter la journalisation comme une **préoccupation transverse de la couche Home Assistant**, jamais du métier.

### 1. Le `core/` reste muet

Aucun module sous `core/` n'importe `logging`. La logique métier communique par valeurs de retour et exceptions ; c'est l'appelant HA qui journalise. La testabilité d'ADR-013 est préservée.

### 2. Logger hiérarchique conservé, contexte ajouté par-dessus

Chaque module HA garde son `_LOGGER = logging.getLogger(__name__)` (filtrage natif par `logger:` dans `configuration.yaml`). Par-dessus, un `IrrigationLoggerAdapter` (module `logging_util.py`) préfixe chaque message par le **nom du potager** : `[Potager Sud] message`. La hiérarchie de logger est intacte, le contexte d'instance est ajouté sans la casser.

### 3. Construction unique, diffusion par injection (ADR-012)

L'adaptateur est construit **une seule fois**, par `IrrigationCoordinator.__init__` via `instance_logger(_LOGGER, entry)`, puis :

- passé à `DataUpdateCoordinator` (les entités y accèdent par `coordinator.logger`) ;
- injecté à `ValveTracker`, `IrrigationScheduler`, `PersistenceManager` par leur constructeur — chacun conserve un paramètre `logger` avec le `_LOGGER` module comme défaut, ce qui les laisse testables isolément.

Les sous-modules ne fabriquent pas leur propre contexte : ils reçoivent le logger comme ils reçoivent leurs callbacks (ADR-012).

### 4. Convention de niveaux

| Niveau | Usage | Exemples |
|---|---|---|
| **DEBUG** | Flux détaillé, valeurs de calcul, transitions, I/O. Off par défaut. | requête Open-Meteo, planification du prochain arrosage, transitions de vanne, volumes intermédiaires, réglage d'une entité, chargement/sauvegarde du Store |
| **INFO** | Événement métier significatif et peu fréquent. | setup/unload de l'intégration, émission `irrigation_requested`, clôture de minuit, migration de schéma, ajout/suppression de culture, activation de l'arrosage auto, réinitialisation du bilan |
| **WARNING** | Anomalie récupérable, dégradation. | météo indisponible (retry), surface déraisonnable, vanne ouverte sans heure connue, débit non configuré, échec de sauvegarde |
| **ERROR** | Échec non récupérable dans le cycle courant. | exception lors du transfert de minuit |

### 5. Point d'entrée unique des actions utilisateur

Les traces d'action utilisateur sont émises dans les mutateurs du coordinator (`async_update_crop_field`, `set_*`, `async_set_auto_irrigation`, `async_reset_irrigation`) — appelés exclusivement par les entités — plutôt que dupliquées dans chaque méthode `async_set_*` des plateformes. Point de convergence unique, sans duplication, avec le contexte d'instance déjà disponible.

## Conséquences

- **Positives** : logs corrélés par instance ; couverture homogène (cycle de vie, actions utilisateur, config flow, persistance) ; niveaux prévisibles et filtrables ; `core/` toujours pur et testable.
- **Négatives** : un point d'indirection supplémentaire (`LoggerAdapter`) ; les sous-modules portent un paramètre `logger` de plus dans leur constructeur. Coût marginal, compensé par la traçabilité multi-jardins.
- **Compatibilité tests** : le défaut `logger=_LOGGER` sur les sous-modules préserve les tests existants (`test_resilience`, `test_ledger`, `test_config_state`) sans changement d'appel.
