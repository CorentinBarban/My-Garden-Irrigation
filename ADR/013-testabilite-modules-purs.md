# 013 — Stratégie de testabilité : modules Python purs sans dépendance HA

**Date** : 2026-05-31  
**Statut** : Accepté  
**Décideurs** : Équipe projet

---

## Contexte

L'intégration ne disposait d'aucun test automatisé. L'ensemble du code business (calculs FAO-56, bilan hydrique, gestion de l'état) était entrelacé avec des imports `homeassistant.*`, rendant toute tentative de test dépendante de l'installation complète de HA et de son infrastructure asyncio.

Les deux options classiques pour tester des intégrations HA sont :

1. **Tests d'intégration complets** : utiliser `pytest-homeassistant-custom-component` avec un vrai `hass` mocké — couverture maximale mais configuration lourde, tests lents (~10 s/test), maintenance complexe sur les mises à jour HA.
2. **Tests unitaires purs** : extraire la logique dans des modules sans import HA et tester ces modules seuls — rapide, stable, mais nécessite une séparation stricte du code.

## Décision

Adopter la stratégie **modules Python purs** : tout code porteur de logique métier doit être écrit sans aucun import `homeassistant.*` au runtime. Les modules HA (coordinator, entités, config_flow) restent non couverts par les tests unitaires mais sont réduits au câblage.

### Périmètre testable sans HA

| Module | Responsabilité testée |
|---|---|
| `core/calculations.py` | Calculs FAO-56 : ETc, précipitations effectives, besoins nets |
| `core/ledger.py` | Allocation des volumes par surface, transfert de minuit |
| `core/kc_data.py` | Accesseurs coefficients Kc (get_kc, get_default_density, etc.) |
| `config_state.py` (RuntimeConfigState) | Setters, sérialisation/restauration Store, guards options_hash, cleanup |

### Convention d'import imposée

`config_state.py` et tout module sous `core/` : **interdit d'importer `homeassistant.*`** au niveau module. Tout import HA éventuel doit être localisé dans un bloc `if TYPE_CHECKING:`.

### Suite de tests

`tests/conftest.py` ajoute la racine du projet au `PYTHONPATH` — aucune installation HA n'est nécessaire pour faire tourner `pytest`. Les tests utilisent des instances directes des classes (pas de mocks) et des assertions numériques `pytest.approx`.

## Justification

- **Vélocité** : 107+ tests s'exécutent en < 2 secondes sur Python 3.14 sans aucune dépendance externe au-delà de `pytest`.
- **Stabilité** : les tests ne cassent pas lors des mises à jour de Home Assistant (aucun mock de `hass`, `ConfigEntry`, etc.).
- **Documentation vivante** : les tests `test_calculations.py` et `test_config_state.py` servent de spécification exécutable des formules agronomiques.
- **Détection précoce** : les bugs de logique pure (division par zéro, rescalage cumulatif, réconciliation options_hash) sont détectés en CI sans déploiement.

## Conséquences

- **Positives** : couverture à 100% de la logique agronomique et du bilan hydrique ; pas de dépendance à un environnement HA en CI.
- **Négatives** : les modules HA (`coordinator.py`, `valve_tracker.py`, `scheduler.py`) restent non couverts par les tests unitaires. Les bugs de câblage HA (mauvaise signature de callback, entités non enregistrées) ne sont détectés qu'à l'exécution. Cette limitation est acceptable car ces modules sont des delegates minces sans logique complexe.
