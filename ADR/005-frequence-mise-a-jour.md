# 005 — Fréquence de mise à jour des sensors

**Date** : 2026-05-28  
**Statut** : Accepté  
**Décideurs** : Équipe projet  

---

## Contexte

Les sensors ETc doivent se recalculer quand l'ETo change. Trois stratégies de mise à jour sont envisageables :

1. **Polling à intervalle fixe** : recalcul toutes les N minutes.
2. **Réactif sur changement d'état** : recalcul à chaque changement du sensor ETo source.
3. **Planifié une fois par jour** : recalcul quotidien (ETo est une valeur journalière).

## Décision

**Option 2 — Réactif sur changement d'état (`async_track_state_change_event`).**

L'intégration s'abonne aux changements d'état de l'entité ETo configurée. À chaque nouvel état valide, tous les sensors ETc sont recalculés immédiatement.

Un recalcul est également déclenché :
- au démarrage de HA (`async_added_to_hass`)
- via le service `potager_irrigation.recalculate`

## Justification

| Critère                        | Polling | Réactif ✅ | Quotidien |
|-------------------------------|---------|------------|-----------|
| Réactivité                    | Moyenne | Haute      | Faible    |
| Charge CPU/mémoire            | Moyenne | Faible     | Très faible |
| Cohérence avec la source ETo  | Partielle | Totale   | Partielle |
| Complexité d'implémentation   | Faible  | Faible     | Moyenne   |

L'ETo est une valeur qui change peu (quotidienne ou horaire selon la source), donc le nombre d'événements déclenchés est naturellement limité. Le mode réactif est le pattern standard HA pour les sensors dérivés.

## Conséquences

- **Positives** : sensors toujours synchronisés avec la source ETo, pas de recalcul inutile, pattern idiomatique HA.
- **Négatives** : si la source ETo est très volatile (mise à jour toutes les minutes), les recalculs sont fréquents — acceptable car le calcul est O(n cultures) et très rapide.
- **Gestion des états invalides** : si l'ETo passe en `unavailable` ou `unknown`, les sensors passent également en `unavailable`. Ils se rétablissent automatiquement dès que la source redevient valide.
- **Pas de `scan_interval`** : la plateforme sensor ne définit pas de `SCAN_INTERVAL` — la mise à jour est entièrement pilotée par les événements.
