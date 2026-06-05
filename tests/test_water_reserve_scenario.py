"""Scénario réel — réserve d'eau après plusieurs jours de pluie (ADR-028).

Déroule 4 jours de bout en bout au niveau des fonctions pures, en suivant le même
enchaînement que le coordinator :

    météo → bilan signé du jour → journal → décision d'arrosage → (arrosage) → minuit

Vérifie que le surplus de pluie est mis en réserve (bilan cumulé négatif), qu'aucun
arrosage n'a lieu tant que la réserve couvre le besoin, que le cycle d'intervalle n'est
PAS réancré sur un jour sauté, et que l'arrosage reprend dès que la réserve est épuisée.

Surface : 6 m² (6 plants, densité 1) → 1 mm = 6 L. Facteur de pluie efficace 0,8 conservé
(ADR-007), donc 15 mm → 12 mm efficaces → 72 L (et non 90 L).
"""
from datetime import datetime

import pytest

from custom_components.my_garden_irrigation.config_state import RuntimeConfigState
from custom_components.my_garden_irrigation.const import (
    CONF_CROPS,
    CONF_CROP_ID,
    CONF_CROP_TYPE,
    CONF_DENSITY,
    CONF_GLOBAL_FLOW_RATE,
    CONF_NB_PLANTS,
    CONF_STAGE,
)
from custom_components.my_garden_irrigation.core.calculations import compute_irrigation_data
from custom_components.my_garden_irrigation.core.journal import (
    DailyWaterLedger,
    WaterSource,
    WaterTransaction,
)
from custom_components.my_garden_irrigation.core.ledger import MidnightClosureOrchestrator
from custom_components.my_garden_irrigation.core.strategies import WateringStrategyFactory

_CROP_ID = "c1"
_KC_DATA = {"crops": {"tomate": {"mid": 1.0}}}
_NOW = datetime(2026, 6, 1, 12, 0, 0)


def _kc_getter(kc_data, crop_type, stage):
    return kc_data.get("crops", {}).get(crop_type, {}).get(stage)


def _state() -> RuntimeConfigState:
    """Potager d'une culture occupant 6 m² (6 plants ÷ densité 1), bilan initial à 0."""
    crop = {
        CONF_CROP_ID: _CROP_ID,
        CONF_CROP_TYPE: "tomate",
        CONF_STAGE: "mid",
        CONF_NB_PLANTS: 6,
        CONF_DENSITY: 1.0,
    }
    state = RuntimeConfigState({CONF_CROPS: [crop], CONF_GLOBAL_FLOW_RATE: 360.0})
    state._cumulative_need = {_CROP_ID: 0.0}
    return state


class _DayResult:
    def __init__(self, balance, target_volume, fired, cumulative_after_midnight):
        self.balance = balance
        self.target_volume = target_volume
        self.fired = fired
        self.cumulative_after_midnight = cumulative_after_midnight


def _run_day(state: RuntimeConfigState, eto_mm: float, precipitation_mm: float) -> _DayResult:
    """Simule une journée complète et renvoie ses grandeurs clés.

    1. Calcule le bilan signé du jour (météo) et l'enregistre au journal.
    2. Décide l'arrosage : volume = max(0, cumulé + bilan du jour) [décision inclusive].
    3. Si arrosage : impute le volume au bilan cumulé (apply_watering_volumes) + journal.
    4. Clôture de minuit : ajoute le bilan signé du jour au cumulé (arrosage exclu).
    """
    ledger = DailyWaterLedger()

    data = compute_irrigation_data(
        crops=state.crops,
        kc_data=_KC_DATA,
        eto_mm=eto_mm,
        precipitation_mm=precipitation_mm,
        kc_getter=_kc_getter,
        cumulative_need=state.cumulative_need,
    )
    ledger.set_daily_need(_CROP_ID, data.crops[_CROP_ID].daily_balance_liters, _NOW)

    # Décision d'arrosage (inclusive, indépendante de l'heure — ADR-028).
    strategy = WateringStrategyFactory.from_irrigation_time("06:00:00")
    target = strategy.calculate_target_volume(
        sum(state.cumulative_need.values()), data.total_daily_balance_liters
    )
    fired = target > 0
    if fired:
        # La vanne distribue exactement le volume cible (au prorata de la surface).
        state.apply_watering_volumes({_CROP_ID: target})
        ledger.record(WaterTransaction(_CROP_ID, -target, WaterSource.IRRIGATION, _NOW))

    # Clôture de minuit.
    new_cumulative = MidnightClosureOrchestrator().execute(
        state.cumulative_need, ledger.replay()
    )
    state.apply_midnight_result(new_cumulative)

    return _DayResult(
        balance=data.total_daily_balance_liters,
        target_volume=target,
        fired=fired,
        cumulative_after_midnight=state.cumulative_need[_CROP_ID],
    )


def test_rain_surplus_builds_reserve_then_waters_when_depleted():
    """Scénario complet sur 4 jours (facteur 0,8, surface 6 m²)."""
    state = _state()

    # J1 — pluie 15 mm, aucun besoin : 72 L de surplus banqués.
    j1 = _run_day(state, eto_mm=0.0, precipitation_mm=15.0)
    assert j1.balance == pytest.approx(-72.0)
    assert j1.fired is False
    assert j1.cumulative_after_midnight == pytest.approx(-72.0)

    # J2 — pluie 10 mm, aucun besoin : réserve portée à 120 L.
    j2 = _run_day(state, eto_mm=0.0, precipitation_mm=10.0)
    assert j2.balance == pytest.approx(-48.0)
    assert j2.fired is False
    assert j2.cumulative_after_midnight == pytest.approx(-120.0)

    # J3 — beau, besoin 40 L. L'intervalle de 3 j est atteint mais la réserve couvre :
    # aucun arrosage, pas de réancrage du cycle. Réserve : −120 + 40 = −80 L.
    j3 = _run_day(state, eto_mm=40.0 / 6.0, precipitation_mm=0.0)
    assert j3.balance == pytest.approx(40.0)
    assert j3.fired is False, "La réserve couvre le besoin du J3 → aucun arrosage"
    assert j3.cumulative_after_midnight == pytest.approx(-80.0)

    # J4 — besoin 120 L. Réserve −80 + besoin 120 = +40 → arrose 40 L (réévalué le
    # lendemain car le cycle n'a pas été réancré au J3). Le bilan revient à 0.
    j4 = _run_day(state, eto_mm=20.0, precipitation_mm=0.0)
    assert j4.balance == pytest.approx(120.0)
    assert j4.fired is True, "Réserve épuisée → l'arrosage doit se déclencher au J4"
    assert j4.target_volume == pytest.approx(40.0)
    assert j4.cumulative_after_midnight == pytest.approx(0.0)


def test_reserve_persists_between_days_without_watering():
    """Sans aucun arrosage, le surplus s'accumule linéairement en réserve."""
    state = _state()
    _run_day(state, eto_mm=0.0, precipitation_mm=15.0)   # −72
    _run_day(state, eto_mm=0.0, precipitation_mm=10.0)   # −120
    assert state.cumulative_need[_CROP_ID] == pytest.approx(-120.0)
