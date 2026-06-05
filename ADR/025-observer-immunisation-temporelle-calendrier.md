# 025 — Observer : Immunisation temporelle du calendrier d'intervalle

**Date** : 2026-06-03  
**Statut** : **Remplacé par ADR-028** (le calendrier est désormais réancré uniquement sur arrosage réel ; le principe d'ADR-021 est réactivé)  
**Décideurs** : Équipe projet

**Supersède** : ADR-021 (Conditionnement du calendrier à l'émission effective de l'événement)

---

## Contexte

### L'Anomalie C et ses deux lectures contradictoires

La Règle 3 de la spécification impose que le calendrier d'intervalle (la variable `last_auto_watering_date`) soit mis à jour **dès que le planificateur constate que l'intervalle requis est atteint**, indépendamment du fait que la vanne ait physiquement ouvert ou non. Le calendrier mesure le temps écoulé, pas l'état du sol.

ADR-021 (actuellement "Proposé", non implémenté) proposait l'inverse : conditionner la mise à jour de `last_auto_watering_date` au retour `True` de `fire_irrigation_event()`. Cette décision visait à corriger l'Anomalie C mais a été formulée avant la spécification de la Règle 3. Elle crée en réalité le comportement défaillant décrit dans l'Anomalie C : en cas de pluie (besoin = 0 → `fire_irrigation_event` retourne False), la date n'est pas avancée et le calendrier glisse.

Le code actuel de `coordinator.py::_on_trigger` (L153-161) est **déjà conforme à la Règle 3** : il appelle `fire_irrigation_event()` puis `update_last_watering_date()` inconditionnellement. ADR-021 est donc en contradiction avec le code en place et avec la spécification.

### Le problème de couplage résiduel

Même si le comportement temporel est correct dans le code actuel, le couplage reste fort : `_on_trigger` est à la fois responsable d'avancer le calendrier et de déclencher l'arrosage physique. Ces deux responsabilités n'ont pas le même critère de déclenchement :

| Responsabilité | Condition de déclenchement |
|---|---|
| Avancer le calendrier | Intervalle de jours atteint (toujours) |
| Commander l'arrosage physique | Intervalle atteint **ET** besoin en eau > 0 |

Le pattern Observer formalise cette séparation en rendant explicite que l'événement temporel `WateringIntervalReached` a deux observateurs indépendants.

## Décision

### 1. Supersession d'ADR-021

ADR-021 est déclaré **Obsolète**. La Règle 3 de `spec.md` prime : `last_auto_watering_date` est toujours mise à jour lorsque l'intervalle est atteint, que l'arrosage physique ait eu lieu ou non.

### 2. Introduction de l'événement métier `WateringIntervalReached`

Le `IrrigationScheduler` (ou `_handle_auto_irrigation` dans `scheduler.py`) ne fait que constater que l'échéance temporelle est atteinte. Il notifie ses observateurs via un callback unique plutôt que d'appeler directement le coordinator.

### 3. Deux observateurs indépendants

**Observateur 1 — Gestionnaire de calendrier** (inscrit en premier, exécuté en premier) :

```python
async def _on_interval_reached_calendar(self, date_iso: str) -> None:
    """Met à jour la date du dernier arrosage — inconditionnellement (Règle 3)."""
    await self.update_last_watering_date(date_iso)
```

**Observateur 2 — Centrale agronomique** (inscrit en second) :

```python
async def _on_interval_reached_agronomic(self) -> None:
    """Évalue le besoin et commande la vanne si nécessaire — conditionnellement."""
    if self.data is None:
        _LOGGER.warning("Données météo indisponibles — arrosage physique différé.")
        return
    fired = self.fire_irrigation_event()
    if not fired:
        _LOGGER.info("Besoin nul (pluie ?) — passage du tour, calendrier déjà avancé.")
```

### 4. Remplacement de `_on_trigger`

```python
async def _on_trigger(self, date_iso: str) -> None:
    """Point d'entrée du planificateur : dispatch vers les deux observateurs."""
    await self._on_interval_reached_calendar(date_iso)   # Règle 3 — toujours
    await self._on_interval_reached_agronomic()          # Règle 2+physique — conditionnel
```

Cette décomposition explicite remplace les deux lignes de l'implémentation actuelle tout en rendant la priorité d'exécution auditable : le calendrier avance en premier, la décision agronomique vient ensuite.

### Scénario III validé

D'après `spec.md` Scénario III :
- Jour 3 : `_on_interval_reached_calendar` → `last_auto_watering_date = Jour 3` ✓
- Jour 3 : `_on_interval_reached_agronomic` → besoin = 0 → `fire_irrigation_event` retourne False, aucune vanne ouverte ✓
- Jour 6 : prochain déclenchement automatique (`Jour 3 + 3 jours = Jour 6`) ✓ — pas de glissement

## Justification

- **Séparation des responsabilités** : le calendrier ne sait pas si l'eau a coulé ; la centrale agronomique ne connaît pas la date — chacun fait son travail.
- **Immunisation temporelle** : la date de référence est ancrée sur l'instant de l'évaluation, pas sur la réalisation physique. Le rythme du jardinier est respecté même en cas d'absence de besoin pendant plusieurs cycles.
- **Correction d'ADR-021** : ADR-021 était une régression masquée — il aurait reproduit exactement l'Anomalie C qu'il prétendait corriger. Cette ADR documente pourquoi la décision inverse est correcte.

## Conséquences

- **Positives** : Scénario III est couvert ; le calendrier ne peut plus glisser à cause de la pluie ou d'un besoin nul ; les deux observateurs sont testables indépendamment.
- **Négatives** : `last_auto_watering_date` peut rester inchangée plusieurs cycles consécutifs sans qu'une vanne s'ouvre (comportement voulu, mais à surveiller dans les logs pour détecter d'éventuelles anomalies de calcul en boucle).
- **Note de surveillance** : si les logs affichent "Besoin nul — passage du tour" plus de 5 jours de suite, investiguer le calcul d'évapotranspiration avant de suspecter le calendrier.
- **Relation** : applique la Règle 3 de `spec.md` ; s'articule avec ADR-024 (Strategy) qui calcule le volume dans `_on_interval_reached_agronomic` ; corrige ADR-021.
