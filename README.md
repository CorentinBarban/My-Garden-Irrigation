# 🌿 My Garden Irrigation — Intégration Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
Version : 1.0.0

**My Garden Irrigation** (`my_garden_irrigation`) est une intégration personnalisée pour Home Assistant qui évalue les besoins en eau des cultures d'un potager. Elle s’appuie sur la méthode de calcul de l’évapotranspiration issue de la publication FAO Irrigation and Drainage Paper 56.

L'intégration récupère l'évapotranspiration de référence (ETo) quotidienne via l'API Open-Meteo et télécharge les coefficients culturaux (Kc) depuis un fichier distant. Son mode de fonctionnement est basé sur le principe du "cloud polling".

---

## 📐 Fonctionnement et formule de calcul

L'estimation repose sur la formule d'agronomie standard :

```
ETc = Kc × ETo
```

- **ETo** : Évapotranspiration de référence journalière (en mm/jour), issue d'Open-Meteo.
- **Kc** : Coefficient cultural propre à chaque plante et indexé selon son stade de croissance.
- **ETc** : Besoin en eau brut converti en litres en fonction de la surface occupée.

La surface d'une zone de culture est automatiquement déduite à partir du **nombre de plants** et de la **densité de plantation** configurés (plants par m²).

---

## 📊 Entités générées

Pour chaque zone ou culture ajoutée, l’intégration expose des entités à travers trois plateformes (`sensor`, `number` et `select`) :

### 🔍 Capteurs (`sensor`)

Chaque capteur principal de culture fournit le volume requis et embarque une liste d'attributs pour vos automatisations et vos suivis :

- `crop_type` & `stage` : Type de culture et stade actuel.
- `nb_plants` & `density_plants_per_m2` : Nombre de pieds et densité par m².
- `surface_m2` : Surface au sol calculée.
- `kc` & `eto_mm` : Valeurs de calcul agronomiques du jour.
- `precipitation_mm` & `effective_rainfall_mm` : Pluviométrie et pluie efficace retenues.
- `cumulative_need_liters` : Bilan du besoin hydrique cumulé.
- `recommended_duration_minutes` : Temps d'arrosage recommandé basé sur le débit configuré.
- **Paramètres de fractionnement** : Détails des cycles si ce mode est activé (`is_fractioned`, `cycles_count`, `duration_per_cycle_minutes`, `soak_duration_minutes`).

### ⚙️ Contrôles numériques (`number`) et Sélecteurs (`select`)

Ces entités vous permettent d'ajuster dynamiquement les paramètres ou de modifier les modes directement depuis vos tableaux de bord Lovelace.

---

## 🥕 Cultures prises en charge

L'intégration intègre nativement les paramètres de densité de plantation par défaut (exprimés en plants/m²) pour **27 cultures** issues du référentiel FAO :

Ail · Artichaut · Asperge · Aubergine · Basilic · Betterave · Brocoli · Carotte · Céleri · Chou · Chou-fleur · Concombre · Courgette · Épinard · Fraise · Haricot vert · Laitue · Melon · Oignon · Persil · Petits pois · Poireau · Poivron · Pomme de terre · Potiron · Radis · Tomate.

### 🔄 Stades de croissance gérés

Pour chaque plante ajoutée, vous définissez son niveau de développement parmi les trois options suivantes :

- `ini` : Stade initial
- `mid` : Stade intermédiaire
- `end` : Stade final/fin de saison

---

## 🛠️ Configuration

La mise en place s'effectue entièrement par l'interface graphique de Home Assistant via un **Config Flow**.

### 🔬 Options avancées disponibles :

- **Gestion d'une vanne globale** : Liaison avec une entité de vanne parente (`global_valve_entity_id`) et saisie du débit d'eau (`global_flow_rate`) pour obtenir l'estimation exacte du temps d'ouverture en minutes.
- **Fréquence d'arrosage** : Choix entre un rythme quotidien (`daily`) ou un intervalle personnalisé défini en nombre de jours (`interval`).
- **Mode de distribution** :
  - Continu (`continuous`)
  - Fractionné (`fractioned`) : Séquence l'arrosage en plusieurs cycles (3 cycles par défaut) entrecoupés de pauses (15 minutes par défaut) pour éviter le ruissellement et optimiser la pénétration de l'eau dans le sol.

---

## 🚀 Services exposés

L'intégration enregistre le service suivant dans Home Assistant :

- **`my_garden_irrigation.recalculate`** : Force la mise à jour immédiate et le recalcul des valeurs hydro-agronomiques sans attendre la planification de mise à jour automatique.

---

## 📥 Installation

### 🛒 Via HACS (recommandé)

1. Ouvrez l'interface **HACS** dans votre instance Home Assistant.
2. Cliquez sur les trois points en haut à droite et sélectionnez **Dépôts personnalisés**.
3. Renseignez l'URL de ce dépôt GitHub, sélectionnez la catégorie **Intégration** et cliquez sur **Ajouter**.
4. Recherchez `My Garden Irrigation` puis cliquez sur **Télécharger**.
5. Redémarrez Home Assistant.

### ⚙️ Configuration initiale

1. Accédez à **Paramètres** > **Appareils et services**.
2. Cliquez sur **Ajouter une intégration** en bas à droite.
3. Recherchez `My Garden Irrigation` dans la liste.
4. Remplissez les formulaires guidés pour ajouter vos cultures et lier vos équipements de distribution d'eau.

---

## 📋 Prérequis

- Home Assistant 2024.1 ou version ultérieure.
- Extension HACS opérationnelle.
- Connexion Internet active pour l'envoi des requêtes Open-Meteo et FAO (Cloud Polling).
