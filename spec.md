Voici un document de spécification fonctionnelle et algorithmique complet, rédigé exclusivement en français, sans aucun code informatique. Il est structuré de manière optimale pour être soumis à une IA de développement (comme Claude) afin qu'elle comprenne les règles métier à appliquer, les algorithmes à réécrire et les cas de tests à coder.

---

# Spécification Fonctionnelle Générale : Refactoring de la Logique Comptable Hydrique

## 1. Cartographie Conceptuelle (Logique Métier)

L'application gère la comptabilité de l'eau d'un potager à l'aide de trois indicateurs clés :

- **Le Besoin Journalier (Indicateur de Flux) :** Le volume net d'eau (en Litres) réclamé par une plante pour la journée en cours, calculé à partir de l'évapotranspiration du soleil déduite de la pluie efficace du jour. Ce compteur est censé se réinitialiser à chaque transition de minuit.
- **Le Besoin Cumulé (Indicateur de Stock) :** Le grand livre de la dette hydrique. C’est la mémoire des jours passés. Si une plante a manqué d'eau hier, le besoin non satisfait est stocké ici pour être réclamé plus tard.
- **La Date du Dernier Arrosage (Indicateur Temporel) :** La date de référence utilisée pour calculer l'intervalle de jours entre deux arrosages (par exemple : s'assurer qu'on arrose strictement tous les 3 jours).

---

## 2. Analyse Algorithmique des 3 Anomalies Métier

### Anomalie A : L'arrosage automatique du MATIN (ex: 06h00) avec intervalle de 3 jours

- **Logique actuelle défaillante :** 1. Au matin du Jour 3, le **Besoin Cumulé** est de 8 Litres (dette accumulée du Jour 1 et du Jour 2).

2.  À 06h00, l'intervalle de 3 jours est atteint. Le système déclenche l'arrosage, distribue 8 Litres, et remet le **Besoin Cumulé** à 0.
3.  Durant la journée du Jour 3, le soleil brille : le **Besoin Journalier** augmente et atteint 4 Litres à la fin de la journée.
4.  À minuit, le système transfère aveuglément le **Besoin Journalier** (4 Litres) dans le **Besoin Cumulé**.

- **Rupture d'expérience :** Agronomiquement, l'eau versée le matin du Jour 3 a servi à hydrater la plante pour toute la journée du Jour 3. Pourtant, l'algorithme considère que cet arrosage n'a remboursé que le passé (Jour 1 et 2) et crée une nouvelle dette à minuit. Le Jour 4 commence donc avec une dette de 4 Litres, infligeant un stress hydrique permanent à la plante pendant les 3 jours d'attente suivants.

### Anomalie B : L'arrosage automatique du SOIR (ex: 21h00) avec intervalle de 3 jours

- **Logique actuelle défaillante :**

1. Au soir du Jour 3 à 21h00, le **Besoin Journalier** a accumulé 4 Litres de soleil pour la journée en cours. Le **Besoin Cumulé** affiche 8 Litres (dette du Jour 1 et 2).
2. Le système se déclenche. Pour calculer le volume à arroser, il lit _uniquement_ le **Besoin Cumulé** (le stock). Il distribue donc 8 Litres et remet le **Besoin Cumulé** à 0.
3. À minuit, la clôture comptable s'active. Elle prend le **Besoin Journalier** de la journée (4 Litres) et l'ajoute au **Besoin Cumulé**.

- **Rupture d'expérience :** Le système ignore la consommation de la journée en cours lors de l'arrosage du soir parce qu'elle n'a pas encore basculé dans le stock à minuit. La terre est physiquement détrempée à 21h00, mais à 00h01, l'application affiche une alerte affirmant que la plante a une dette de 4 Litres.

### Anomalie C : Le glissement du calendrier pour cause de pluie (Fréquence par intervalle)

- **Logique actuelle défaillante :**

1. Au matin du Jour 3, il a plu abondamment les jours précédents. Le sol est saturé : le **Besoin Cumulé** est égal à 0 Litre.
2. À 06h00, le planificateur constate que l'intervalle de 3 jours est atteint et tente d'arroser. Constatant que le **Besoin Cumulé** est à 0, il annule légitimement l'ouverture de la vanne.
3. L'arrosage physique n'ayant pas eu lieu, le système **ne met pas à jour** la **Date du Dernier Arrosage** (qui reste bloquée au Jour 0).
4. Le Jour 4 est sec et crée une dette. Au matin du Jour 5, le système calcule l'intervalle depuis le Jour 0 (`5 jours - 0 jour = 5 jours`). Constatant que 5 est supérieur ou égal à 3, il arrose et met enfin à jour la variable avec la date du Jour 5.

- **Rupture d'expérience :** Le calendrier a glissé de deux jours. Le prochain arrosage automatique n'aura pas lieu au Jour 6 comme prévu initialement, mais au Jour 8 (Jour 5 + 3 jours). La pluie déphase complètement le rythme fixe choisi par le jardinier.

---

## 3. Règles de Gestion Cibles (Spécifications Algorithmiques)

