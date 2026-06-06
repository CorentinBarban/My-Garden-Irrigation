# 🌿 My Garden Irrigation — Intégration Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![quality_scale](https://img.shields.io/badge/Quality%20Scale-Silver-lightgrey.svg)](https://developers.home-assistant.io/docs/core/integration-quality-scale/)
Version : 1.0.0

**My Garden Irrigation** (`my_garden_irrigation`) est une intégration personnalisée pour Home Assistant qui calcule les besoins en eau des cultures d'un potager et pilote leur arrosage. Elle s'appuie sur la méthode d'évapotranspiration de la publication **FAO Irrigation and Drainage Paper 56**.

L'intégration récupère l'évapotranspiration de référence (ETo) et la pluviométrie quotidiennes via l'API **Open-Meteo**, et télécharge les coefficients culturaux (Kc) depuis un référentiel distant. Son mode de fonctionnement repose sur le principe du *cloud polling*.

---

## 📐 Principe de calcul

### Besoin brut du jour

L'estimation repose sur la formule d'agronomie standard :

```
ETc = Kc × ETo
```

- **ETo** : évapotranspiration de référence journalière (mm/jour), issue d'Open-Meteo.
- **Kc** : coefficient cultural propre à chaque plante, indexé selon son stade de croissance.
- **ETc** : besoin en eau brut, converti en litres selon la surface occupée.

La surface d'une parcelle est automatiquement déduite à partir du **nombre de plants** et de la **densité de plantation** (plants par m²).

### Bilan hydrique signé et réserve de pluie

L'intégration tient une **comptabilité hydrique signée** du sol, qui mémorise aussi bien le déficit que le surplus :

```
Bilan du jour = ETc − pluie efficace
Besoin cumulé += bilan du jour          (à minuit)
Besoin cumulé −= volume réellement arrosé
```

- Le **besoin cumulé** peut être **positif** (dette : le sol a soif) ou **négatif** (réserve : surplus de pluie reporté sur les jours suivants).
- Après plusieurs jours de pluie, la **réserve** constituée espace ou annule automatiquement les arrosages suivants, jusqu'à épuisement.
- La pluie n'est retenue qu'à hauteur de son **efficacité réelle** (facteur 0,8 sur la pluie brute).
- Le volume effectivement distribué est imputé **une seule fois** au bilan, garantissant une comptabilité fiable.

> Le besoin affiché à l'utilisateur reste plafonné à 0 (`max(0, bilan)`), tandis que le bilan signé pilote en interne la décision d'arroser ou non.

---

## 📊 Entités générées

### 🔍 Capteurs (`sensor`)

**Par parcelle de culture :**

- **Irrigation** : volume requis du jour (litres), avec une liste d'attributs détaillés :
  - `crop_type`, `stage` : type de culture et stade actuel.
  - `nb_plants`, `density_plants_per_m2`, `surface_m2` : géométrie de la parcelle.
  - `kc`, `eto_mm` : valeurs agronomiques du jour.
  - `precipitation_mm`, `effective_rainfall_mm` : pluie brute et pluie efficace retenue.
  - `etc_liters`, `net_liters` : besoin brut et bilan net du jour.
  - `watering_applied_today_liters` : volume déjà distribué aujourd'hui.
  - `cumulative_need_liters` : besoin hydrique cumulé (signé).
  - `recommended_duration_minutes` : durée d'arrosage recommandée selon le débit configuré.
  - `liters_per_plant`, `weekly_projection_l` : indicateurs de suivi.
  - **Mode fractionné** (si activé) : `is_fractioned`, `cycles_count`, `duration_per_cycle_minutes`, `soak_duration_minutes`.
- **Kc** et **ETo** : valeurs agronomiques exposées individuellement.
- **Besoin cumulé** : bilan signé propre à la parcelle.

**Au niveau du potager (centrale) :**

- **Besoin journalier** : somme des besoins du jour de toutes les parcelles.
- **Besoin cumulé** : bilan hydrique signé global.
- **Précipitations journalières** : pluviométrie du jour (mm).
- **Prochain arrosage** : date/heure du prochain arrosage planifié.

### ⚙️ Contrôles numériques (`number`)

`Nombre de plants` · `Densité (plants/m²)` · `Débit de l'installation` · `Intervalle entre arrosages` · `Nombre de cycles` · `Repos entre cycles`.

### 🎛️ Sélecteurs (`select`)

`Stade de croissance` · `Fréquence d'arrosage` · `Mode d'arrosage`.

### 🔘 Boutons (`button`)

