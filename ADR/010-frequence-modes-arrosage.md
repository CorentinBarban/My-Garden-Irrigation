# 010 — Intégration de la Fréquence et des Modes d'Arrosage au niveau du potager global

**Date** : 2026-05-30  
**Statut** : Proposé  
**Décideurs** : Équipe projet  

---

## Contexte

La gestion de l'irrigation nécessite de définir non seulement le volume d'eau requis, mais aussi le rythme et la méthode de distribution temporelle de cette eau. L'arrosage d'un potager n'a pas besoin d'être quotidien. De plus, selon la nature du sol (par exemple, un sol argileux compact), un apport massif d'eau en continu peut saturer la surface et provoquer du ruissellement, tandis qu'un arrosage fractionné (*Cycle & Soak*) favorise une infiltration profonde.

L'ADR 009 a établi que l'arrosage est piloté par une unique vanne globale au niveau du potager. Par ailleurs, l'**ADR 009 (Modélisation de l'efficience/coefficient d'application) ayant été rejeté**, le mode et la fréquence d'arrosage n'ont plus d'impact multiplicateur ou réducteur direct sur le calcul du besoin agronomique net en litres (le besoin brut calculé via la FAO-56 reste inchangé). Ils doivent donc être traités comme des **paramètres de planification temporelle et opérationnelle** à l'échelle globale du potager.

## Décision

Introduire les concepts de **Fréquence** et de **Mode d'arrosage** au niveau des options générales du potager (`ConfigEntry`), et adapter l'affichage du besoin ainsi que les consignes d'ouverture de la vanne globale en conséquence.

### 1. Configuration globale (`config_flow.py`)

Ajouter deux paramètres généraux dans la configuration principale du potager :

- `watering_frequency` : menu déroulant (*Quotidien*, *Intervalle fixe de X jours*, *Jours spécifiques de la semaine (ex. Lun, Mer, Ven)*, ou *Seuil dynamique basé sur le déficit maximum*).
- `watering_mode` : menu déroulant (*Continu* ou *Intermittent / Fractionné*).

### 2. Impact de la Fréquence sur les capteurs de besoin

- Les jours définis comme « sans arrosage » par la planification choisie, le capteur principal `sensor.potager_total` et les capteurs individuels de cultures affichent `0 Litres`, car aucune action immédiate n'est requise.
- En arrière-plan, le bilan hydrique cumulé (ADR 008) continue de comptabiliser quotidiennement le déficit en eau de chaque culture (Besoins − Pluie).
- Le jour planifié de l'arrosage, l'intégration met à jour les capteurs pour afficher la **somme totale des déficits accumulés** depuis le dernier arrosage. C'est ce volume cumulé global qui est alors proposé pour l'ouverture de la vanne.

### 3. Impact du Mode d'Arrosage (séquençage opérationnel)

Puisque l'ADR 009 (efficience) est abandonné, le choix du mode n'altère pas le volume d'eau total recommandé. En revanche, il modifie la manière dont la consigne de temps de fonctionnement est exposée dans les attributs du capteur :

**En mode Continu** : l'intégration calcule la durée totale d'arrosage d'une seule traite et l'expose via l'attribut `recommended_duration_minutes` :

$$\text{Durée (min)} = \frac{\text{Besoin Cumulé Global (L)}}{\text{Global Flow Rate (L/h)}} \times 60$$

**En mode Intermittent / Fractionné** : l'intégration segmente automatiquement cette durée totale pour éviter la saturation du sol et expose des attributs de pilotage enrichis :

| Attribut | Description |
|---|---|
| `recommended_duration_minutes` | Durée totale cumulée de fonctionnement de la vanne |
| `is_fractioned` | `true` |
| `cycles_count` | Nombre de cycles recommandé (ex. 3 cycles) |
| `duration_per_cycle_minutes` | Durée de chaque impulsion ($\text{Durée totale} \div \text{cycles}$) |
| `soak_duration_minutes` | Temps de repos entre deux cycles (ex. 15 min fixes) |

## Justification

- **Rigueur agronomique sans complexité utilisateur** : le rejet de l'ADR sur l'efficience évite d'introduire des coefficients arbitraires difficiles à calibrer pour un jardinier amateur ; le besoin en eau reste mathématiquement strict et transparent.
- **Interfaçage simplifié avec les automatisations** : en découpant la consigne temporelle sous forme d'attributs clairs (`cycles_count`, `duration_per_cycle_minutes`), l'intégration fournit une feuille de route directement exploitable par les scripts ou blueprints Home Assistant pour piloter l'électrovanne globale de manière optimale.
- **Respect du sol et économies indirectes** : bien que le volume théorique ne soit pas modifié, fractionner l'apport réduit considérablement le ruissellement de surface et le gaspillage d'eau réel sur le terrain.

## Conséquences

- **Positives** : gestion propre des cycles d'arrosage espacés (ex. tous les 3 jours) sans perte de données sur le besoin réel des plantes ; optimisation physique de l'absorption de l'eau par le sol via le mode fractionné.
- **Négatives** : l'utilisateur doit s'assurer que ses automatisations Home Assistant lisent correctement les attributs de fractionnement si le mode intermittent est activé, afin d'exécuter les boucles d'ouverture/fermeture de la vanne conformément aux recommandations de l'intégration.