Pour corriger ces anomalies, les algorithmes de calcul doivent intégrer les trois nouvelles règles de comportement suivantes :

### Règle 1 : L'équilibrage absolu lors du transfert de minuit

La clôture comptable ne doit plus être une simple addition du flux dans le stock. Le nouveau calcul du **Besoin Cumulé** à minuit doit faire la somme du passif et du besoin du jour, puis en soustraire la totalité de l'arrosage reçu durant la journée.

- **Formule algorithmique :** `Nouveau Besoin Cumulé = Maximum entre (0) et (Besoin Cumulé Précédent + Besoin Journalier du jour - Total des Arrosages Appliqués aujourd'hui)`

### Règle 2 : Le calcul inclusif pour les arrosages tardifs

Lorsqu'un arrosage automatique est initié en soirée (définir un seuil horaire, par exemple après 12h00 ou via une configuration "Soir"), le volume d'eau commandé à la vanne ne doit pas se limiter au stock historique. Il doit anticiper la clôture de minuit en englobant le flux de la journée en cours.

- **Formule algorithmique :**
  `Volume d'arrosage cible = Besoin Cumulé + Besoin Journalier en cours`

### Règle 3 : L'immunisation temporelle du calendrier

Le calendrier des intervalles mesure le temps écoulé, pas l'état sec ou humide de la terre. Dès que le planificateur valide que l'intervalle de jours requis est atteint, l'échéance temporelle est considérée comme "traitée".

- **Logique algorithmique :**
  `Si (Date du jour - Date du Dernier Arrosage) est supérieure ou égale à l'Intervalle Configuré :`
  `Alors -> Mettre à jour immédiatement la Date du Dernier Arrosage avec la Date du jour (que le volume d'arrosage physique final soit de X Litres ou de 0 Litre à cause de la pluie).`

---

## 4. Scénarios de Validation Fonctionnelle (Plans de Tests)

_Ces scénarios décrivent le comportement attendu à travers le parcours du jardinier pour guider l'écriture des tests de non-régression._

### Scénario I : Validation de la réinitialisation de la dette après un arrosage matinal

- **Étant donné :** Un potager configuré avec un arrosage automatique tous les 3 jours à 06h00 du matin.
- **Et que :** Le Jour 1 et le Jour 2 ont accumulé une dette totale de 8 Litres (le **Besoin Cumulé** est égal à 8).
- **Quand :** Au matin du Jour 3 à 06h00, l'arrosage se déclenche et distribue 8 Litres.
- **Et que :** Durant la journée du Jour 3, le soleil brille et génère un **Besoin Journalier** de 4 Litres.
- **Alors :** Lors du passage à minuit, le système doit appliquer la règle d'équilibrage et calculer : `8 (Passé) + 4 (Jour) - 8 (Arrosé) = 4 Litres`. Ce reliquat de 4 Litres étant inférieur ou égal à l'arrosage déjà reçu (8 Litres), le **Besoin Cumulé** au matin du Jour 4 doit être strictement égal à **0 Litre**.

### Scénario II : Validation du calcul de volume exhaustif pour l'arrosage du soir

- **Étant donné :** Un potager configuré avec un arrosage automatique tous les 3 jours à 21h00 du soir.
- **Et que :** Le Jour 1 et le Jour 2 ont accumulé une dette de 8 Litres (le **Besoin Cumulé** est égal à 8).
- **Et que :** Au Jour 3 à 21h00, la journée ensoleillée a généré un **Besoin Journalier** en cours de 4 Litres.
- **Quand :** L'arrosage automatique se déclenche à 21h00.
- **Alors :** Le système doit sommer les deux indicateurs et commander un volume d'arrosage total de **12 Litres** (8 Litres de dette historique + 4 Litres de la journée en cours).
- **Et alors :** Après la distribution de ces 12 Litres et le passage de minuit, le **Besoin Cumulé** au matin du Jour 4 doit être égal à **0 Litre**.

### Scénario III : Validation de la fixité du calendrier malgré les perturbations de la pluie

- **Étant donné :** Un potager configuré avec un arrosage automatique tous les 3 jours à 06h00 du matin.
- **Et que :** La **Date du Dernier Arrosage** est enregistrée au Jour 0.
- **Et que :** Il a plu au Jour 1 et au Jour 2, maintenant le **Besoin Cumulé** à 0 Litre.
- **Quand :** Le scheduler s'exécute au matin du Jour 3 à 06h00 (`Jour 3 - Jour 0 = 3 jours`).
- **Alors :** L'arrosage physique est annulé (0 Litre distribué) car le besoin est nul.
- **Et alors :** La **Date du Dernier Arrosage** doit obligatoirement être modifiée et enregistrée à la date du **Jour 3**.
- **Conséquence attendue :** Au matin du Jour 4 et du Jour 5, l'arrosage automatique doit être ignoré. Le prochain contrôle doit être programmé de façon stricte au **Jour 6** (`Jour 6 - Jour 3 = 3 jours`), empêchant tout glissement ou retard dans le rythme de surveillance du potager.
