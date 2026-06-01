# 015 — Rescalage proportionnel du bilan hydrique lors de modification d'une culture

**Date** : 2026-05-31  
**Statut** : Accepté  
**Décideurs** : Équipe projet

---

## Contexte

Le bilan hydrique cumulé (`cumulative_need` par culture, ADR-008) accumule quotidiennement le déficit en eau calculé d'après les formules FAO-56. Ce déficit est proportionnel à la surface plantée (`compute_surface_m2 = nb_plants / density`).

Lorsque l'utilisateur modifie le nombre de plants (`nb_plants`) ou la densité de plantation (`density`) via les entités HA correspondantes, la formule de calcul s'actualise immédiatement au prochain refresh du coordinator. Cependant, le cumulatif accumulé depuis le dernier arrosage restait à sa valeur d'avant la modification, créant une incohérence :

**Exemple** : 10 tomates, cumulatif = 30 L (3 jours d'ETo) → passage à 20 tomates → `daily_need_liters` double, mais `cumulative_need["c1"]` reste 30 L au lieu de 60 L. Le sensor affiche un besoin sous-estimé.

Par ailleurs, modifier le stade de croissance (`stage`) change le coefficient cultural Kc mais pas la surface. Le cumulatif n'a pas besoin d'être rescalé, mais le coordinator doit quand même rafraîchir les sensors.

## Décision

Introduire `IrrigationCoordinator.async_update_crop_field()` — méthode action utilisateur distincte de `update_crop_field()` (réservée à la restauration au boot) :

### Logique de rescalage

Pour les champs qui modifient la **surface** (`CONF_NB_PLANTS`, `CONF_DENSITY`) :

$$\text{cumulative\_need\_new}[c] = \text{cumulative\_need}[c] \times \frac{S_{\text{new}}}{S_{\text{old}}}$$

où $S = \text{nb\_plants} / \text{density}$ (en m²).

Si l'ancienne surface est nulle (cas limite), aucun rescalage n'est effectué.

Pour les champs qui modifient le **Kc** (`CONF_STAGE`, `CONF_CROP_TYPE`) : pas de rescalage — le cumulatif passé reste valide puisque la surface n'a pas changé.

Dans tous les cas : sauvegarde en Store + `async_refresh()` immédiat pour que les sensors reflètent les nouvelles valeurs sans attendre le prochain cycle horaire.

### Séparation boot vs action utilisateur

`update_crop_field()` (sync, sans refresh) est conservé pour `async_added_to_hass()` — lors du boot, la restauration depuis le Store est déjà cohérente et ne doit pas déclencher de rescalage.

## Justification

- **Cohérence sémantique** : si j'ai 10 plants avec 30 L de dette accumulée, passer à 20 plants signifie que cette même période d'ETo aurait produit 60 L de dette. Le rescalage proportionnel traduit fidèlement ce fait.
- **Immédiat** : `async_refresh()` (et non le `async_request_refresh()` rate-limité) garantit que les sensors sont à jour dès que la modification est enregistrée.
- **Sans perte d'historique** : contrairement à un reset complet du cumulatif, le rescalage préserve le nombre de jours de déficit représenté.

## Conséquences

- **Positives** : les sensors de besoin cumulé restent cohérents immédiatement après toute modification de culture, sans attendre le lendemain.
- **Négatives** : le rescalage est une approximation — il suppose que les conditions météo des jours précédents auraient été identiques avec le nouveau nombre de plants. Si l'utilisateur divise sa culture par 2, la moitié de la dette historique est considérée comme non pertinente, ce qui est une approximation raisonnable.
