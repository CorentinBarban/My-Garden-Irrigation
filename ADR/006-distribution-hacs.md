# 006 — Distribution : HACS vs intégration core Home Assistant

**Date** : 2026-05-28  
**Statut** : Accepté  
**Décideurs** : Équipe projet  

---

## Contexte

Une intégration HA peut être distribuée de deux façons :

1. **Core HA** : intégrée directement dans le dépôt officiel `home-assistant/core`. Disponible nativement pour tous les utilisateurs.
2. **HACS** (Home Assistant Community Store) : dépôt GitHub indépendant, installable via HACS. Mise à jour indépendante du cycle HA.
3. **Installation manuelle** : copie dans `custom_components/`, sans gestionnaire.

## Décision

**HACS en v1, avec ambition Core en v2.**

L'intégration est distribuée comme custom component via HACS pour la v1. Une soumission au core HA sera envisagée après une période de stabilisation et de retours utilisateurs.

Prérequis HACS à respecter :
- Dépôt GitHub public
- `hacs.json` à la racine
- `manifest.json` valide avec `version`
- Releases GitHub taguées (semver)

```json
// hacs.json
{
  "name": "Potager Irrigation",
  "render_readme": true
}
```

## Justification

| Critère                          | Core HA | HACS ✅ | Manuel |
|----------------------------------|---------|---------|--------|
| Délai de mise en prod            | 3–6 mois (review) | Immédiat | Immédiat |
| Mise à jour automatique utilisateur | ✓   | ✓       | ✗      |
| Audience                         | Tous    | ~500K   | Faible |
| Contraintes de qualité           | Très élevées | Modérées | Aucune |
| Cycle de release indépendant     | ✗       | ✓       | ✓      |

Le process de soumission au core HA exige une couverture de tests > 95%, une revue approfondie et plusieurs cycles d'itération (souvent 3–6 mois). HACS permet de livrer rapidement, de collecter des retours et de stabiliser avant une éventuelle soumission core.

## Conséquences

- **Positives** : time-to-market court, itérations rapides, pas de contrainte sur le cycle de release HA.
- **Négatives** : l'utilisateur doit avoir HACS installé (cas très majoritaire dans la communauté HA avancée).
- **Versioning** : utiliser semver strict (`1.0.0`, `1.1.0`, `2.0.0`). Toute breaking change de config bumpe le major.
- **Tests** : viser ≥ 80% de couverture dès la v1 pour faciliter une future soumission core.
