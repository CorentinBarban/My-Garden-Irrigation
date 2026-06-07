# 029 — Atténuation dynamique et phasée du paillage selon les stades de croissance (FAO 56)

**Date** : 2026-06-07
**Statut** : Implémenté (remplace la V1 — facteur forfaitaire unique 0,80)
**Décideurs** : Équipe projet

---

## Contexte

La V1 de cette décision introduisait un facteur d'atténuation **forfaitaire unique de 0,80**
pour les cultures paillées. L'analyse agronomique de la FAO 56 montre que l'impact d'un
paillis (*mulch*) sur l'évapotranspiration de la culture (`ETc`) **n'est pas constant** au
cours de la saison :

- **Stade initial (`ini`)** : le sol est majoritairement nu. L'évaporation directe du sol
  (`Ke`) représente jusqu'à 100 % de l'eau perdue. Le paillis y est critique : il bloque de
  50 % à 80 % de cette évaporation.
- **Mi-saison (`mid`)** : la canopée est complète et ombrage le sol. Les pertes proviennent
  presque exclusivement de la transpiration foliaire (`Kcb`). L'effet du paillis devient
  marginal (abattement de l'ordre de 5 à 10 %).
- **Fin de cycle (`end`)** : début de sénescence, ouverture partielle de la canopée,
  l'évaporation du sol remonte légèrement.

> Le modèle de données ne distingue que trois stades (`ini`, `mid`, `end` — voir `STAGES`
> dans `const.py`). Un éventuel stade intermédiaire (`dev`) non défini retombe sur le
> facteur neutre `1,0`.

Un facteur fixe de 0,80 provoquerait donc un **sur-arrosage en début de cycle** (où le
paillis bloque bien davantage que 20 % de l'évaporation) et surtout un **sous-arrosage en
mi-saison** (période de fructification critique, où le vrai abattement n'est que de ~10 %).
L'atténuation doit suivre la phase phénologique active.

**Levier existant** : la phase de la culture est déjà un champ configuré par culture
(`CONF_STAGE` → `"ini" | "dev" | "mid" | "end"`) qui traverse toute la chaîne de calcul
jusqu'à [`compute_crop_result(... stage=...)`](../custom_components/my_garden_irrigation/core/calculations.py).
Cette ADR s'appuie sur ce `stage` déjà disponible — **sans** re-dérivation depuis la date de
plantation — pour rester dans une couche de calcul pure (ADR-013).

## Décision

Implémenter une atténuation **dynamique par phase**, pilotée par un commutateur « Paillage »
unique et appliquée dans la couche de calcul pure.

### 1. Coefficients d'abattement par phase (`const.py`)

```python
FAO56_MULCH_STAGE_FACTORS: dict[str, float] = {
    STAGE_INI: 0.55,  # −45 % : sol nu, évaporation directe largement bloquée
    STAGE_MID: 0.90,  # −10 % : canopée complète, transpiration dominante
    STAGE_END: 0.85,  # −15 % : début de sénescence, canopée qui s'ouvre
}
```

### 2. Atténuation dans le moteur de calcul (`core/calculations.py`)

Le facteur s'applique sur l'`ETc` **avant** la déduction de la pluie efficace
(`compute_balance_liters`), car le paillage réduit la composante évaporative du besoin, pas
la pluie reçue par le sol. La fonction pure reste sans état et testable sans Home Assistant.

```python
def apply_mulch_factor(etc_liters: float, stage: str, mulch_active: bool) -> float:
    """Atténue l'ETc selon la phase FAO 56 si le paillage est actif (ADR-029).

    Phase inconnue → facteur 1,0 (aucune atténuation, comportement sûr).
    """
    if not mulch_active:
        return etc_liters
    factor = FAO56_MULCH_STAGE_FACTORS.get(stage, 1.0)
    return etc_liters * factor
```

`compute_crop_result` reçoit `mulch_active: bool = False` et applique le facteur sur
`etc_liters` avant `compute_balance_liters` / `compute_net_liters`. Le `stage` est déjà un
paramètre de la fonction. Le défaut `False` garantit la rétrocompatibilité : une culture sans
paillage ou une phase inconnue conserve exactement le calcul actuel.

### 3. Câblage par culture (`switch.py`, `config_state.py`)

Le paillage est un drapeau **par culture**, piloté par un commutateur HA `MulchSwitch`
(une entité par parcelle, attachée au device de la plante, comme `StageSelect`). Sa valeur
est un champ override runtime (`CONF_MULCH_ACTIVE`) ajouté à `_CROP_OVERRIDE_FIELDS` dans
`config_state.py` : il est donc persisté dans le Store HA et restauré au boot sous la même
garde `options_hash` que le stade et la densité — l'utilisateur l'active une fois, il survit
aux redémarrages.

Le drapeau voyage dans le dict de culture déjà transmis par le coordinator à
`compute_irrigation_data`, qui lit `crop.get("mulch_active", False)` et le passe à
`compute_crop_result`. Aucune logique agronomique n'est ajoutée dans le coordinator ni dans
les entités : le calcul reste confiné à la couche pure. Une culture sans la clé (config
antérieure, formulaire d'ajout inchangé) est traitée comme non paillée — rétrocompatibilité
totale.

## Conséquences

- **Positives**
  - **Exactitude agronomique** : l'abattement suit la dynamique réelle sol/canopée au fil de
    la saison ; plus de sous-irrigation en mi-saison (fructification) ni de sur-irrigation en
    début de cycle.
  - **Automatisation transparente** : l'utilisateur active le paillage une seule fois ; le
    système fait évoluer le coefficient au gré des changements de phase, sans intervention.
  - **Pureté et testabilité** : `apply_mulch_factor` est une fonction pure couverte par des
    tests unitaires sans mock HA (ADR-013) ; le `stage` réutilisé évite tout nouveau couplage
    temporel.
- **Négatives / Risques**
  - **Dépendance à l'exactitude du `stage`** : un stade mal renseigné applique le mauvais
    facteur. Le risque est borné par le défaut `1.0` (phase inconnue = aucune atténuation,
    jamais d'amplification).
  - **Calibration empirique** : les quatre coefficients sont des valeurs de référence FAO 56
    à affiner ; ils restent centralisés dans `const.py` pour ajustement ultérieur.
- **Relation** : remplace la V1 (facteur forfaitaire 0,80) ; s'insère dans la chaîne de calcul
  d'**ADR-003** (le nombre de plants pilote la surface) et d'**ADR-007** (pluie efficace
  appliquée *après* l'atténuation de l'ETc) ; respecte la pureté de la couche calcul
  (**ADR-013**) ; le commutateur « Paillage » suit le modèle d'option par culture introduit
  pour la vanne globale (**ADR-009**). Couvert par `tests/test_calculations.py`
  (section paillage : `apply_mulch_factor`, `compute_crop_result` et
  `compute_irrigation_data` paillés).
