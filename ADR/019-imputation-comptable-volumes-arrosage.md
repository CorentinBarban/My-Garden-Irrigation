# 019 — Imputation comptable réelle des volumes d'arrosage et préservation du déficit cumulé

**Date** : 2026-06-01  
**Statut** : Proposé  
**Décideurs** : Équipe projet

---

## Contexte

L'intégration calcule le besoin résiduel journalier d'une culture (`daily_need_liters`) en soustrayant le volume déjà arrosé aujourd'hui (`watering_applied_today_liters`) du besoin net théorique de la journée (`net_liters`).

Or, l'arrosage automatique matinal est déclenché pour éponger la dette historique issue du bilan hydrique cumulé (`cumulative_need`). Imputer cette eau sur le besoin propre de la journée courante crée une double déduction erronée : la consommation théorique de la journée est artificiellement masquée, et le sol perd sa mémoire hydrique à minuit.

De plus, la fermeture de la vanne globale réinitialisait aveuglément le déficit cumulé à `0.0`, effaçant l'historique de la dette en cas d'ouverture manuelle courte ou de test technique.

## Décision

1. **Découpler** le besoin net journalier de l'historique des arrosages dans le module de calcul pur. Le besoin net reste le reflet strict de l'évapotranspiration moins la pluie efficace.
2. **Substituer** la remise à zéro inconditionnelle du déficit cumulé par une véritable soustraction arithmétique (Débit / Crédit) lors de la notification de volume d'eau distribué.

### Modifications du code source

Dans `custom_components/my_garden_irrigation/core/calculations.py` :

```python
def compute_crop_result(...) -> CropResult:
    # ... calculs de surface, etc_liters, net_liters ...

    # Le besoin résiduel de la journée est égal au besoin net constaté.
    # L'arrosage matinal ne doit pas effacer la consommation de la journée en cours.
    daily_need_liters = net_liters

    return CropResult(
        # ... champs inchangés ...
        daily_need_liters=round(daily_need_liters, 1),
    )
```

Dans `custom_components/my_garden_irrigation/config_state.py` :

```python
def apply_watering_volumes(self, volumes: dict[str, float]) -> None:
    """Soustrait le volume distribué de la dette accumulée au lieu de tout raser."""
    for crop_id, vol in volumes.items():
        self._watering_applied_today[crop_id] = (
            self._watering_applied_today.get(crop_id, 0.0) + vol
        )
        # Diminution comptable proportionnelle au volume réel
        if crop_id in self._cumulative_need:
            self._cumulative_need[crop_id] = max(0.0, self._cumulative_need[crop_id] - vol)
```

## Conséquences

- **Positives** : précision agronomique stricte ; les sessions d'arrosage partielles ou manuelles n'annulent plus la mémoire de sécheresse du sol ; le bilan hydrique cumulé reflète fidèlement l'état réel du sol entre les cycles.
- **Négatives** : le volume d'arrosage appliqué dans la journée n'est plus déduit visuellement du capteur de besoin instantané du jour même, mais affecte le capteur cumulé — ce qui correspond à la réalité physique du sol.
- **Relation** : complète ADR-008 (bilan hydrique cumulé) et corrige un effet de bord introduit lors des corrections de résilience d'ADR-011 à ADR-015.
