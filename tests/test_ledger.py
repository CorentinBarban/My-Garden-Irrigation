"""Tests des opérations comptables du bilan hydrique (core/ledger.py).

Fonctions pures — aucune dépendance HA, aucun mock nécessaire.
"""
import pytest
from custom_components.my_garden_irrigation.core.ledger import (
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
