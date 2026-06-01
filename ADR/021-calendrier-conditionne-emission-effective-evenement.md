# 021 — Conditionnement du calendrier d'intervalle à l'émission effective de l'événement

**Date** : 2026-06-01  
**Statut** : Proposé  
**Décideurs** : Équipe projet

---

## Contexte

Chaque fois que l'heure planifiée retentit, le callback `_on_trigger` met à jour la variable `last_auto_watering_date` à la date du jour, réinitialisant le délai d'attente en jours (`watering_interval_days`).

Cependant, si le besoin en eau du sol est nul ou négatif, la méthode interne `fire_irrigation_event` coupe court à son exécution et n'émet aucun événement vers la vanne physique. Le cycle d'arrosage est donc annulé, mais le calendrier considère l'événement comme validé : la prochaine évaluation est reportée d'un intervalle complet (plusieurs jours), laissant le sol sans arrosage même si le besoin augmente entre-temps.

## Décision

Modifier la signature de la méthode `fire_irrigation_event` pour retourner un indicateur d'exécution booléen. La mise à jour de la date d'arrosage en mémoire et sur disque devient conditionnelle à cet indicateur : le calendrier n'est avancé que si l'arrosage a effectivement eu lieu.

### Modifications du code source

Dans `custom_components/my_garden_irrigation/coordinator.py` :

```python
def fire_irrigation_event(self) -> bool:
    """Retourne True si l'arrosage est requis et initié, False sinon."""
    data = self.data
    if data is None:
        return False

    total_cumulative = sum(data.cumulative_need.values())
    if total_cumulative <= 0:
        _LOGGER.info("Besoin cumulé nul — cycle d'arrosage automatique sauté.")
        return False

    # ... validation du débit et envoi du signal bus ...
    self.hass.bus.async_fire(f"{DOMAIN}_irrigation_requested", payload)
    return True

async def _on_trigger(self, date_iso: str) -> None:
    """Callback déclenché par le planificateur horaire."""
    # On ne décale le calendrier QUE si l'arrosage a effectivement eu lieu
    if self.fire_irrigation_event():
        await self.update_last_watering_date(date_iso)
    else:
        _LOGGER.info("Calendrier préservé — Nouvelle tentative planifiée pour demain.")
```

## Justification

- **Exactitude sémantique** : `last_auto_watering_date` doit refléter la dernière fois que le sol a réellement reçu de l'eau, non la dernière fois que le planificateur a vérifié le besoin.
- **Réactivité améliorée** : après une pluie qui comble le déficit, le système passe son tour mais se tient prêt dès le lendemain si le sol a de nouveau séché — comportement correct en cas de temps variable.
- **Pas de boucle infinie** : le lendemain, si le besoin est toujours nul, le même mécanisme s'applique ; le cycle ne se déclenche jamais à tort.

## Conséquences

- **Positives** : en cas de pluie ou de sol humide le jour de l'échéance, le système passe son tour mais reste disponible dès le lendemain, au lieu de se bloquer pendant un intervalle complet ; le calendrier reflète fidèlement l'historique réel des arrosages.
- **Négatives** : nécessite une surveillance des logs pour s'assurer qu'aucune anomalie de calcul ne maintienne le système dans un état de déclenchement quotidien en boucle fermée ; la valeur de `last_auto_watering_date` peut rester inchangée plusieurs jours consécutifs.
- **Relation** : dépend de ADR-008 (bilan hydrique cumulé comme critère de déclenchement) et de ADR-013 (testabilité des modules purs — `fire_irrigation_event` doit rester testable sans état HA réel).
