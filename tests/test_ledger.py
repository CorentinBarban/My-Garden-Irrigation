"""Tests des opérations comptables du bilan hydrique.

Fonctions pures — aucune dépendance HA, aucun mock nécessaire.

Modules couverts :
  core/ledger.py     — allocate_volume_by_surface, midnight_transfer, MidnightClosureOrchestrator
  core/strategies.py — StandardMorningStrategy, InclusiveEveningStrategy, WateringStrategyFactory
  core/journal.py    — WaterSource, WaterTransaction, DailyWaterLedger
"""
from datetime import datetime

import pytest

from custom_components.my_garden_irrigation.core.journal import (
    DailyWaterLedger,
    WaterSource,
    WaterTransaction,
)
from custom_components.my_garden_irrigation.core.ledger import (
    MidnightClosureOrchestrator,
    allocate_volume_by_surface,
    midnight_transfer,
)
from custom_components.my_garden_irrigation.core.strategies import (
    InclusiveWateringStrategy,
    WateringStrategyFactory,
)


# ---------------------------------------------------------------------------
# allocate_volume_by_surface
# ---------------------------------------------------------------------------

def test_allocate_equal_surfaces():
    surfaces = {"c1": 5.0, "c2": 5.0}
    result = allocate_volume_by_surface(20.0, surfaces)
    assert result["c1"] == pytest.approx(10.0)
    assert result["c2"] == pytest.approx(10.0)

def test_allocate_proportional():
    # c1 = 10m², c2 = 30m² → ratio 1:3 → c1=5L, c2=15L
    surfaces = {"c1": 10.0, "c2": 30.0}
    result = allocate_volume_by_surface(20.0, surfaces)
    assert result["c1"] == pytest.approx(5.0)
    assert result["c2"] == pytest.approx(15.0)

def test_allocate_single_crop():
    surfaces = {"c1": 10.0}
    result = allocate_volume_by_surface(15.0, surfaces)
    assert result["c1"] == pytest.approx(15.0)

def test_allocate_sum_equals_total():
    surfaces = {"c1": 3.0, "c2": 7.0, "c3": 5.0}
    total = 30.0
    result = allocate_volume_by_surface(total, surfaces)
    assert sum(result.values()) == pytest.approx(total)

def test_allocate_zero_volume():
    surfaces = {"c1": 5.0, "c2": 5.0}
    result = allocate_volume_by_surface(0.0, surfaces)
    assert result == {}

def test_allocate_zero_surface():
    surfaces = {"c1": 0.0, "c2": 0.0}
    result = allocate_volume_by_surface(20.0, surfaces)
    assert result == {}

def test_allocate_empty_surfaces():
    result = allocate_volume_by_surface(20.0, {})
    assert result == {}

def test_allocate_does_not_mutate_input():
    surfaces = {"c1": 5.0, "c2": 5.0}
    original = dict(surfaces)
    allocate_volume_by_surface(10.0, surfaces)
    assert surfaces == original


# ---------------------------------------------------------------------------
# midnight_transfer
# ---------------------------------------------------------------------------

def test_midnight_transfer_accumulates():
    cumulative = {"c1": 10.0, "c2": 5.0}
    daily = {"c1": 3.0, "c2": 2.0}
    result = midnight_transfer(cumulative, daily)
    assert result["c1"] == pytest.approx(13.0)
    assert result["c2"] == pytest.approx(7.0)

def test_midnight_transfer_new_crop():
    # c2 n'existe pas encore dans le cumulé
    cumulative = {"c1": 10.0}
    daily = {"c1": 3.0, "c2": 5.0}
    result = midnight_transfer(cumulative, daily)
    assert result["c1"] == pytest.approx(13.0)
    assert result["c2"] == pytest.approx(5.0)

def test_midnight_transfer_empty_daily():
    cumulative = {"c1": 10.0}
    result = midnight_transfer(cumulative, {})
    assert result == {"c1": 10.0}

def test_midnight_transfer_empty_cumulative():
    result = midnight_transfer({}, {"c1": 5.0})
    assert result == {"c1": pytest.approx(5.0)}

def test_midnight_transfer_does_not_mutate_inputs():
    cumulative = {"c1": 10.0}
    daily = {"c1": 3.0}
    orig_cum = dict(cumulative)
    orig_daily = dict(daily)
    midnight_transfer(cumulative, daily)
    assert cumulative == orig_cum
    assert daily == orig_daily

