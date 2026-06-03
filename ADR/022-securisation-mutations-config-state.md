# 022 — Sécurisation des mutations d'états et programmation défensive dans RuntimeConfigState

**Date** : 2026-06-01  
**Statut** : Implémenté  
**Décideurs** : Équipe projet

---

## Contexte

La classe `RuntimeConfigState` fait office de conteneur d'états mutables. Ses méthodes de modification (`set_cycles_count`, `set_flow_rate`, etc.) reçoivent des entrées typées issues des entités graphiques du tableau de bord HA ou du fichier de configuration persisté, sans en valider les bornes logiques.

L'injection d'un nombre de cycles négatif ou nul, ou d'un débit inférieur à zéro, provoque des divisions par zéro dans les calculs d'attributs de `sensor.py` ou des comportements indéterminés dans les automatisations matérielles. Ces valeurs aberrantes peuvent provenir d'une saisie utilisateur directe, d'un fichier de restauration corrompu ou d'une régression dans un test unitaire.

## Décision

Implémenter des verrous sanitaires stricts directement dans les méthodes de mutation de `RuntimeConfigState` pour interdire l'affectation de valeurs hors plage logique. La protection est centralisée au niveau du setter, ce qui garantit que toute voie d'entrée (UI, restauration, test) bénéficie du même garde-fou.

### Modifications du code source

Dans `custom_components/my_garden_irrigation/config_state.py` :

```python
def set_cycles_count(self, value: int) -> None:
    """Garantit un nombre de cycles supérieur ou égal à 1."""
    self._cycles_count = max(1, int(value))

def set_flow_rate(self, value: float) -> None:
    """Garantit l'absence de débit négatif."""
    self._flow_rate = max(0.0, float(value))

def set_watering_interval_days(self, value: int) -> None:
    """Garantit un intervalle minimum d'un jour."""
    self._watering_interval_days = max(1, int(value))

def set_soak_duration_minutes(self, value: int) -> None:
    """Garantit l'absence de durée de ressuyage négative."""
    self._soak_duration_minutes = max(0, int(value))
```

Les appels `int()` et `float()` garantissent en outre le rejet silencieux des chaînes de caractères mal converties issues du stockage JSON.

## Justification

- **Robustesse aux entrées corrompues** : un fichier `.storage` partiellement corrompu ou une saisie utilisateur inattendue ne peut plus provoquer de crash dans le cycle de calcul agronomique.
- **Centralisation de la logique de validation** : le setter est le seul endroit où la contrainte est encodée ; les appelants (coordinator, config flow, tests) n'ont pas à implémenter leurs propres guards.
- **Conformité aux guidelines HA** : les intégrations HA doivent tolérer des états de démarrage dégradés sans lever d'exception non gérée.

## Conséquences

- **Positives** : protection globale du cycle de calcul contre les corruptions de données et les erreurs de saisie ; suppression des risques de division par zéro lors du calcul de `duration_per_cycle_minutes = total_duration / cycles_count` dans les capteurs.
- **Négatives** : les tests unitaires qui passent délibérément des valeurs invalides (ex. `cycles_count=0`) verront leurs configurations redressées à la borne minimale plutôt que levées en erreur — les tests doivent vérifier le comportement en entrée valide ou tester explicitement la borne minimale.
- **Relation** : renforce la testabilité introduite dans ADR-013 ; protège les attributs exposés par ADR-017 (paramètres configurables du mode fractionné) et ADR-018 (attributs consommés par le Blueprint).
