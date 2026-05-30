# 007 — Prise en compte de la pluviométrie (précipitations réelles et effectives)

**Date** : 2026-05-30  
**Statut** : Accepté  
**Décideurs** : Expert Home Assistant / Équipe projet

---

## Contexte

Actuellement, l'intégration calcule le besoin théorique en eau d'une culture exclusivement à partir de l'évapotranspiration ($ETc$). Si une averse de 15 mm (15 L/m²) survient, le capteur de l'intégration continuera d'afficher le même besoin d'arrosage positif, ce qui pousse à la sur-irrigation et au gaspillage d'eau si l'utilisateur crée des automatisations simples.

## Décision

Intégrer les précipitations dans l'équation agronomique pour calculer un besoin d'arrosage net.

### Extraction des données

Modifier l'appel Open-Meteo dans `coordinator.py` pour récupérer également le champ `precipitation_sum` (ou `rain_sum`) de la veille ou du jour courant.

### Calcul révisé

Dans `core/calculations.py`, appliquer la formule de la pluie efficace (estimée à 80 % de la pluie brute pour le potager afin d'exclure le ruissellement) :

$$\text{Pluie Efficace (mm)} = \text{Précipitations (mm)} \times 0{,}8$$

$$\text{Besoin Net (mm)} = \max(0,\ ETc - \text{Pluie Efficace})$$

### Interface

Ajouter un capteur global `sensor.potager_precipitations` dans `sensor.py` pour offrir une visibilité complète à l'utilisateur.

## Justification

Un système d'irrigation moderne et éco-responsable se doit de déduire l'eau gratuite apportée par la nature. Cette fonctionnalité apporte une valeur ajoutée écologique et économique : dès qu'il pleut, les automatisations d'arrosage se réduisent ou s'annulent automatiquement sans intervention de l'utilisateur.

## Conséquences

- **Positives** : économies d'eau massives automatisées dès qu'il pleut ; besoin net toujours ≥ 0 (jamais d'arrosage négatif absurde).
