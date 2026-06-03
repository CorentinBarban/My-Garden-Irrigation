"""Tests des opérations comptables du bilan hydrique (core/ledger.py).

Fonctions pures — aucune dépendance HA, aucun mock nécessaire.
"""
from datetime import datetime

import pytest

from custom_components.my_garden_irrigation.core.ledger import (
    DailyWaterLedger,
    InclusiveEveningStrategy,
    StandardMorningStrategy,
    WaterSource,
    WaterTransaction,
    allocate_volume_by_surface,
    midnight_transfer,
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


# ---------------------------------------------------------------------------
# midnight_transfer — avec déduction arrosage (Règle 1 spec)
# ---------------------------------------------------------------------------

def test_midnight_transfer_deducts_watering_exact():
    """Scénario I spec : arrosage du matin soldant la dette + besoin journalier → 0."""
    # Jour 3 : cumul déjà remis à 0 par apply_watering_volumes (8L distribués),
    # besoin journalier du soleil = 4L, arrosage_du_jour = 8L
    # max(0, 0 + 4 - 8) = 0
    result = midnight_transfer({"c1": 0.0}, {"c1": 4.0}, {"c1": 8.0})
    assert result["c1"] == pytest.approx(0.0)

def test_midnight_transfer_deducts_watering_partial():
    """Arrosage insuffisant : dette résiduelle correctement calculée."""
    # max(0, 5 + 2 - 3) = 4
    result = midnight_transfer({"c1": 5.0}, {"c1": 2.0}, {"c1": 3.0})
    assert result["c1"] == pytest.approx(4.0)

def test_midnight_transfer_no_negative_cumulative():
    """Sur-arrosage : le résultat est clampé à 0, jamais négatif."""
    result = midnight_transfer({"c1": 2.0}, {"c1": 1.0}, {"c1": 50.0})
    assert result["c1"] == pytest.approx(0.0)

def test_midnight_transfer_backward_compat_no_watering_arg():
    """Sans troisième argument, comportement identique à l'ancienne version."""
    result = midnight_transfer({"c1": 10.0}, {"c1": 3.0})
    assert result["c1"] == pytest.approx(13.0)

def test_midnight_transfer_watering_none():
    """watering_applied_today=None équivaut à aucun arrosage."""
    result = midnight_transfer({"c1": 10.0}, {"c1": 3.0}, None)
    assert result["c1"] == pytest.approx(13.0)

def test_midnight_transfer_multi_crop_mixed():
    """Plusieurs cultures : chacune déduit son propre arrosage.

    apply_watering_volumes() réduit cumulative avant minuit :
    c1 arrosé 8L → cumul c1 déjà à 0 ; c2 non arrosé → cumul reste 4.
    """
    # cumul après apply_watering_volumes : c1 réduit à 0, c2 inchangé
    cumulative = {"c1": 0.0, "c2": 4.0}
    daily = {"c1": 4.0, "c2": 2.0}
    watering = {"c1": 8.0, "c2": 0.0}
    result = midnight_transfer(cumulative, daily, watering)
    assert result["c1"] == pytest.approx(0.0)   # max(0, 0 + 4 - 8) = 0
    assert result["c2"] == pytest.approx(6.0)   # max(0, 4 + 2 - 0) = 6

def test_midnight_transfer_does_not_mutate_inputs_with_watering():
    """Les dictionnaires d'entrée ne sont pas mutés."""
    cumulative = {"c1": 5.0}
    daily = {"c1": 2.0}
    watering = {"c1": 3.0}
    orig_c, orig_d, orig_w = dict(cumulative), dict(daily), dict(watering)
    midnight_transfer(cumulative, daily, watering)
    assert cumulative == orig_c
    assert daily == orig_d
    assert watering == orig_w


# ---------------------------------------------------------------------------
# ADR-024 — Strategy : Calcul adaptatif du volume d'arrosage
# ---------------------------------------------------------------------------

def test_morning_strategy_ignores_daily_need():
    """Scénario I spec : arrosage matinal → uniquement la dette historique."""
    s = StandardMorningStrategy()
    assert s.calculate_target_volume(cumulative_need=8.0, daily_need=4.0) == pytest.approx(8.0)

def test_morning_strategy_zero_cumulative():
    s = StandardMorningStrategy()
    assert s.calculate_target_volume(0.0, 4.0) == pytest.approx(0.0)

def test_evening_strategy_includes_daily_need():
    """Scénario II spec : arrosage tardif → dette + besoin journalier."""
    s = InclusiveEveningStrategy()
    assert s.calculate_target_volume(cumulative_need=8.0, daily_need=4.0) == pytest.approx(12.0)

def test_evening_strategy_zero_cumulative():
    s = InclusiveEveningStrategy()
    assert s.calculate_target_volume(0.0, 4.0) == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# ADR-026 — DailyWaterLedger
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 6, 3, 10, 0, 0)


def test_ledger_replay_net_balance():
    ledger = DailyWaterLedger()
    ledger.record(WaterTransaction("c1", 4.0, WaterSource.ETO, _NOW))
    ledger.record(WaterTransaction("c1", -3.0, WaterSource.IRRIGATION, _NOW))
    assert ledger.replay()["c1"] == pytest.approx(1.0)

def test_ledger_replay_no_negative():
    """Sur-arrosage : le solde est clampé à 0."""
    ledger = DailyWaterLedger()
    ledger.record(WaterTransaction("c1", 4.0, WaterSource.ETO, _NOW))
    ledger.record(WaterTransaction("c1", -10.0, WaterSource.IRRIGATION, _NOW))
    assert ledger.replay()["c1"] == pytest.approx(0.0)

def test_ledger_replay_empty():
    assert DailyWaterLedger().replay() == {}

def test_ledger_replay_multi_crop():
    ledger = DailyWaterLedger()
    ledger.record(WaterTransaction("c1", 4.0, WaterSource.ETO, _NOW))
    ledger.record(WaterTransaction("c2", 2.0, WaterSource.ETO, _NOW))
    ledger.record(WaterTransaction("c1", -4.0, WaterSource.IRRIGATION, _NOW))
    result = ledger.replay()
    assert result["c1"] == pytest.approx(0.0)
    assert result["c2"] == pytest.approx(2.0)

def test_ledger_bool_empty():
    assert not DailyWaterLedger()

def test_ledger_bool_non_empty():
    ledger = DailyWaterLedger()
    ledger.record(WaterTransaction("c1", 1.0, WaterSource.ETO, _NOW))
    assert ledger

def test_ledger_roundtrip_storage():
    """to_storage / from_storage préserve le résultat du replay."""
    ledger = DailyWaterLedger()
    ledger.record(WaterTransaction("c1", 4.0, WaterSource.ETO, _NOW))
    ledger.record(WaterTransaction("c1", -1.5, WaterSource.IRRIGATION, _NOW))
    restored = DailyWaterLedger.from_storage(ledger.to_storage())
    assert restored.replay()["c1"] == pytest.approx(2.5)

def test_ledger_roundtrip_empty():
    restored = DailyWaterLedger.from_storage([])
    assert restored.replay() == {}
