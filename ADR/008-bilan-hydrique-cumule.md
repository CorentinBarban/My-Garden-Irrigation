# 008 — Persistence du Bilan Hydrique Cumulé (Gestion du déficit en eau)

**Date** : 2026-05-30  
**Statut** : Proposé  
**Décideurs** : Expert Home Assistant / Équipe projet  

---

## Contexte

Actuellement, l'intégration recalcule les données toutes les heures et affiche le besoin du jour courant. Si le capteur indique qu'il faut 5 L le lundi et que l'utilisateur n'arrose pas (ou que son automatisation ne se déclenche pas), le mardi le capteur affichera uniquement le besoin du mardi (par exemple 6 L). Le déficit du lundi (5 L) est totalement oublié par le système. Le sol n'ayant pas de mémoire logicielle ici, les plantes accumulent un stress hydrique critique.

## Décision

Passer d'un modèle « sans état » à un modèle de **Bilan Hydrique Cumulé** (*Soil Water Deficit tracking*).

### Mémoire de l'état

Utiliser la capacité de Home Assistant à restaurer l'état des capteurs au redémarrage via `RestoreEntity`.

### Algorithme d'accumulation

Chaque jour à minuit, le besoin non satisfait de la veille est ajouté au déficit cumulé de la zone :

$$\text{Déficit}_t = \text{Déficit}_{t-1} + \text{Besoin Journalier}_t - \text{Arrosage Réalisé}_t$$

### Création d'un service d'arrosage

Enregistrer un service Home Assistant (ex. `my_garden_irrigation.log_irrigation`) dans `__init__.py`. Lorsque l'utilisateur arrose (via une automatisation connectée à une vanne), ce service est appelé avec la quantité de litres fournie, ce qui vient déduire et apurer le déficit accumulé.

## Justification

C'est la fonctionnalité reine des logiciels professionnels de gestion de l'irrigation (méthode du bilan hydrique FAO). Elle permet d'espacer les arrosages — par exemple, arroser abondamment tous les 3 jours plutôt qu'un peu tous les jours — ce qui favorise l'enracinement profond des cultures tout en s'assurant qu'aucun déficit n'est oublié.

## Conséquences

- **Positives** : fiabilité agronomique absolue ; gestion de plannings d'arrosage complexes (ex. interdiction d'arroser certains jours de la semaine sans perdre le fil des besoins du potager).
- **Négatives** : complexité algorithmique plus élevée ; demande à l'utilisateur de lier ses automatisations de vannes à l'intégration via l'appel de service pour que le système sache quand et combien d'eau a été versée.
