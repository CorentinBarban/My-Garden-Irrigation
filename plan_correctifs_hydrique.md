# Plan de Correctifs — Logique Comptable Hydrique

> Document destiné à une IA experte en développement Python / Home Assistant.  
> Basé sur `spec.md` (3 anomalies) et analyse complète du code source.

---

## 0. Contexte architectural

| Classe / Fichier | Rôle |
|---|---|
| `core/ledger.py` | Fonctions pures de comptabilité (sans I/O) |
| `config_state.py` — `RuntimeConfigState` | État mutable runtime (bilan hydrique, config) |
| `coordinator.py` — `IrrigationCoordinator` | Orchestration HA, callbacks, API publique |
| `scheduler.py` — `IrrigationScheduler` | Déclenchement temporel (minuit + arrosage auto) |
| `core/calculations.py` | Calculs ETc / besoins journaliers |

Les trois anomalies n'impliquent **aucune** modification de `scheduler.py`, `calculations.py`, `models.py`, `valve_tracker.py` ni `persistence.py`.

---

## 1. Analyse d'impact — Carte des modifications

```
spec.md Anomalie A  ──►  core/ledger.py       : midnight_transfer()          MODIFIER
                    ──►  config_state.py       : apply_midnight_transfer()     MODIFIER

spec.md Anomalie B  ──►  coordinator.py        : fire_irrigation_event()       MODIFIER
                    ──►  const.py              : nouvelle constante seuil soir AJOUTER

spec.md Anomalie C  ──►  coordinator.py        : _on_trigger()                 MODIFIER

Tests               ──►  tests/test_ledger.py        nouveaux cas              AJOUTER
                    ──►  tests/test_config_state.py   nouveaux cas              AJOUTER
                    ──►  tests/test_resilience.py     nouveaux cas              AJOUTER
```

---

## 2. Correctif A — Équilibrage absolu au transfert de minuit

### Règle métier cible (spec.md §3 Règle 1)

```
Nouveau Besoin Cumulé = max(0, Besoin_Cumulé_Précédent + Besoin_Journalier − Total_Arrosages_Aujourd'hui)
```

### 2.1 `custom_components/my_garden_irrigation/core/ledger.py`

**Fonction : `midnight_transfer()` — lignes 32-51**

Ajouter un troisième paramètre optionnel `watering_applied_today` et appliquer la soustraction avec plancher à 0.

```python
def midnight_transfer(
    cumulative_need: dict[str, float],
    daily_needs: dict[str, float],
    watering_applied_today: dict[str, float] | None = None,
) -> dict[str, float]:
    """Transfère le besoin journalier résiduel vers le bilan hydrique cumulé.

    Applique la Règle 1 du spec : soustrait les arrosages du jour avant
    d'accumuler, avec plancher à 0 (jamais de crédit hydrique négatif).
    """
    _applied = watering_applied_today or {}
    result = dict(cumulative_need)
    for crop_id, daily in daily_needs.items():
        applied = _applied.get(crop_id, 0.0)
        result[crop_id] = max(0.0, result.get(crop_id, 0.0) + daily - applied)
    return result
```

**Rétrocompatibilité :** le paramètre est optionnel (`None` par défaut) — tous les appels existants sans `watering_applied_today` continuent de fonctionner sans modification. Les tests existants de `test_ledger.py` restent valides.

### 2.2 `custom_components/my_garden_irrigation/config_state.py`

**Méthode : `apply_midnight_transfer()` — lignes 322-329**

Passer `self._watering_applied_today` à `midnight_transfer()` :

```python
def apply_midnight_transfer(self, daily_needs: dict[str, float]) -> None:
    """Accumule les besoins journaliers au cumulé, déduit l'arrosage du jour, remet à zéro."""
    self._cumulative_need = midnight_transfer(
        self._cumulative_need,
        daily_needs,
        self._watering_applied_today,   # ← AJOUT : déduction Règle 1
    )
    _LOGGER.debug(
        "RuntimeConfigState : accumulation minuit — bilan cumulé : %s",
        {k: round(v, 1) for k, v in self._cumulative_need.items()},
    )
    self._watering_applied_today = {}
```

