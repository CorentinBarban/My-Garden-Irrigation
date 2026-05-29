# My Garden Irrigation — Intégration Home Assistant

## Présentation

**My Garden Irrigation** est une intégration custom pour Home Assistant qui calcule automatiquement les besoins en eau de chaque culture de votre potager, en temps réel et sans abonnement.

Elle combine les données météo locales déjà disponibles dans votre installation Home Assistant avec les coefficients culturaux de référence de la FAO (Food and Agriculture Organization), pour vous dire précisément combien de litres arroser — par culture, par jour, par semaine.

---

## Le problème qu'elle résout

Arroser un potager à l'instinct, c'est souvent trop ou pas assez. Trop d'eau favorise les maladies fongiques et gaspille une ressource précieuse. Pas assez, et les rendements s'effondrent.

Les besoins en eau varient selon la culture (une tomate n'a pas les mêmes exigences qu'une carotte), le stade de croissance (une plante en fleur boit plus qu'un semis), et les conditions météo du moment (une canicule multiplie les besoins par deux). Gérer tout cela manuellement est fastidieux.

**My Garden Irrigation automatise ce raisonnement agronomique** et l'intègre directement dans votre domotique.

---

## Comment ça fonctionne

L'intégration s'appuie sur la formule de référence mondiale en agronomie (FAO Paper 56) :

```
ETc = Kc × ETo
```

- **ETo** — l'évapotranspiration de référence du jour, issue de votre source météo Home Assistant (Open-Meteo, station locale, etc.), en mm/jour
- **Kc** — le coefficient cultural propre à chaque plante et à son stade de croissance, récupéré depuis un fichier de référence FAO hébergé en ligne
- **ETc** — le besoin en eau réel de la culture, converti en litres selon la surface occupée

La surface de chaque culture est calculée à partir du **nombre de plants** que vous avez et de leur densité de plantation, ce qui est plus naturel que de mesurer des mètres carrés.

---

## Ce que vous obtenez dans Home Assistant

Pour chaque culture configurée, l'intégration crée un sensor dédié :

- `sensor.potager_tomate_litres_jour` 
- `sensor.potager_carotte_litres_jour`
- `sensor.potager_total_litres_jour`

Chaque sensor expose des attributs détaillés : litres par plant, surface calculée, coefficient Kc utilisé, projection hebdomadaire.

Ces entités s'utilisent comme n'importe quel sensor HA : dans vos **automatisations** (déclencher une électrovanne quand le besoin dépasse un seuil), vos **dashboards Lovelace**, ou vos **notifications** matinales.

---

## Cultures supportées

Tomate · Carotte · Haricot vert · Poivron · Laitue · Courgette · Oignon

D'autres cultures peuvent être ajoutées via le fichier de données FAO, sans mise à jour du code.

---

## Installation et configuration

L'intégration s'installe via **HACS** en quelques clics. La configuration se fait entièrement depuis l'interface Home Assistant :

1. Pouvoir recuperer les données depuis Open-Meteo
2. Ajouter ses cultures, avec le nombre de plants et le stade de croissance
3. C'est tout — les sensors apparaissent immédiatement


---

## Prérequis

- Home Assistant 2024.1 ou supérieur
- HACS installé

---
