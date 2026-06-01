# 018 — Délégation du pilotage matériel à un Blueprint HA natif

**Date** : 2026-06-01  
**Statut** : Accepté  
**Décideurs** : Équipe projet

---

## Contexte

L'implémentation initiale du mode fractionné gérait la séquence d'ouverture et de fermeture de la vanne directement dans le coordinator via `_irrigation_sequence_task` :

```python
async def _irrigation_sequence_task(self, ...):
    for cycle in range(cycles_count):
        await hass.services.async_call("switch", "turn_on", {"entity_id": valve})
        await asyncio.sleep(duration_per_cycle_seconds)
        await hass.services.async_call("switch", "turn_off", {"entity_id": valve})
        if cycle < cycles_count - 1:
            await asyncio.sleep(soak_duration_seconds)
```

Cette architecture présente deux défauts critiques :

1. **Absence de résilience** : si Home Assistant redémarre ou subit une coupure de courant pendant un cycle, la boucle `asyncio` est tuée. La vanne peut rester ouverte indéfiniment (risque d'inondation) ou ne jamais s'ouvrir (manque d'eau).
2. **Responsabilité incorrecte** : une intégration HA ne doit pas gérer directement des états matériels temporels. C'est le rôle des automatisations HA, conçues précisément pour être resilientes aux redémarrages via leur moteur d'état interne.

## Décision

Supprimer `_irrigation_sequence_task` et toute gestion directe de la vanne depuis l'intégration Python. L'intégration se concentre sur ce qu'elle fait bien — calcul agronomique — et délègue entièrement l'exécution matérielle à un Blueprint HA natif.

### 1. Suppression du code de pilotage

`_irrigation_sequence_task`, les appels `hass.services.async_call("switch", "turn_on/off", …)` et les `asyncio.sleep()` associés sont supprimés de `coordinator.py` et `scheduler.py`.

### 2. Exposition exhaustive des attributs de diagnostic (`sensor.py`)

Le capteur `TotalCumulativeNeedSensor` expose l'intégralité des paramètres de séquençage comme attributs :

| Attribut | Type | Description |
|---|---|---|
| `recommended_duration_minutes` | `float` | Durée totale cumulée de fonctionnement |
| `is_fractioned` | `bool` | `true` si mode fractionné activé |
| `cycles_count` | `int` | Nombre de cycles (ADR-017) |
| `duration_per_cycle_minutes` | `float` | Durée par cycle = durée totale ÷ cycles |
| `soak_duration_minutes` | `int` | Repos entre cycles (ADR-017) |
| `next_watering` | `datetime` | Date/heure du prochain arrosage recommandé |

Ces attributs sont la seule interface entre l'intégration et les automatisations de l'utilisateur.

### 3. Blueprint `watering_blueprint.yaml`

Un fichier Blueprint standard HA est fourni dans le dépôt. Il lit les attributs du capteur et orchestre la vanne globale via les services HA natifs. La structure de déclenchement gère nativement la reprise sur panne :

```yaml
blueprint:
  name: "My Garden Irrigation — Arrosage automatique"
  domain: automation
  input:
    sensor_entity:
      selector:
        entity:
          integration: my_garden_irrigation
    valve_entity:
      selector:
        entity:
          domain: switch

trigger:
  - platform: state
    entity_id: !input sensor_entity
    attribute: next_watering

action:
  - variables:
      is_frac: "{{ state_attr(sensor, 'is_fractioned') }}"
      cycles: "{{ state_attr(sensor, 'cycles_count') | int }}"
      cycle_min: "{{ state_attr(sensor, 'duration_per_cycle_minutes') | float }}"
      soak_min: "{{ state_attr(sensor, 'soak_duration_minutes') | int }}"
  - repeat:
      count: "{{ cycles }}"
      sequence:
        - service: switch.turn_on
          target:
            entity_id: !input valve_entity
        - delay:
            minutes: "{{ cycle_min }}"
        - service: switch.turn_off
          target:
            entity_id: !input valve_entity
        - if:
            - condition: template
              value_template: "{{ repeat.index < cycles }}"
          then:
            - delay:
                minutes: "{{ soak_min }}"
```

Le moteur d'automatisation HA gère nativement le redémarrage : si HA redémarre pendant un `delay`, la vanne est fermée par le service de démarrage HA avant que le blueprint ne reprenne.

## Justification

- **Résilience matérielle** : le moteur d'automatisation HA est conçu pour les scénarios de reprise sur panne. Déléguer le pilotage de la vanne à une automatisation garantit que la vanne sera fermée même en cas de coupure de courant ou de redémarrage inopiné.
- **Responsabilité unique** : l'intégration calcule, le Blueprint exécute. Cette séparation est conforme aux guidelines HA Core et facilite les tests unitaires (aucun `hass.services.async_call` à mocker).
- **Flexibilité utilisateur** : l'utilisateur peut personnaliser ou remplacer le Blueprint (notifications, interverrouillage avec la météo, conditions sur un capteur de pluie) sans modifier le code Python de l'intégration.
- **Éligibilité HA Core** : les intégrations acceptées dans HA Core ne pilotent pas directement du matériel depuis un coordinator — elles exposent des données et laissent les automatisations orchestrer.

## Conséquences

- **Positives** : suppression d'environ 80 lignes de code fragile ; résilience matérielle assurée par le moteur HA natif ; l'intégration devient éligible à une inclusion dans HA Core.
- **Négatives** : l'utilisateur doit importer le Blueprint et le configurer une fois (étape manuelle). La séquence ne démarre plus automatiquement après calcul — c'est une automatisation explicite qui la déclenche. Ce changement est documenté dans le README comme un choix délibéré de sécurité.
- **Relation** : dépend de ADR-010 (attributs `is_fractioned`, `cycles_count`, `duration_per_cycle_minutes`) et ADR-017 (paramètres configurables exposés comme attributs) ; retire la responsabilité de pilotage de `IrrigationScheduler` (ADR-012).
