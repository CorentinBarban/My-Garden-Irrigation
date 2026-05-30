# 005 — Fréquence de mise à jour des sensors

**Date** : 2026-05-28  
**Révisé** : 2026-05-29  
**Statut** : Accepté (révisé)  
**Décideurs** : Équipe projet  

---

## Contexte

Les sensors ETc doivent se recalculer régulièrement. Trois stratégies de mise à jour sont envisageables :

1. **Polling à intervalle fixe** : recalcul toutes les N heures via `DataUpdateCoordinator`.
2. **Réactif sur changement d'état** : recalcul à chaque changement du sensor ETo source via `async_track_state_change_event`.
3. **Planifié une fois par jour** : recalcul quotidien (ETo est une valeur journalière).

## Décision

~~**Option 2 — Réactif sur changement d'état** : l'intégration s'abonnait aux changements d'état de l'entité ETo configurée.~~

**Option 1 — Polling horaire via `DataUpdateCoordinator` (`SCAN_INTERVAL = timedelta(hours=1)`).**

> **Révision v2** : le mode réactif était couplé à l'approche entité HA (ADR-002). Depuis le passage à l'appel direct Open-Meteo, il n'y a plus d'entité HA à observer. Le coordinator utilise `DataUpdateCoordinator` avec un intervalle fixe d'1 heure.

```python
# coordinator.py
SCAN_INTERVAL = timedelta(hours=1)

class IrrigationCoordinator(DataUpdateCoordinator[IrrigationData]):
    def __init__(self, hass, entry):
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)
```

Un recalcul forcé reste possible via le service `my_garden_irrigation.recalculate`.

## Justification

| Critère                        | Polling 1 h ✅ | Réactif | Quotidien |
|-------------------------------|---------------|---------|-----------|
| Compatibilité appel direct API | ✓            | ✗ (pas d'entité à observer) | ✓ |
| Réactivité                    | Moyenne       | Haute   | Faible    |
| Charge réseau                 | 24 req/j      | Variable | 1 req/j  |
| Complexité d'implémentation   | Faible (pattern standard HA) | Moyenne | Moyenne |
| Granularité ETo réaliste      | Horaire = suffisant | Inutile (ETo journalier) | Insuffisant |

L'ETo Open-Meteo est une prévision journalière qui ne change pas en cours de journée. Un polling horaire est donc plus que suffisant en pratique tout en restant idiomatique avec `DataUpdateCoordinator`.

## Conséquences

- **Positives** : implémentation simple (pattern HA standard), 24 appels réseau/jour seulement, recalcul forcé disponible via service.
- **Négatives** : délai maximal d'1 heure entre un changement de configuration et la mise à jour des sensors — acceptable car l'ETo est une valeur journalière.
- **Gestion des erreurs** : `UpdateFailed` levée si Open-Meteo est inaccessible, sensors marqués `unavailable` par HA. Rétablissement automatique à la prochaine tentative (voir ADR-002).
- **Couplage** : ce choix est une conséquence directe de ADR-002 (source ETo = API directe) — les deux décisions sont liées.
