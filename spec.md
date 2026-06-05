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

> **Mise à jour ADR-028 (2026-06-05) — Réserve hydrique signée.** Les trois règles
> ci-dessous ont évolué pour gérer le report du surplus de pluie. Le **Besoin Cumulé**
> devient un **bilan signé** : positif = dette, négatif = réserve d'eau. Le facteur de
> pluie efficace 0,8 (ADR-007) est conservé.

### Règle 1 : Le bilan hydrique signé lors du transfert de minuit

La clôture comptable additionne le **bilan signé du jour** (besoin ETc − pluie efficace,
qui peut être négatif) au bilan cumulé. Le résultat **n'est plus planché à 0** : un surplus
de pluie reporte une réserve (bilan négatif) consommée les jours suivants. L'arrosage du
jour n'est **pas** soustrait ici — il est déjà imputé en temps réel au bilan cumulé à la
fermeture de la vanne (source unique, pas de double comptage).

- **Formule algorithmique :** `Nouveau Besoin Cumulé = Besoin Cumulé Précédent + Bilan Signé du Jour`
  où `Bilan Signé du Jour = Besoin ETc du jour − Pluie Efficace du jour` (signé).

### Règle 2 : Le calcul inclusif du volume d'arrosage (toute heure)

Le volume commandé à la vanne anticipe toujours la clôture de minuit en englobant le bilan
net de la journée en cours, **quelle que soit l'heure** d'arrosage. Comme l'arrosage n'est
imputé qu'une fois et que le bilan est signé, pré-payer le besoin du jour fait simplement
passer le cumulé en réserve (négatif), ré-équilibrée à minuit — il n'y a plus de raison de
distinguer matin et soir.

- **Formule algorithmique :**
  `Volume d'arrosage cible = Maximum entre (0) et (Besoin Cumulé + Bilan Net du Jour)`
  Un cumulé négatif (réserve) ou un bilan du jour négatif (pluie) réduit — voire annule — le volume.

### Règle 3 : Le réancrage du calendrier sur arrosage réel

Le cycle d'intervalle n'est réancré (`Date du Dernier Arrosage = aujourd'hui`) **que si un
arrosage est effectivement émis**. Un jour d'intervalle sauté faute de besoin net (réserve
qui couvre, ou pluie) **ne consomme pas** un nouveau cycle : le planificateur réévalue dès
le lendemain jusqu'à ce qu'un arrosage ait lieu.

- **Logique algorithmique :**
  `Si (Date du jour - Date du Dernier Arrosage) ≥ Intervalle Configuré :`
  `  Évaluer le volume cible (Règle 2).`
  `  Si volume > 0 (arrosage émis) -> Date du Dernier Arrosage = aujourd'hui (réancrage).`
  `  Sinon -> ne pas réancrer ; réévaluer demain.`

---

## 4. Scénarios de Validation Fonctionnelle (Plans de Tests)

_Ces scénarios décrivent le comportement attendu à travers le parcours du jardinier pour guider l'écriture des tests de non-régression._

### Scénario I : Arrosage matinal — calcul inclusif et ré-équilibrage à minuit

- **Étant donné :** Un potager configuré avec un arrosage automatique tous les 3 jours à 06h00 du matin.
- **Et que :** Le Jour 1 et le Jour 2 ont accumulé une dette totale de 8 Litres (le **Besoin Cumulé** est égal à 8).
- **Et que :** Le Jour 3 ensoleillé génère un **Bilan Net du Jour** de 4 Litres.
- **Quand :** Au matin du Jour 3 à 06h00, l'arrosage se déclenche.
- **Alors :** Le volume commandé est inclusif (Règle 2) : `8 (dette) + 4 (jour) = 12 Litres`. L'imputation immédiate fait passer le **Besoin Cumulé** à `8 − 12 = −4` (réserve).
- **Et alors :** Au passage de minuit, le bilan signé du jour (`+4`) est ajouté : `−4 + 4 = 0`. Le **Besoin Cumulé** au matin du Jour 4 est strictement égal à **0 Litre**.

### Scénario II : Arrosage du soir — résultat identique au matin (ADR-028)

- **Étant donné :** Le même potager mais arrosage à 21h00.
- **Et que :** Dette de 8 Litres, bilan du jour de 4 Litres au Jour 3.
- **Quand :** L'arrosage se déclenche à 21h00.
- **Alors :** Le volume commandé est **12 Litres** (8 + 4), comme le matin : la décision est désormais toujours inclusive, indépendante de l'heure.
- **Et alors :** Après distribution et passage de minuit, le **Besoin Cumulé** au Jour 4 est égal à **0 Litre**.

### Scénario III : Réancrage du calendrier uniquement sur arrosage réel

- **Étant donné :** Un potager arrosé tous les 3 jours à 06h00 ; **Date du Dernier Arrosage** au Jour 0.
- **Et que :** Il a plu au Jour 1 et au Jour 2, constituant une **réserve** (Besoin Cumulé < 0).
- **Quand :** Le scheduler s'exécute au matin du Jour 3 (`Jour 3 − Jour 0 = 3 jours`).
- **Alors :** L'arrosage est annulé (0 Litre) car la réserve couvre le besoin du jour.
- **Et alors :** La **Date du Dernier Arrosage** **n'est pas avancée** (aucun arrosage réel) — le cycle n'est pas réancré.
- **Conséquence attendue :** Le planificateur **réévalue au Jour 4**, et arrose dès que la réserve ne couvre plus le besoin, au lieu d'attendre un nouveau cycle complet jusqu'au Jour 6.

### Scénario IV : Report du surplus de pluie en réserve puis reprise de l'arrosage

_Surface 6 m² (1 mm = 6 L), facteur de pluie efficace 0,8, intervalle 3 jours._

- **Jour 1 :** besoin nul, pluie 15 mm → 12 mm efficaces → **72 L** de surplus. Bilan cumulé : **−72 L** (réserve). Aucun arrosage.
- **Jour 2 :** besoin nul, pluie 10 mm → 48 L de surplus. Bilan cumulé : **−120 L**. Aucun arrosage.
- **Jour 3 :** beau, besoin **40 L**. L'intervalle de 3 j est atteint mais la réserve couvre (`−120 + 40 = −80 ≤ 0`) → **aucun arrosage**, cycle **non réancré**. Bilan cumulé : **−80 L**.
- **Jour 4 :** besoin **120 L**. Réévaluation : `−80 + 120 = +40 > 0` → **arrose 40 L**, cycle réancré. Bilan cumulé ramené à **0 L**.

> Note : avec de la pluie brute (sans le facteur 0,8) on banquerait 150 L et le Jour 4
> n'arroserait que 10 L. Le facteur 0,8 (ADR-007) ramène le surplus banqué à 120 L, d'où
> les **40 L** au Jour 4. Couvert par `tests/test_water_reserve_scenario.py`.
