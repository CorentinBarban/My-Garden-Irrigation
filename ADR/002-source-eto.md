# 002 — Source de l'évapotranspiration de référence (ETo)

**Date** : 2026-05-28  
**Révisé** : 2026-05-29  
**Statut** : Accepté (révisé)  
**Décideurs** : Équipe projet  

---

## Contexte

Le calcul `ETc = Kc × ETo` requiert une valeur d'ETo fiable et mise à jour quotidiennement. Plusieurs sources ont été évaluées :

1. Entité Home Assistant existante (fournie par l'utilisateur)
2. Appel direct à l'API Open-Meteo depuis l'intégration
3. Calcul interne à partir des sensors météo HA (température, humidité, vent, rayonnement)
4. Valeur fixe saisie manuellement

## Décision

~~**Option 1 comme source principale** — l'intégration consommait une entité HA choisie par l'utilisateur dans le Config Flow (`eto_entity_id`).~~

**Option 2 — Appel direct à l'API Open-Meteo depuis l'intégration.**

> **Révision v2** : l'option entité HA a été abandonnée et le champ `eto_entity_id` supprimé lors de la migration `entry.version 1 → 2`. Le coordinator (`IrrigationCoordinator._fetch_eto`) appelle directement Open-Meteo en utilisant les coordonnées GPS configurées dans Home Assistant (`hass.config.latitude` / `hass.config.longitude`).

Endpoint appelé par l'intégration :

```
GET https://api.open-meteo.com/v1/forecast
  ?latitude={hass.config.latitude}
  &longitude={hass.config.longitude}
  &daily=et0_fao_evapotranspiration
  &timezone=auto
  &forecast_days=1
```

## Justification

| Critère                        | Entité HA | Open-Meteo direct ✅ | Calcul interne | Valeur fixe |
|-------------------------------|-----------|----------------------|----------------|-------------|
| Flexibilité (station locale…) | ✓         | ✗                    | ✓              | ✗           |
| Précision                      | Variable  | Haute (Penman-Monteith) | Haute       | Faible      |
| Friction à l'installation     | Haute     | Nulle                | Haute          | Faible      |
| Complexité d'implémentation   | Faible    | Moyenne              | Haute          | Faible      |
| Dépendance externe dans le code | ✗       | ✓                    | ✗              | ✗           |
| Gratuit / sans clé API        | —         | ✓                    | —              | —           |

L'approche entité HA imposait à l'utilisateur de configurer une intégration météo tierce avant d'installer celle-ci, créant une dépendance d'installation non triviale. L'appel direct à Open-Meteo élimine cette friction : aucune configuration supplémentaire n'est requise car les coordonnées GPS sont déjà présentes dans HA.

## Conséquences

- **Positives** : installation zéro-config (coordonnées HA suffisantes), ETo toujours cohérent avec Penman-Monteith FAO, pas de gestion d'API key.
- **Négatives** : dépendance réseau externe dans le coordinator — si Open-Meteo est inaccessible, les sensors passent en `unavailable` jusqu'à la prochaine tentative.
- **Comportement en erreur** : `UpdateFailed` levée, HA marque les sensors `unavailable`. Rétablissement automatique à la prochaine mise à jour (`SCAN_INTERVAL = 1 h`, voir ADR-005).
- **Pas de support station locale** : un jardinier avec une station météo HA ne peut pas substituer ses données — accepté comme contrainte v1.
