# 017 — Paramètres configurables du mode fractionné (Cycle & Soak)

**Date** : 2026-06-01  
**Statut** : Accepté  
**Décideurs** : Équipe projet

---

## Contexte

L'ADR-010 a introduit le mode fractionné (_Cycle & Soak_) : au lieu d'arroser d'une seule traite, l'intégration fractionne la durée totale en plusieurs cycles entrecoupés de pauses pour favoriser l'infiltration. Ce mode est particulièrement utile sur sols argileux ou en pente.

L'implémentation initiale codait en dur deux paramètres opérationnels :

- **Nombre de cycles** : 3 (constante dans `scheduler.py`)
- **Durée de repos entre cycles** : 15 minutes (constante dans `scheduler.py`)

Ces valeurs conviennent à un sol argileux standard, mais un sol sableux n'a besoin que d'1-2 cycles ; un potager en terrasse peut nécessiter 30 minutes de repos. L'impossibilité de modifier ces paramètres depuis l'interface contraint l'utilisateur à éditer le code source ou à accepter un programme sous-optimal.

## Décision

Exposer `cycles_count` et `soak_duration_minutes` comme paramètres configurables dans le Config Flow du potager.

### Nouvelles constantes (`const.py`)

```python
CONF_CYCLES_COUNT = "cycles_count"
CONF_SOAK_DURATION = "soak_duration_minutes"
DEFAULT_CYCLES_COUNT = 3
DEFAULT_SOAK_DURATION_MINUTES = 15
```

### Formulaire dynamique (`config_flow.py`)

Dans `async_step_watering_config`, le schéma Voluptuous s'enrichit conditionnellement lorsque `watering_mode == WATERING_MODE_FRACTIONED` :

```python
if user_input.get(CONF_WATERING_MODE) == WATERING_MODE_FRACTIONED:
    schema = schema.extend({
        vol.Optional(CONF_CYCLES_COUNT, default=DEFAULT_CYCLES_COUNT):
            vol.All(int, vol.Range(min=1, max=10)),
        vol.Optional(CONF_SOAK_DURATION, default=DEFAULT_SOAK_DURATION_MINUTES):
            vol.All(int, vol.Range(min=5, max=60)),
    })
```

Les deux champs n'apparaissent pas si le mode continu est sélectionné.

### Stockage dans `RuntimeConfigState`

`RuntimeConfigState` expose `cycles_count: int` et `soak_duration_minutes: int` lus depuis `entry.options` avec valeurs par défaut. Ces valeurs sont accessibles par `IrrigationScheduler` via `config.cycles_count` et `config.soak_duration_minutes` — sans changement d'interface du scheduler (ADR-012).

### Attributs du capteur (`sensor.py`)

Le capteur `TotalCumulativeNeedSensor` expose `cycles_count` et `soak_duration_minutes` comme attributs de diagnostic (au lieu des valeurs codées en dur). Les blueprints et automatisations existants qui lisent ces attributs continuent de fonctionner sans modification.

### i18n

Les clés `cycles_count` et `soak_duration_minutes` sont déclarées dans `strings.json` et traduits en `fr`, `en`, `es`, `it`, `de`.

## Justification

- **Agronomie terrain** : le nombre de cycles optimal dépend de la perméabilité du sol, de la pente et du débit de l'arroseur. Fixer ces valeurs en dur rend le mode fractionné inutilisable pour une large fraction des configurations de jardins.
- **Cohérence avec ADR-010** : l'ADR-010 posait le principe du mode fractionné et mentionnait explicitement `cycles_count` comme attribut exposable — cette ADR finalise la décision en le rendant paramétrable plutôt qu'exposé en dur.
- **Aucun impact sur les algorithmes** : les formules FAO-56 et le calcul du volume total restent inchangés ; seule la segmentation temporelle de ce volume est paramétrée.

## Conséquences

- **Positives** : l'utilisateur choisit le fractionnement adapté à son sol sans toucher au code ; les valeurs apparaissent dans les attributs du capteur et dans le formulaire de configuration de manière cohérente.
- **Négatives** : ajouter des champs conditionnels dans le Config Flow augmente légèrement la complexité du formulaire. Le risque de confusion (pourquoi ces champs n'apparaissent-ils pas en mode continu ?) est mitigé par les descriptions i18n.
- **Relation** : étend ADR-010 (modes d'arrosage) ; les valeurs sont lues par `IrrigationScheduler` via `RuntimeConfigState` (ADR-011, ADR-012).