def test_midnight_transfer_returns_new_dict():
    cumulative = {"c1": 10.0}
    daily = {"c1": 3.0}
    result = midnight_transfer(cumulative, daily)
    assert result is not cumulative

def test_midnight_transfer_allows_negative_reserve():
    """ADR-028 : un bilan du jour négatif (surplus de pluie) crée une réserve (cumulé < 0)."""
    result = midnight_transfer({"c1": 1.0}, {"c1": -5.0})
    assert result["c1"] == pytest.approx(-4.0)


# ---------------------------------------------------------------------------
# ADR-028 — Décision inclusive unique (remplace ADR-024 matin/soir)
# ---------------------------------------------------------------------------

def test_inclusive_strategy_adds_daily_balance():
    """Volume = dette cumulée + bilan net du jour, à toute heure."""
    s = InclusiveWateringStrategy()
    assert s.calculate_target_volume(cumulative_need=8.0, daily_balance=4.0) == pytest.approx(12.0)

def test_inclusive_strategy_zero_cumulative():
    s = InclusiveWateringStrategy()
    assert s.calculate_target_volume(0.0, 4.0) == pytest.approx(4.0)

def test_inclusive_strategy_negative_reserve_offsets_need():
    """Une réserve cumulée (cumulé < 0) réduit le volume cible : −10 réserve + 4 besoin = −6."""
    s = InclusiveWateringStrategy()
    assert s.calculate_target_volume(cumulative_need=-10.0, daily_balance=4.0) == pytest.approx(-6.0)

def test_inclusive_strategy_rainy_day_balance_negative():
    """Un bilan du jour négatif (pluie) réduit aussi le volume : 8 dette − 5 pluie = 3."""
    s = InclusiveWateringStrategy()
    assert s.calculate_target_volume(cumulative_need=8.0, daily_balance=-5.0) == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# ADR-028 — WateringStrategyFactory (stratégie unique, indépendante de l'heure)
# ---------------------------------------------------------------------------

def test_factory_returns_inclusive_morning():
    s = WateringStrategyFactory.from_irrigation_time("06:00:00")
    assert isinstance(s, InclusiveWateringStrategy)

def test_factory_returns_inclusive_evening():
    s = WateringStrategyFactory.from_irrigation_time("21:30:00")
    assert isinstance(s, InclusiveWateringStrategy)

def test_factory_returns_inclusive_invalid_time():
    s = WateringStrategyFactory.from_irrigation_time("invalid")
    assert isinstance(s, InclusiveWateringStrategy)


# ---------------------------------------------------------------------------
# ADR-023 — MidnightClosureOrchestrator
# ---------------------------------------------------------------------------

def test_orchestrator_accumulates():
    orch = MidnightClosureOrchestrator()
    result = orch.execute({"c1": 10.0}, {"c1": 3.0})
    assert result["c1"] == pytest.approx(13.0)

def test_orchestrator_allows_negative_reserve():
    """ADR-028 : l'orchestrateur reporte un surplus en réserve (cumulé signé négatif)."""
    orch = MidnightClosureOrchestrator()
    result = orch.execute({"c1": 1.0}, {"c1": -50.0})
    assert result["c1"] == pytest.approx(-49.0)

def test_orchestrator_does_not_mutate():
    cumulative = {"c1": 5.0}
    daily = {"c1": 2.0}
    orig_c, orig_d = dict(cumulative), dict(daily)
    MidnightClosureOrchestrator().execute(cumulative, daily)
    assert cumulative == orig_c
    assert daily == orig_d


# ---------------------------------------------------------------------------
# ADR-026 — DailyWaterLedger
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 6, 3, 10, 0, 0)


def test_ledger_replay_excludes_irrigation():
    """ADR-028 : replay ne somme que l'apport ETo/pluie ; l'arrosage est exclu (imputé ailleurs)."""
    ledger = DailyWaterLedger()
    ledger.record(WaterTransaction("c1", 4.0, WaterSource.ETO, _NOW))
    ledger.record(WaterTransaction("c1", -3.0, WaterSource.IRRIGATION, _NOW))
    assert ledger.replay()["c1"] == pytest.approx(4.0)

def test_ledger_replay_negative_on_rain_surplus():
    """Un apport ETo signé négatif (surplus de pluie) donne un bilan du jour négatif."""
    ledger = DailyWaterLedger()
    ledger.record(WaterTransaction("c1", -72.0, WaterSource.ETO, _NOW))
    assert ledger.replay()["c1"] == pytest.approx(-72.0)

