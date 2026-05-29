# 004 — Stratégie de configuration : Config Flow UI vs YAML

**Date** : 2026-05-28  
**Statut** : Accepté  
**Décideurs** : Équipe projet  

---

## Contexte

Home Assistant supporte deux modes de configuration des intégrations :

1. **YAML** : configuration dans `configuration.yaml`, rechargement requis, pas d'UI.
2. **Config Flow** : configuration via l'interface graphique HA, persistée en `config_entries`.
3. **Hybride** : Config Flow pour l'installation initiale, YAML pour les surcharges avancées.

## Décision

**Config Flow uniquement, avec Options Flow pour les modifications.**

- L'intégration est configurée exclusivement via l'UI HA (Config Flow).
- Les modifications post-installation (ajout/suppression de cultures, changement de stade) passent par l'Options Flow, accessible depuis *Paramètres → Intégrations → Potager Irrigation → Configurer*.
- Aucune configuration YAML n'est supportée en v1.

## Justification

| Critère                        | YAML | Config Flow ✅ | Hybride |
|-------------------------------|------|----------------|---------|
| Accessibilité non-développeur | ✗    | ✓              | Partiel |
| Rechargement sans redémarrage | ✗    | ✓              | Partiel |
| Conformité bonnes pratiques HA 2024+ | ✗ | ✓           | Partiel |
| Complexité d'implémentation   | Faible | Moyenne      | Haute   |

Depuis HA 2023, les nouvelles intégrations sont fortement encouragées à utiliser Config Flow. L'utilisateur cible (jardinier amateur) ne doit pas avoir à éditer des fichiers YAML.

## Conséquences

- **Positives** : installation en quelques clics, modifications sans redémarrage, compatible HACS.
- **Négatives** : la gestion d'une liste variable de cultures dans un Config Flow HA est plus complexe à implémenter qu'un simple YAML (nécessite un flow multi-étapes ou un menu de sélection).
- **Pattern recommandé** : utiliser `OptionsFlowHandler` avec un menu listant les cultures existantes + une option "Ajouter une culture".
- **Migration** : si une v2 supporte YAML, un `import_config_entry_from_yaml` sera implémenté pour ne pas casser les installations existantes.