---

## 3. Correctif B — Volume inclusif pour les arrosages tardifs

### Règle métier cible (spec.md §3 Règle 2)

```
Si heure_arrosage >= seuil_soir :
    Volume_cible = Besoin_Cumulé + Besoin_Journalier_en_cours
```

### 3.1 `custom_components/my_garden_irrigation/const.py`

Ajouter à la fin du fichier la constante de seuil horaire :

```python
# --- Arrosage tardif (Anomalie B spec) ---
EVENING_IRRIGATION_HOUR_THRESHOLD = 12
"""Heure (incluse) à partir de laquelle l'arrosage est considéré 'tardif'.
Un arrosage tardif doit inclure le besoin journalier en cours dans son volume cible."""
```

### 3.2 `custom_components/my_garden_irrigation/coordinator.py`

**Import à ajouter** en haut du fichier (dans le bloc `from .const import ...`) :

```python
from .const import (
    ...
    EVENING_IRRIGATION_HOUR_THRESHOLD,
    ...
)
```

**Méthode : `fire_irrigation_event()` — lignes 244-297**

Remplacer la section qui calcule `total_cumulative`, `duration_minutes` et le `payload` :

```python
def fire_irrigation_event(self) -> bool:
    data = self.data
    if data is None:
        _LOGGER.warning(
            "Arrosage impossible : les données météo ne sont pas encore disponibles."
        )
        return False

    total_cumulative = sum(data.cumulative_need.values())

    # Règle 2 (spec) : pour un arrosage tardif, inclure le besoin journalier en cours
    try:
        h = int(self.config.irrigation_time.split(":")[0])
        is_evening = h >= EVENING_IRRIGATION_HOUR_THRESHOLD
    except (ValueError, AttributeError, IndexError):
        is_evening = False

    if is_evening:
        total_volume = total_cumulative + data.total_daily_need_liters
    else:
        total_volume = total_cumulative

    if total_volume <= 0:
        _LOGGER.debug(
            "Arrosage auto : volume cible = 0 L (cumulé=%.1f, journalier=%.1f, mode=%s) — "
            "événement non émis.",
            total_cumulative,
            data.total_daily_need_liters,
            "soir" if is_evening else "matin",
        )
        return False

    flow_rate = self.config.flow_rate
    if flow_rate <= 0:
        _LOGGER.warning(
            "Arrosage auto : débit non configuré (%.1f L/h) — événement non émis.",
            flow_rate,
        )
        return False

    duration_minutes = round((total_volume / flow_rate) * 60, 1)
    is_fractioned = self.config.watering_mode == WATERING_MODE_FRACTIONED

    payload: dict[str, Any] = {
        "entry_id": self._entry.entry_id,
        "valve_entity_id": self.config.valve_entity_id,
        "total_volume_liters": round(total_volume, 1),       # ← total_volume, pas total_cumulative
        "recommended_duration_minutes": duration_minutes,
        "is_fractioned": is_fractioned,
    }
    if is_fractioned:
        cycles = max(1, self.config.cycles_count)
        payload["cycles_count"] = cycles
        payload["duration_per_cycle_minutes"] = round(duration_minutes / cycles, 1)
        payload["soak_duration_minutes"] = self.config.soak_duration_minutes
    else:
        cycles = 1

    self.config.begin_irrigation_session(cycles)
    self.hass.bus.async_fire(f"{DOMAIN}_irrigation_requested", payload)
    _LOGGER.info(
        "Événement %s_irrigation_requested émis — volume=%.1fL (cumulé=%.1fL + journalier=%.1fL), "
        "durée=%.1f min, mode=%s.",
        DOMAIN,
        total_volume,
        total_cumulative,
        data.total_daily_need_liters if is_evening else 0.0,
        duration_minutes,
        self.config.watering_mode,
    )
    return True
```

