# 002 — Source de l'évapotranspiration de référence (ETo)

**Date** : 2026-05-28  
**Statut** : Accepté  
**Décideurs** : Équipe projet  

---

## Contexte

Le calcul `ETc = Kc × ETo` requiert une valeur d'ETo fiable et mise à jour quotidiennement. Plusieurs sources ont été évaluées :

1. Entité Home Assistant existante (fournie par l'utilisateur)
2. Appel direct à l'API Open-Meteo depuis l'intégration
3. Calcul interne à partir des sensors météo HA (température, humidité, vent, rayonnement)
4. Valeur fixe saisie manuellement

## Décision

**Option 1 comme source principale, Option 2 comme source recommandée, Option 4 comme fallback.**

L'intégration consomme n'importe quelle entité HA exposant une valeur en `mm` ou `mm/d`. L'utilisateur choisit sa source dans le Config Flow.

La documentation de l'intégration recommande de coupler avec l'intégration **Open-Meteo** (gratuite, sans clé API, couvre le monde entier), qui expose nativement un sensor ETo via Penman-Monteith.

Endpoint Open-Meteo utilisé par l'intégration recommandée :

```
GET https://api.open-meteo.com/v1/forecast
  ?latitude={lat}&longitude={lon}
  &daily=et0_fao_evapotranspiration
  &timezone=auto
  &forecast_days=1
```

En dernier recours, un `input_number.eto_manuel` peut être créé par l'utilisateur comme source de fallback.

## Justification

| Critère                        | Entité HA ✅ | Open-Meteo direct | Calcul interne | Valeur fixe |
|-------------------------------|-------------|-------------------|----------------|-------------|
| Flexibilité (station locale…) | ✓           | ✗                 | ✓              | ✗           |
| Précision                      | Variable    | Haute             | Haute          | Faible      |
| Complexité d'implémentation   | Faible      | Moyenne           | Haute          | Faible      |
| Dépendance externe dans le code | ✗         | ✓                 | ✗              | ✗           |
| Gratuit / sans clé API        | —           | ✓                 | —              | —           |

Déléguer la source ETo à une entité HA existante respecte le principe de responsabilité unique : l'intégration calcule les besoins hydriques, elle ne gère pas la météo. Cela la rend compatible avec toute station météo locale, API météo déjà configurée, ou même un sensor virtuel.

## Conséquences

- **Positives** : aucune dépendance réseau dans le code de l'intégration, compatibilité maximale, pas de gestion d'API key.
- **Négatives** : l'utilisateur doit configurer sa source ETo séparément — point de friction à l'installation documenté avec un guide pas-à-pas pour Open-Meteo.
- **Comportement si entité indisponible** : les sensors passent en état `unavailable`. Aucun calcul erroné n'est exposé.
