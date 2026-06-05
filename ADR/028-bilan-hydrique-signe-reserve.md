# 028 — Bilan hydrique signé, réserve de pluie, décision inclusive et réancrage sur arrosage réel

**Date** : 2026-06-05
**Statut** : Implémenté
**Décideurs** : Équipe projet

---

## Contexte

Un scénario réel met en défaut le modèle existant : après plusieurs jours de pluie, le
surplus d'eau devrait être **mis en réserve** et consommé les jours suivants pour espacer
ou annuler les arrosages. Or :

1. Le **Besoin Cumulé** était une dette **planchée à 0** (Règle 1 historique, ADR-008/019/023) :
   tout surplus de pluie était perdu, jamais reporté.
2. L'arrosage était imputé **deux fois** — par `apply_watering_volumes` (temps réel) **et**
   par une transaction `IRRIGATION` rejouée à minuit dans `DailyWaterLedger.replay()`. Les
   planchers `max(0, …)` masquaient ce double comptage ; les retirer sans corriger le ferait
   plonger le bilan en négatif à tort à chaque arrosage.
3. La distinction matin/soir du volume cible (ADR-024) n'a plus lieu d'être une fois le
   bilan signé et l'arrosage imputé une seule fois.
4. Le calendrier était réancré dès l'intervalle atteint, **même sans arrosage** (Règle 3,
   ADR-025). Avec une réserve, un jour sauté bloquait alors l'arrosage jusqu'au cycle suivant.

## Décision

Adopter un **bilan hydrique signé** : `cumulative_need` peut être positif (dette) ou
négatif (réserve). Quatre planchers `max(0, …)` sont retirés et la comptabilité de
l'arrosage est rendue unique.

1. **Bilan signé du jour** (`compute_balance_liters`) = `ETc − pluie efficace` (non planché).
   Le besoin affiché (`daily_need_liters`, `liters`) reste `max(0, bilan)` pour l'UI ;
   un champ comptable signé (`daily_balance_liters`, `total_daily_balance_liters`) alimente
   le journal et la décision.
2. **Journal** : la transaction ETo porte le bilan signé ; `replay()` ne somme que les
   apports ETo/pluie (signés) et **exclut l'arrosage** — déjà imputé par
   `apply_watering_volumes`. Plus de double comptage ; corrige aussi un bug latent où le
   besoin du jour était perdu après un arrosage matinal.
3. **Minuit** (`midnight_transfer`) : `cumulé += bilan signé du jour`, sans plancher.
4. **Arrosage** (`apply_watering_volumes`) : `cumulé −= volume distribué`, sans plancher
   (un sur-arrosage crée une réserve). Point d'imputation **unique**.
5. **Décision inclusive unique** (`InclusiveWateringStrategy`, remplace ADR-024) :
   `volume = max(0, cumulé + bilan net du jour)`, à toute heure.
6. **Réancrage sur arrosage réel** (`_on_trigger`, remplace la Règle 3 d'ADR-025,
   réactive le principe d'ADR-021) : la `last_auto_watering_date` n'avance que si
   `fire_irrigation_event()` retourne `True`. Un saut (réserve/pluie) → réévaluation demain.

## Conséquences

- **Positives** : mémoire hydrique complète du sol (déficit ET surplus) ; arrosages
  réellement espacés après la pluie ; comptabilité de l'arrosage à source unique ;
  modèle de volume simplifié (plus de matin/soir).
- **Négatives** : le « glissement quotidien » que l'Anomalie C d'ADR-025 voulait éviter
  devient le comportement voulu (réévaluation quotidienne tant que la réserve couvre) ;
  le bilan cumulé peut afficher des valeurs négatives (réserve) — assumé.
- **Relation** : **remplace ADR-024 et ADR-025** ; réactive le principe d'**ADR-021** ;
  amende **ADR-008 / 019 / 023 / 026** (planchers retirés, arrosage exclu de `replay`) ;
  conserve **ADR-007** (facteur de pluie efficace 0,8). Réécrit les Règles 1-3 et les
  Scénarios I-IV de `spec.md`. Couvert par `tests/test_water_reserve_scenario.py`.
