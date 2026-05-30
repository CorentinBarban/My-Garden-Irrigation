# 009 — Couplage natif avec une entité Vanne globale au niveau du potager

**Date** : 2026-05-30  
**Statut** : Proposé  
**Décideurs** : Équipe projet  

---

## Contexte

Dans la première ébauche conceptuelle, il avait été envisagé d'associer une vanne et un débit spécifiques à chaque culture. Cependant, dans la réalité des potagers familiaux et des installations d'arrosage résidentielles, l'ensemble du potager est généralement piloté par une **unique électrovanne globale** (ou une seule zone de programmateur) qui alimente un réseau partagé (goutte-à-goutte ou asperseurs traversant toutes les cultures).

Multiplier les vannes au niveau de chaque plant ou ligne de culture complexifierait inutilement l'interface utilisateur (*UI*) et ne refléterait pas la topologie matérielle réelle de la majorité des utilisateurs.

## Décision

Déplacer la gestion de la vanne et du débit au **niveau global du potager** (directement dans la configuration principale de l'intégration / `ConfigEntry`), plutôt que de la segmenter par culture.

### 1. Évolution de la configuration globale (`config_flow.py`)

Modifier l'étape initiale ou ajouter une option de configuration générale dans l'icône de l'intégration pour renseigner :

- `global_valve_entity_id` : sélecteur d'entité Home Assistant unique limité aux domaines `valve.*` ou `switch.*`.
- `global_flow_rate` : débit horaire total de l'installation d'arrosage du potager (en litres / heure).

### 2. Calcul automatique de l'apport en eau (`coordinator.py`)

Le coordinateur surveille l'état de cette unique vanne globale via un écouteur d'événement d'état (`async_track_state_change_event`). À la fermeture de la vanne (`on` → `off`), le volume total d'eau introduit dans le potager est calculé :

$$\text{Volume Global Distribué (L)} = \frac{\text{Durée d'ouverture (s)}}{3600} \times \text{Global Flow Rate (L/h)}$$

### 3. Stratégie de répartition entre les cultures (`core/calculations.py`)

Comme toutes les cultures reçoivent de l'eau en même temps lorsque la vanne s'ouvre, le volume global distribué doit être ventilé pour apurer le déficit hydrique individuel de chaque culture (ADR 008). L'eau est répartie de manière **proportionnelle à la surface occupée** par chaque culture (calculée via ADR 003 : $nb\_plants \div densit\acute{e}$) :

$$\text{Volume attribué à la culture } i = \text{Volume Global} \times \frac{\text{Surface culture } i}{\text{Surface totale du potager}}$$

Ce volume calculé vient ensuite réduire le déficit cumulé de chaque culture au sein du bilan hydrique.

## Justification

- **Conformité matérielle** : correspond exactement à l'installation physique standard des utilisateurs (une seule arrivée d'eau pour tout le potager).
- **Simplicité de configuration (UX)** : l'utilisateur ne configure sa vanne et son débit qu'une seule fois pour tout son système, au lieu de devoir les répéter et diviser son débit sur chaque fiche de culture.
- **Rigueur agronomique sous contrainte** : le fait d'avoir une seule vanne implique que toutes les cultures sont arrosées pendant la même durée. Répartir le volume au prorata de la surface modélise correctement l'apport d'eau par m² délivré uniformément sur la zone.

## Conséquences

- **Positives** : intégration logicielle/matérielle extrêmement simple à mettre en place pour l'utilisateur ; une seule automatisation globale ou un simple suivi de vanne suffit.
- **Négatives** : contrainte physique de l'arrosage unique — si une culture (ex. tomates, gros besoin) nécessite beaucoup d'eau et une autre (ex. oignons, faible besoin) en demande moins, l'arrosage global basé sur la culture la plus gourmande entraînera une sur-irrigation locale des plantes sobres. L'intégration pourra toutefois avertir l'utilisateur de ce déséquilibre agronomique via des attributs de diagnostic (ex. afficher quelle culture induit l'arrosage et lesquelles se retrouvent temporairement en sur-irrigation).
