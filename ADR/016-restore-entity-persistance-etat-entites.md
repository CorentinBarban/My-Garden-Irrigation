# 016 — RestoreEntity comme mécanisme de persistance d'état des entités de configuration

**Date** : 2026-06-01  
**Statut** : Accepté  
**Décideurs** : Équipe projet

---

## Contexte

Les entités `NbPlantsNumber`, `DensityNumber` et `StageSelect` permettent à l'utilisateur de modifier les paramètres agronomiques de chaque culture (nombre de plants, densité de plantation, stade de croissance) directement depuis le tableau de bord HA.

L'implémentation initiale utilisait `hass.config_entries.async_update_entry(entry, options={…})` pour persister ces modifications. Ce choix présentait deux problèmes graves :

1. **Rechargements intempestifs** : `async_update_entry` sur les options déclenche systématiquement `_async_reload_entry` via le listener HA standard. L'intégration masquait ce comportement par un drapeau interne `OPTIONS_FIELD_UPDATE_FLAG` intercepté dans `__init__.py` — un hack fragile dont la suppression était requise.
2. **Violation du contrat HA Core** : `entry.options` est réservé aux paramètres définis par l'utilisateur via le Config Flow. Les valeurs d'état opérationnel (combien de plants j'ai aujourd'hui, à quel stade sont mes tomates) ne sont pas des options de configuration — ce sont des données d'exécution.

## Décision

Faire hériter les entités `NbPlantsNumber`, `DensityNumber` et `StageSelect` de `homeassistant.helpers.restore_state.RestoreEntity` et implémenter `async_added_to_hass()` pour récupérer le dernier état HA via `await self.async_get_last_state()`.

### Mécanisme de restauration

```python
async def async_added_to_hass(self) -> None:
    await super().async_added_to_hass()
    last_state = await self.async_get_last_state()
    if last_state is not None and last_state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        value = int(last_state.state)  # ou float / str selon l'entité
        self.coordinator.config.update_crop_field(self._crop_id, CONF_NB_PLANTS, value)
    self.async_write_ha_state()
```

### Suppression du hack OPTIONS_FIELD_UPDATE_FLAG

La constante `OPTIONS_FIELD_UPDATE_FLAG` et le bloc de filtrage dans `__init__.py._async_reload_entry` sont supprimés. `config_flow.py` cesse de stocker les valeurs de culture dynamiques dans `entry.options`.

### Source de vérité à l'exécution

`RuntimeConfigState` (ADR-011) reste la source de vérité pendant l'exécution. `RestoreEntity` gère uniquement la récupération de l'état après redémarrage, avant que le coordinator ne soit disponible.

## Justification

- **Conformité HA Core** : `RestoreEntity` est le mécanisme officiel pour les entités dont l'état doit survivre aux redémarrages sans recharger l'intégration. Son usage est explicitement recommandé pour les entités `Number` et `Select` portant de l'état applicatif.
- **Suppression du hack** : éliminer `OPTIONS_FIELD_UPDATE_FLAG` retire un point de fragilité ; tout rechargement d'intégration est désormais intentionnel.
- **Séparation claire** : options de configuration (immuables hors Config Flow) vs état opérationnel (mutable via entités HA, restauré par `RestoreEntity`).

## Conséquences

- **Positives** : plus de rechargements parasites lors de la modification d'une culture ; `entry.options` ne contient plus que les vrais paramètres de configuration (coordonnées, vanne, fréquence, mode).
- **Négatives** : `RestoreEntity` repose sur la table d'états HA (`recorder`). Si le recorder est désactivé, l'état n'est pas restauré au démarrage et les cultures reprennent leurs valeurs par défaut — comportement attendu et documenté dans HA.
- **Relation** : remplace partiellement la logique de restauration de `RuntimeConfigState.restore_from_storage()` pour les champs de culture dynamiques ; les deux mécanismes coexistent (Store HA pour le bilan hydrique, RestoreEntity pour les paramètres de culture).
