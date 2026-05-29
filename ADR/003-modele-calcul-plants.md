# 003 — Modèle de calcul : surface pilotée par le nombre de plants

**Date** : 2026-05-28  
**Statut** : Accepté  
**Décideurs** : Équipe projet  

---

## Contexte

La formule FAO calcule ETc par unité de surface (mm/m²/jour). Deux approches s'offrent à l'utilisateur pour paramétrer son potager :

- **Option A — Surface pilote** : l'utilisateur renseigne une superficie en m², la densité est indicative.
- **Option B — Plants pilotent** : l'utilisateur renseigne un nombre de plants et une densité, la surface est calculée.

```
Option A : ETc = Kc × ETo × surface_saisie
Option B : surface = nb_plants ÷ densité
           ETc = Kc × ETo × surface
```

## Décision

**Option B — Le nombre de plants pilote le calcul.**

L'utilisateur saisit :
- le nombre de plants (ex. : 12 pieds de tomate)
- la densité de plantation en plants/m² (pré-remplie avec la valeur FAO, modifiable)

La surface est dérivée automatiquement : `surface = nb_plants ÷ densité`.

## Justification

Le profil utilisateur cible est un jardinier amateur qui pense naturellement en nombre de plants ("j'ai planté 12 tomates") et non en superficie ("j'occupe 4 m²"). L'Option B est plus intuitive et réduit les erreurs de saisie.

| Critère                          | Option A (surface) | Option B (plants) ✅ |
|----------------------------------|--------------------|----------------------|
| Intuitivité pour jardinier amateur | Faible           | Haute                |
| Précision agronomique            | Équivalente        | Équivalente          |
| Sensibilité aux erreurs de saisie | Haute             | Faible               |
| Cohérence avec le suivi réel     | Faible             | Haute                |

Les deux options sont agronomiquement équivalentes : modifier la densité dans l'Option B revient exactement à modifier la surface dans l'Option A.

## Conséquences

- **Positives** : UX simplifiée, la surface calculée est affichée en retour comme information utile (et non saisie requise).
- **Négatives** : la densité par défaut (FAO) peut ne pas correspondre à l'espacement réel du jardinier — documenté comme paramètre à ajuster.
- **Validation** : `nb_plants ≥ 1`, `densité ≥ 0.1 plants/m²`. Si la surface calculée dépasse 10 000 m², un avertissement est loggué (saisie probablement erronée).