- **Lancer l'arrosage maintenant** : déclenche immédiatement un arrosage.
- **Réinitialiser l'irrigation** : remet à zéro le bilan hydrique cumulé.

### 🔀 Interrupteur (`switch`) et 🕒 Heure (`time`)

- **Arrosage automatique** : active/désactive l'émission automatique de l'événement d'arrosage.
- **Heure d'arrosage** : heure quotidienne de déclenchement automatique.

Toutes ces entités sont ajustables dynamiquement depuis vos tableaux de bord Lovelace.

---

## 🥕 Cultures prises en charge

L'intégration intègre nativement les densités de plantation par défaut (plants/m²) pour **27 cultures** issues du référentiel FAO :

Ail · Artichaut · Asperge · Aubergine · Basilic · Betterave · Brocoli · Carotte · Céleri · Chou · Chou-fleur · Concombre · Courgette · Épinard · Fraise · Haricot vert · Laitue · Melon · Oignon · Persil · Petits pois · Poireau · Poivron · Pomme de terre · Potiron · Radis · Tomate.

### 🔄 Stades de croissance

Pour chaque parcelle, vous choisissez le stade de développement :

- `ini` — **Initial** (semis / reprise)
- `mid` — **Mi-saison** (plein développement)
- `end` — **Fin de saison** (maturation)

---

## 🛠️ Configuration

La mise en place s'effectue entièrement via l'interface graphique de Home Assistant (**Config Flow**). Le menu d'options regroupe :

- **Ajouter / Supprimer une culture** : nom de parcelle, type, stade, nombre de plants et densité (pré-remplie selon le référentiel FAO).
- **Vanne globale** : liaison avec une entité vanne ou interrupteur (`global_valve_entity_id`) et saisie du débit total de l'installation (`global_flow_rate`, en L/h) pour estimer la durée d'arrosage. Laissez vide pour désactiver le suivi automatique.
- **Fréquence et mode d'arrosage** :
  - **Fréquence** : `daily` (quotidien) ou `interval` (intervalle fixe de X jours).
  - **Mode** :
    - **Continu** (`continuous`).
    - **Fractionné** (`fractioned`) : séquence l'arrosage en plusieurs cycles (3 par défaut) entrecoupés de pauses (15 min par défaut) pour éviter le ruissellement et favoriser l'infiltration.
- **Arrosage automatique** : heure de déclenchement quotidien de l'événement d'arrosage.

---

## 🤖 Arrosage automatique et pilotage de la vanne

L'intégration ne pilote pas directement votre matériel : elle **émet un événement** que vous reliez à votre vanne physique via un blueprint. Cette séparation garantit la sécurité d'extinction et reste agnostique de votre installation.

1. Configurez la **vanne globale** et activez le switch **« Arrosage automatique »**.
2. À l'heure configurée (ou selon l'intervalle), la centrale émet l'événement `my_garden_irrigation_irrigation_requested` **uniquement si un arrosage est réellement nécessaire** (le calendrier se réancre sur l'arrosage effectif, pas sur le simple écoulement de l'intervalle).
3. Importez le **blueprint fourni** ([`watering_blueprint.yaml`](blueprints/automation/my_garden_irrigation/watering_blueprint.yaml)) pour lier cet événement à votre vanne. Le blueprint s'appuie sur le moteur natif de Home Assistant : **si HA redémarre en cours d'arrosage, la vanne est coupée automatiquement à la reprise**.

---

## 🚀 Service exposé

- **`my_garden_irrigation.recalculate`** : force le recalcul immédiat de tous les besoins en eau, sans attendre la planification automatique. Utile après une mise à jour manuelle de l'ETo ou pour tester une automatisation.

---

## 📥 Installation

### 🛒 Via HACS (recommandé)

1. Ouvrez **HACS** dans votre instance Home Assistant.
2. Menu (trois points en haut à droite) → **Dépôts personnalisés**.
3. Renseignez l'URL de ce dépôt, catégorie **Intégration**, puis **Ajouter**.
4. Recherchez `My Garden Irrigation` et cliquez sur **Télécharger**.
5. Redémarrez Home Assistant.

### ⚙️ Configuration initiale

1. **Paramètres** → **Appareils et services**.
2. **Ajouter une intégration** → recherchez `My Garden Irrigation`.
3. Suivez les formulaires guidés pour ajouter vos cultures et lier votre vanne.

---

## 📋 Prérequis

- Home Assistant 2024.1 ou version ultérieure.
- HACS opérationnel.
- Coordonnées géographiques renseignées dans Home Assistant (pour la récupération Open-Meteo).
- Connexion Internet active (requêtes Open-Meteo et référentiel Kc — *cloud polling*).
