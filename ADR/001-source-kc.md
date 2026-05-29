# 001 — Source des coefficients culturaux (Kc)

**Date** : 2026-05-28  
**Statut** : Accepté  
**Décideurs** : Équipe projet  

---

## Contexte

L'intégration a besoin des coefficients culturaux Kc (initial, mi-saison, fin) pour chaque culture supportée. Ces valeurs sont issues de la publication FAO Irrigation and Drainage Paper n°56 (Allen et al., 1998), qui fait référence mondiale en agronomie.

Trois approches ont été envisagées :
1. Constantes codées en dur dans `const.py`
2. API tierce exposant les Kc à la demande
3. Fichier JSON versionné hébergé sur GitHub, téléchargé au démarrage

## Décision

**Option 3 — Fichier JSON versionné sur GitHub.**

Le fichier `kc_fao56.json` est hébergé dans le dépôt du projet et téléchargé par l'intégration au démarrage de Home Assistant. En cas d'échec réseau, un fichier de fallback embarqué dans le package est utilisé.

```
GET https://raw.githubusercontent.com/<org>/potager-irrigation/main/data/kc_fao56.json
```

Structure du fichier :

```json
{
  "version": "1.0",
  "source": "FAO Irrigation and Drainage Paper 56, Table 12",
  "updated": "2026-05-28",
  "crops": {
    "tomate":    { "ini": 0.60, "mid": 1.15, "end": 0.80, "density_default": 3 },
    "carotte":   { "ini": 0.70, "mid": 1.05, "end": 0.95, "density_default": 60 },
    "haricot":   { "ini": 0.50, "mid": 1.05, "end": 0.90, "density_default": 12 },
    "poivron":   { "ini": 0.60, "mid": 1.05, "end": 0.90, "density_default": 3 },
    "laitue":    { "ini": 0.70, "mid": 1.00, "end": 0.95, "density_default": 8 },
    "courgette": { "ini": 0.50, "mid": 1.00, "end": 0.80, "density_default": 1 },
    "oignon":    { "ini": 0.50, "mid": 1.05, "end": 0.75, "density_default": 25 }
  }
}
```

## Justification

| Critère             | Codé en dur | API tierce | JSON GitHub ✅ |
|---------------------|-------------|------------|---------------|
| Mise à jour sans redéployer | ✗ | ✓ | ✓ |
| Fonctionne hors ligne | ✓ | ✗ | ✓ (fallback) |
| API Kc publique disponible | — | ✗ (inexistante) | — |
| Contrôle de la source | ✓ | ✗ | ✓ |
| Complexité | Faible | Haute | Faible |

Aucune API publique n'expose les Kc FAO de façon structurée. La solution JSON GitHub offre la flexibilité d'une API (mise à jour centralisée, versionnage) sans dépendance externe fragile.

## Conséquences

- **Positives** : ajout de nouvelles cultures sans mise à jour du code, traçabilité via git blame, fichier lisible et auditable.
- **Négatives** : nécessite un accès GitHub au premier démarrage. Géré par le mécanisme de fallback embarqué.
- **Risque** : si GitHub est inaccessible ET que c'est la première installation, les Kc du fallback (version figée) sont utilisés — comportement à documenter clairement pour l'utilisateur.
