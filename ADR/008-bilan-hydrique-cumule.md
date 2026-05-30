# 008 — Persistence du Bilan Hydrique Cumulé (Gestion du déficit en eau)

**Date** : 2026-05-30  
**Statut** : Proposé  
**Décideurs** : Expert Home Assistant / Équipe projet  

---

## Contexte

Actuellement, l'intégration recalcule les données toutes les heures et affiche le besoin du jour courant. Si le capteur indique qu'il faut 5 L le lundi et que l'utilisateur n'arrose pas (ou que son automatisation ne se déclenche pas), le mardi le capteur affichera uniquement le besoin du mardi (par exemple 6 L). Le déficit du lundi (5 L) est totalement oublié par le système. Le sol n'ayant pas de mémoire logicielle ici, les plantes accumulent un stress hydrique critique.

## Décision

Passer d'un modèle « sans état » à un modèle de **Bilan Hydrique Cumulé** (*Soil Water Deficit tracking*).

### Deux valeurs exposées par zone

L'intégration maintient et expose deux grandeurs distinctes pour chaque zone :

| Grandeur | Description | Mise à jour | Remise à zéro |
|---|---|---|---|
| **Besoin hydrique journalier** | Besoin net du jour = ETP − pluie du jour − arrosage réalisé dans la journée | En continu (chaque cycle coordinateur) | Chaque nuit à minuit |
| **Besoin hydrique cumulé** | Cumul des besoins journaliers non satisfaits depuis le dernier arrosage | Chaque nuit à minuit | À chaque fermeture de la vanne globale |

Le **volume d'arrosage journalier** n'est pas exposé en tant que capteur dédié : il est fourni en temps réel par la vanne globale (ADR 009) et déduit directement du besoin journalier lors de chaque mise à jour du coordinateur.

### Mémoire de l'état

Utiliser la capacité de Home Assistant à restaurer l'état des capteurs au redémarrage via `RestoreEntity`. Seul le **bilan cumulé** nécessite cette persistance ; le besoin journalier est recalculé à la volée.

### Algorithme de calcul journalier

Le besoin hydrique journalier est calculé en continu à chaque cycle du coordinateur :

$$\text{Besoin Journalier} = \max(0,\ \text{ETP} - \text{Pluie du jour} - \text{Volume arrosage du jour})$$

Le volume d'arrosage du jour est fourni automatiquement par la vanne globale (ADR 009) au prorata de la surface de chaque culture.

### Algorithme d'accumulation du cumulé

Chaque nuit à minuit, le besoin journalier résiduel de la veille est ajouté au bilan cumulé :

$$\text{Cumulé}_t = \text{Cumulé}_{t-1} + \text{Besoin Journalier}_{t-1}$$

À chaque fermeture de la vanne globale, le **bilan cumulé est remis à zéro** car le besoin journalier intègre déjà l'arrosage réalisé — si l'arrosage couvre le déficit, le besoin journalier tombe à 0 et rien ne s'accumule au prochain minuit.

## Justification

C'est la fonctionnalité reine des logiciels professionnels de gestion de l'irrigation (méthode du bilan hydrique FAO). Elle permet d'espacer les arrosages — par exemple, arroser abondamment tous les 3 jours plutôt qu'un peu tous les jours — ce qui favorise l'enracinement profond des cultures tout en s'assurant qu'aucun déficit n'est oublié.

## Conséquences

- **Positives** : fiabilité agronomique absolue ; gestion de plannings d'arrosage complexes (ex. interdiction d'arroser certains jours de la semaine sans perdre le fil des besoins du potager).
- **Négatives** : complexité algorithmique plus élevée ; nécessite que l'utilisateur configure la vanne globale (ADR 009) pour que le suivi du volume arrosé soit automatique — sans cette vanne, l'arrosage réalisé n'est pas pris en compte dans le besoin journalier.