**Pourquoi ça fonctionne avec le Correctif A :**  
Quand la vanne se ferme, `ValveTracker` appelle `_on_volumes_applied(volumes)` avec le volume total distribué (incluant la partie journalière). `apply_watering_volumes()` met à jour `watering_applied_today`. Au passage de minuit, `apply_midnight_transfer()` calcule :  
`max(0, cumul + journalier - (cumul + journalier)) = 0` → dette soldée.

---

## 4. Correctif C — Immunisation temporelle du calendrier

### Règle métier cible (spec.md §3 Règle 3)

```
Si intervalle atteint :
    Mettre à jour last_auto_watering_date IMMÉDIATEMENT
    (que le volume distribué soit X litres ou 0 litre)
```

### 4.1 `custom_components/my_garden_irrigation/coordinator.py`

**Méthode : `_on_trigger()` — lignes 152-156**

La méthode actuelle ne met à jour la date que si `fire_irrigation_event()` retourne `True`, ce qui bloque la mise à jour quand le besoin est nul (pluie). Correction :

```python
async def _on_trigger(self, date_iso: str) -> None:
    """L'intervalle est atteint : déclencher l'arrosage puis ancrer la date.

    Règle 3 (spec) : la date est mise à jour dès que l'intervalle est validé,
    même si le volume distribué est 0 L (pluie, sol saturé). Exception : si les
    données météo sont indisponibles (data is None), on ne met pas à jour la date
    pour éviter de sauter un créneau sans avoir eu la chance d'arroser.
    """
    if self.data is None:
        _LOGGER.warning(
            "Arrosage auto ignoré : données météo indisponibles. "
            "Date du dernier arrosage non mise à jour — nouvelle tentative demain."
        )
        return

    self.fire_irrigation_event()           # émet si volume > 0, log debug si 0
    await self.update_last_watering_date(date_iso)   # ← toujours exécuté si data != None
```

