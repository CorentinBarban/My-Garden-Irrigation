# Cahier des Charges de Réfractoration - Intégration Home Assistant "My Garden Irrigation"

## 🎯 Objectif Général

Ce document contient les instructions strictes de refactoring pour corriger la dette technique, les violations d'architecture Home Assistant Core et les failles de robustesse de l'intégration `my_garden_irrigation`. L'objectif est de transformer le code actuel pour le rendre éligible à une inclusion dans Home Assistant Core, en améliorant la modularité, l'i18n, la sécurité matérielle et la testabilité unitaire.

---

## 🚫 Règles d'Or et Contraintes Strictes (Ne pas dévier)

1. **Zéro Décision Arbitraire :** Ne modifie aucun algorithme agronomique sous-jacent issu de la FAO. Tout changement doit servir l'architecture logicielle, pas la logique métier de base.
2. **Respect des Principes HA Core :** Pas d'appels bloquants, utilisation exclusive de la boucle d'événements asynchrone (`async_...`), typage strict (`Type Hints`) sur toutes les fonctions.
3. **Aucune Modification de ConfigEntry Hors Flow :** Les entités (Lovelace) ne doivent JAMAIS appeler `async_update_entry`. La configuration est immuable en dehors du flux de configuration.

---

## 🛠️ Module 1 : Correction du Détournement de `ConfigEntry` et Migration vers `RestoreEntity`

### Contexte du Problème

Actuellement, les fichiers `number.py` et `select.py` modifient directement `entry.options` via `async_update_entry` pour enregistrer l'état de fonctionnement de l'utilisateur (nombre de plants, stade de croissance, densité). Cela provoque des rechargements d'intégration intempestifs, masqués par un hack asynchrone (`OPTIONS_FIELD_UPDATE_FLAG`) dans `__init__.py`.

### Instructions de Refactoring

1. **Nettoyage de `__init__.py` :**
   - Supprime définitivement la constante `OPTIONS_FIELD_UPDATE_FLAG` et le mécanisme de filtrage interceptant le rechargement automatique dans `_async_reload_entry`.
2. **Nettoyage de `config_flow.py` :**
   - Supprime le stockage dynamique des cultures à l'intérieur de `entry.options`. `OptionsFlow` ne doit configurer que les vrais paramètres fixes (coordonnées météo alternatives, liaison vanne globale, etc.).
3. **Refonte de `number.py` et `select.py` :**
   - Supprime l'appel à la fonction interne `_update_crop_field` et `_update_global_option`.
   - Fais hériter `NbPlantsNumber`, `DensityNumber` et `StageSelect` de la classe `RestoreEntity` (fournie par `homeassistant.helpers.restore_state`).
   - Implémente la méthode `async_added_to_hass` pour récupérer la dernière valeur d'état sauvegardée à l'aide de `await self.async_get_last_state()`.
   - Enregistre la valeur modifiée directement dans la mémoire de l'entité/coordinateur et appelle `self.async_write_ha_state()`.

---

## 🧱 Module 2 : Déconstruction du "God Object" `coordinator.py`

### Contexte du Problème

La classe `IrrigationCoordinator` viole le Principe de Responsabilité Unique (SRP). Elle gère simultanément le polling HTTP d'Open-Meteo, le stockage HA Store, l'écoute d'événements physiques de vannes, la planification temporelle et l'exécution asynchrone matérielle.

### Instructions de Refactoring

Découpe `coordinator.py` en 3 modules distincts au sein du dossier `custom_components/my_garden_irrigation/` :

1. **`coordinator.py` (Nouveau) :**
   - Doit hériter uniquement de `DataUpdateCoordinator`.
   - Sa seule fonction est la méthode `_async_update_data()` : appeler l'API Open-Meteo via `_fetch_weather` et retourner un objet `IrrigationData`.
2. **`valve_tracker.py` (Nouveau) :**
   - Gère l'écouteur d'événements d'état de la vanne globale (`async_track_state_change_event`).
   - Calcule le volume global consommé lors de la fermeture de la vanne et applique la formule de prorata de surface.
3. **`scheduler.py` (Nouveau) :**
   - Gère les fonctions temporelles à l'aide de `async_track_point_in_time`.
   - Émet le déclencheur de minuit pour basculer le besoin journalier résiduel vers le bilan hydrique cumulé.

---

## 🧬 Module 3 : Rapatriement de la Logique Métier Pure vers `core/`

### Contexte du Problème

Le fichier `coordinator.py` contient du code de calcul agronomique (le calcul du prorata de répartition de l'eau basé sur les surfaces et l'accumulation temporelle du bilan hydrique). Ces calculs doivent être 100% isolés du framework Home Assistant pour être testables hors ligne.

### Instructions de Refactoring