def test_ledger_replay_empty():
    assert DailyWaterLedger().replay() == {}

def test_ledger_replay_multi_crop():
    ledger = DailyWaterLedger()
    ledger.record(WaterTransaction("c1", 4.0, WaterSource.ETO, _NOW))
    ledger.record(WaterTransaction("c2", 2.0, WaterSource.ETO, _NOW))
    ledger.record(WaterTransaction("c1", -4.0, WaterSource.IRRIGATION, _NOW))
    result = ledger.replay()
    assert result["c1"] == pytest.approx(4.0)  # arrosage exclu du bilan de minuit
    assert result["c2"] == pytest.approx(2.0)

def test_ledger_bool_empty():
    assert not DailyWaterLedger()

def test_ledger_bool_non_empty():
    ledger = DailyWaterLedger()
    ledger.record(WaterTransaction("c1", 1.0, WaterSource.ETO, _NOW))
    assert ledger

def test_ledger_roundtrip_storage():
    """to_storage / from_storage préserve replay (ETo) et applied_volumes (arrosage)."""
    ledger = DailyWaterLedger()
    ledger.record(WaterTransaction("c1", 4.0, WaterSource.ETO, _NOW))
    ledger.record(WaterTransaction("c1", -1.5, WaterSource.IRRIGATION, _NOW))
    restored = DailyWaterLedger.from_storage(ledger.to_storage())
    assert restored.replay()["c1"] == pytest.approx(4.0)         # bilan ETo (arrosage exclu)
    assert restored.applied_volumes()["c1"] == pytest.approx(1.5)  # arrosage conservé

def test_ledger_roundtrip_empty():
    restored = DailyWaterLedger.from_storage([])
    assert restored.replay() == {}


# ---------------------------------------------------------------------------
# ADR-026 — set_daily_need (ETo idempotent) + applied_volumes
# ---------------------------------------------------------------------------

def test_set_daily_need_is_idempotent_per_crop():
    """Plusieurs refresh météo n'ajoutent pas le besoin ETo plusieurs fois (anti sur-comptage)."""
    ledger = DailyWaterLedger()
    ledger.set_daily_need("c1", 5.0, _NOW)
    ledger.set_daily_need("c1", 5.0, _NOW)
    ledger.set_daily_need("c1", 5.0, _NOW)
    assert ledger.replay()["c1"] == pytest.approx(5.0)

def test_set_daily_need_replaces_with_latest_value():
    """Le dernier besoin ETo connu remplace le précédent."""
    ledger = DailyWaterLedger()
    ledger.set_daily_need("c1", 5.0, _NOW)
    ledger.set_daily_need("c1", 7.0, _NOW)
    assert ledger.replay()["c1"] == pytest.approx(7.0)

def test_set_daily_need_preserves_irrigation():
    """Le remplacement de l'apport ETo ne touche pas les transactions d'arrosage."""
    ledger = DailyWaterLedger()
    ledger.set_daily_need("c1", 5.0, _NOW)
    ledger.record(WaterTransaction("c1", -2.0, WaterSource.IRRIGATION, _NOW))
    ledger.set_daily_need("c1", 5.0, _NOW)  # nouveau refresh météo
    assert ledger.replay()["c1"] == pytest.approx(5.0)             # bilan ETo seul (arrosage exclu)
    assert ledger.applied_volumes()["c1"] == pytest.approx(2.0)   # arrosage toujours présent

def test_applied_volumes_sums_irrigation_as_positive():
    ledger = DailyWaterLedger()
    ledger.set_daily_need("c1", 5.0, _NOW)
    ledger.record(WaterTransaction("c1", -2.0, WaterSource.IRRIGATION, _NOW))
    ledger.record(WaterTransaction("c1", -1.5, WaterSource.IRRIGATION, _NOW))
    assert ledger.applied_volumes()["c1"] == pytest.approx(3.5)

def test_applied_volumes_ignores_eto():
    """applied_volumes ne reflète que les arrosages, pas l'apport ETo."""
    ledger = DailyWaterLedger()
    ledger.set_daily_need("c1", 5.0, _NOW)
    assert ledger.applied_volumes() == {}

def test_applied_volumes_empty():
    assert DailyWaterLedger().applied_volumes() == {}
