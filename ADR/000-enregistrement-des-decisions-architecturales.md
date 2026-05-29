# 000 — Enregistrement des décisions architecturales

**Date** : 2026-01-23  
**Statut** : Accepté  
**Décideurs** : Équipe projet  

---

## Contexte

Le projet My Garden Irrigation implique des choix techniques complexes (calculs agronomiques, intégration Home Assistant, gestion d'états). L'absence de documentation sur les décisions passées rend l'intégration de nouveaux contributeurs difficile et risque de provoquer des régressions conceptuelles.

## Décision

Utiliser les ADR (Architecture Decision Records) pour documenter les changements architecturaux significatifs.

- **Format** : Markdown.
- **Emplacement** : dossier `ADR/` à la racine du projet.
- **Nommage** : `NNN-titre-court.md` (ex. `004-config-flow-vs-yaml.md`).
- **Cycle de vie** : Proposé → Accepté / Rejeté → Obsolète.

## Justification

Un format texte versionné dans git garantit que chaque décision est liée à un diff, révisable via PR, et accessible sans outil tiers.

## Conséquences

- **Positives** : historique clair des choix techniques, facilite la revue de code, onboarding accéléré.
- **Négatives** : légère surcharge administrative lors de la conception.