1. **Création de `core/ledger.py` ou Enrichissement de `core/calculations.py` :**
   - Déplace la logique de ventilation proportionnelle du volume d'eau :
     $$ ext{Volume attribué} = ext{Volume Global} imes rac{ ext{Surface de la culture}}{ ext{Surface totale}}$$
   - Crée une fonction pure Python pour simuler le passage à minuit (le transfert arithmétique de l'état hydrique journalier non satisfait vers le bilan cumulé).
2. **Garantie de Testabilité :**
   - Ces fonctions doivent accepter uniquement des structures de données natives Python (`dict`, `float`, `int`, `dataclass`) et ne doivent importer aucun module provenant de `homeassistant.*`.

---

## 🌐 Module 4 : Formulaires, Validations `Voluptuous` et Internationalisation (i18n)

### Contexte du Problème

Certains formulaires assemblent des chaînes textuelles dynamiques en dur à l'intérieur de Python, brisant la compatibilité avec l'i18n. De plus, les schémas de validation backend manquent de rigueur logicielle.

### Instructions de Refactoring

1. **Utilisation de `OptionsFlowWithReload` :**
   - Modifie la classe `IrrigationOptionsFlowHandler` dans `config_flow.py` pour qu'elle hérite directement de `OptionsFlowWithReload` au lieu de `OptionsFlow`. Supprime le boilerplate manuel lié au listener de rechargement.
2. **i18n de l'étape `remove_crop` :**
   - Interdiction de générer la clé `"label"` via une f-string Python dans `config_flow.py`.
   - Modifie le dictionnaire renvoyé pour utiliser des clés fixes et déclare des placeholders dans `strings.json` sous la clé de traduction appropriée.
3. **Renforcement de la Validation Backend via `Voluptuous` :**
   - Dans `async_step_add_crop`, ne t'appuie pas uniquement sur les contraintes du sélecteur frontend.
   - Remplace `vol.Required(CONF_CROP_NAME): str` par une validation stricte empêchant les injections d'espaces vides ou de chaînes vides :
     ```python
     vol.Required(CONF_CROP_NAME): vol.All(str, vol.Strip, vol.Length(min=1))
     ```

---

## ⚙️ Module 5 : Flexibilité des Paramètres du Mode Fractionné

### Contexte du Problème

Le mode fractionné (_Cycle & Soak_) de l'ADR-010 est codé en dur avec 3 cycles et 15 minutes de repos. L'utilisateur ne peut pas modifier ces valeurs dans l'interface visuelle.

### Instructions de Refactoring

1. **Évolution des Constantes :**
   - Ajoute `CONF_CYCLES_COUNT = "cycles_count"` et `CONF_SOAK_DURATION = "soak_duration_minutes"` dans `const.py`.
2. **Dynamisation du Schéma dans `config_flow.py` :**
   - Dans l'étape `async_step_watering_config`, rends le formulaire dynamique.
   - Si `user_input[CONF_WATERING_MODE] == WATERING_MODE_FRACTIONED`, ajoute au schéma soumis à l'écran les deux champs optionnels (ou obligatoires avec valeurs par défaut) pour le nombre de cycles et le temps de repos.
3. **Mise à jour de `strings.json` :**
   - Ajoute les entrées de dictionnaire de traduction correspondantes pour ces deux variables dans toutes les langues supportées (`fr`, `en`, `es`, `it`, `de`).

---

## 🛡️ Module 6 : Sécurisation du Pilotage Matériel (Migration vers l'Approche Blueprint)

### Contexte du Problème

La méthode `_irrigation_sequence_task` dans le coordinateur utilise des boucles d'attente asynchrones complexes à base de `asyncio.sleep()`. Si l'instance Home Assistant redémarre ou subit une coupure de courant en plein cycle, l'état de la vanne est corrompu en mémoire et le potager risque d'être inondé ou privé d'eau.

### Instructions de Refactoring

1. **Suppression de la boucle de commande Python :**
   - Supprime définitivement la méthode `_irrigation_sequence_task` et l'appel direct aux services `turn_on` / `turn_off` matériels depuis le fichier de l'intégration.
2. **Exposition Totale en Attributs de Diagnostic :**
   - Assure-toi que toutes les données de séquençage calculées par `core/calculations.py` soient exposées de manière exhaustive en tant qu'attributs de l'entité globale `TotalCumulativeNeedSensor` dans `sensor.py` :
     - `recommended_duration_minutes`
     - `is_fractioned`
     - `cycles_count`
     - `duration_per_cycle_minutes`
     - `soak_duration_minutes`
3. **Création d'un Fichier Blueprint Externe :**
   - Crée un fichier blueprint d'automatisation Home Assistant standard (`watering_blueprint.yaml`) fourni dans la documentation du dépôt. Ce blueprint permettra à l'utilisateur de lier de manière sécurisée les attributs du capteur de diagnostic à son automatisation native HA, garantissant la reprise sur panne et la sécurité d'extinction de la vanne physique par le moteur natif de Home Assistant.