**Suppression de la branche `else` :** le message "Calendrier préservé — Nouvelle tentative planifiée pour demain" est désormais caduc (c'est le comportement corrigé qui ne doit plus se produire). Le supprimer évite toute confusion dans les logs.

---

## 5. Tests à ajouter

### 5.1 `tests/test_ledger.py` — Correctif A

Ajouter à la suite des tests existants :

```python
# ---------------------------------------------------------------------------
# midnight_transfer — avec déduction arrosage (Règle 1 spec)
# ---------------------------------------------------------------------------

def test_midnight_transfer_deducts_watering_same_day():
    """Scénario I spec : arrosage matin, besoin soleil dans la journée → dette = 0."""
    # Jour 3 matin : arrosage 8 L soldant la dette passée
    # Jour 3 journée : soleil génère 4 L de besoin journalier
    # Minuit Jour 3 : max(0, 0 + 4 - 8) = 0
    cumulative = {"c1": 0.0}          # déjà remis à 0 par apply_watering_volumes au matin
    daily = {"c1": 4.0}
    watering = {"c1": 8.0}
    result = midnight_transfer(cumulative, daily, watering)
    assert result["c1"] == pytest.approx(0.0)

def test_midnight_transfer_partial_watering():
    """Arrosage partiel : seulement 3 L sur 8 L de dette + 4 L de journalier → 9 L restants."""
    cumulative = {"c1": 8.0}
    daily = {"c1": 4.0}
    watering = {"c1": 3.0}
    result = midnight_transfer(cumulative, daily, watering)
    assert result["c1"] == pytest.approx(9.0)

def test_midnight_transfer_no_negative_cumulative():
    """Le résultat ne peut jamais être négatif (le sol ne crédite pas)."""
    cumulative = {"c1": 2.0}
    daily = {"c1": 1.0}
    watering = {"c1": 50.0}   # sur-arrosage
    result = midnight_transfer(cumulative, daily, watering)
    assert result["c1"] == pytest.approx(0.0)

def test_midnight_transfer_backward_compat_no_watering_arg():
    """Sans argument watering_applied_today, comportement identique à l'ancienne version."""
    cumulative = {"c1": 10.0}
    daily = {"c1": 3.0}
    result = midnight_transfer(cumulative, daily)          # pas de 3e arg
    assert result["c1"] == pytest.approx(13.0)            # additionne comme avant

def test_midnight_transfer_watering_none():
    """watering_applied_today=None équivaut à aucun arrosage."""
    cumulative = {"c1": 10.0}
    daily = {"c1": 3.0}
    result = midnight_transfer(cumulative, daily, None)
    assert result["c1"] == pytest.approx(13.0)
```

### 5.2 `tests/test_config_state.py` — Correctif A

```python
def test_apply_midnight_transfer_deducts_watering():
    """Scénario I spec : la dette après minuit doit être 0 si arrosage >= cumulé + journalier."""
    from custom_components.my_garden_irrigation.config_state import RuntimeConfigState

    options = {"crops": [{"crop_id": "c1", "nb_plants": 4, "density": 1.0, ...}], ...}
    state = RuntimeConfigState(options)

    # Simuler : cumulé passé = 8 L, arrosage du jour = 8 L, besoin journalier = 4 L
    state._cumulative_need = {"c1": 0.0}      # apply_watering_volumes a déjà réduit à 0
    state._watering_applied_today = {"c1": 8.0}

    state.apply_midnight_transfer({"c1": 4.0})

    assert state.cumulative_need["c1"] == pytest.approx(0.0)
    assert state.watering_applied_today == {}   # remis à zéro

def test_apply_midnight_transfer_residual_debt():
    """Arrosage insuffisant → dette résiduelle correctement calculée."""
    from custom_components.my_garden_irrigation.config_state import RuntimeConfigState

    options = {...}
    state = RuntimeConfigState(options)
    state._cumulative_need = {"c1": 5.0}
    state._watering_applied_today = {"c1": 3.0}

    state.apply_midnight_transfer({"c1": 2.0})

    # max(0, 5 + 2 - 3) = 4
    assert state.cumulative_need["c1"] == pytest.approx(4.0)
```

### 5.3 `tests/test_resilience.py` — Correctifs B et C

Ajouter les scénarios II et III du spec :

```python
# ---------------------------------------------------------------------------
# Scénario II — volume inclusif pour arrosage du soir
# ---------------------------------------------------------------------------

async def test_evening_irrigation_includes_daily_need(hass, ...):
    """Scénario II spec : arrosage 21h00 → volume = cumul (8L) + journalier (4L) = 12L."""
    # Setup coordinator avec irrigation_time="21:00", cumulative=8L, daily_need=4L
    # Appeler fire_irrigation_event()
    # Vérifier que l'événement émis contient total_volume_liters=12.0
    ...

async def test_morning_irrigation_excludes_daily_need(hass, ...):
    """Arrosage 06h00 → volume = cumul seulement (pas de daily_need en extra)."""
    # Setup coordinator avec irrigation_time="06:00", cumulative=8L, daily_need=4L
    # Appeler fire_irrigation_event()
    # Vérifier que l'événement émis contient total_volume_liters=8.0
    ...

async def test_evening_irrigation_midnight_resets_to_zero(hass, ...):
    """Scénario II spec (suite) : après arrosage soir 12L, besoin cumulé à minuit = 0."""
    # Setup : cumulative=8L, daily_need=4L
    # Déclencher fire_irrigation_event() à 21h → 12L distribués
    # Simuler _on_volumes_applied({"c1": 12.0})
    # Simuler _on_midnight() avec daily_needs={"c1": 4.0}
    # Vérifier cumulative_need["c1"] == 0.0
    ...

# ---------------------------------------------------------------------------
# Scénario III — immunisation calendrier (Règle 3)
# ---------------------------------------------------------------------------

async def test_calendar_updated_even_if_no_irrigation(hass, ...):
    """Scénario III spec : intervalle atteint + pluie (cumul=0) → date mise à jour."""
    # Setup : watering_frequency=interval, interval=3j, last_date=Jour0, cumulative=0
    # Appeler _on_trigger("jour3")
    # Vérifier que last_auto_watering_date == "jour3" malgré cumul=0
    ...

async def test_calendar_not_updated_if_no_weather_data(hass, ...):
    """Si data is None, la date ne doit PAS être mise à jour (erreur technique)."""
    # Setup coordinator avec self.data=None
    # Appeler _on_trigger("jour3")
    # Vérifier que last_auto_watering_date n'a pas changé
    ...

async def test_next_irrigation_scheduled_at_day6_not_day8(hass, ...):
    """Conséquence Scénario III : Jour0 → Jour3 (date ancée) → prochain = Jour6."""
    # Vérifier qu'après _on_trigger("2024-01-03") avec cumul=0,
    # last_auto_watering_date == "2024-01-03"
    # Et que le scheduler ne déclenchera pas avant "2024-01-06"
    ...
```

---

## 6. Récapitulatif des modifications par fichier

| Fichier | Modification | Lignes actuelles |
|---|---|---|
| `core/ledger.py` | `midnight_transfer()` : +1 paramètre, formule avec soustraction+plancher | L32-51 |
| `config_state.py` | `apply_midnight_transfer()` : passer `_watering_applied_today` à ledger | L322-329 |
| `const.py` | Ajouter `EVENING_IRRIGATION_HOUR_THRESHOLD = 12` | fin du fichier |
| `coordinator.py` | `fire_irrigation_event()` : volume inclusif si heure >= seuil soir | L244-297 |
| `coordinator.py` | `_on_trigger()` : mettre à jour la date si `data is not None` | L152-156 |
| `tests/test_ledger.py` | 5 nouveaux tests `midnight_transfer` avec watering | à la suite |
| `tests/test_config_state.py` | 2 nouveaux tests `apply_midnight_transfer` | à la suite |
| `tests/test_resilience.py` | 5 nouveaux tests Scénarios II et III | à la suite |

**Total : 5 fichiers source modifiés, 3 fichiers de tests étendus.**  
**Aucun changement de signature publique, aucune migration de données, rétrocompatibilité maintenue.**

---

## 7. Ordre d'implémentation recommandé

1. **`core/ledger.py`** — la fonction pure, le plus simple à tester en isolation  
2. **`config_state.py`** — l'appelant de ledger, une ligne à changer  
3. **Tests `test_ledger.py` + `test_config_state.py`** — valider Correctif A avant de toucher coordinator  
4. **`const.py`** — ajouter la constante  
5. **`coordinator.py` `fire_irrigation_event()`** — Correctif B  
6. **`coordinator.py` `_on_trigger()`** — Correctif C  
7. **Tests `test_resilience.py`** — valider B et C  
8. **`graphify update .`** — mettre à jour le graphe de connaissance

---

## 8. Points d'attention

- **`data.total_daily_need_liters`** dans `IrrigationData` (models.py L68) est bien la somme des `daily_need_liters` = `net_liters` = ETc − pluie efficace, **avant** soustraction de `watering_applied_today`. C'est exactement le "Besoin Journalier en cours" de la spec.
- **`data.cumulative_need`** dans `IrrigationData` est une copie du dict `_cumulative_need` de `RuntimeConfigState` au moment du calcul. Il est déjà réduit par `apply_watering_volumes()` si un arrosage a eu lieu dans la journée. C'est le "Besoin Cumulé" de la spec.
- Pour le Correctif B, si un arrosage manuel est survenu dans la journée avant l'arrosage automatique du soir, `total_daily_need_liters` ne tient pas compte de ce premier arrosage. Cela peut légèrement sur-arroser. Ce cas hors-spec n'est pas traité dans ce plan.
- Le `EVENING_IRRIGATION_HOUR_THRESHOLD = 12` est choisi conforme à la spec ("après 12h00 ou via une configuration 'Soir'"). Il n'est pas exposé en UI dans ce plan. Si une future version doit le rendre configurable, il faudra l'ajouter dans les options du `config_flow`.
