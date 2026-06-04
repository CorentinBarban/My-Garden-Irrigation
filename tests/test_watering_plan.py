"""Tests du calcul du plan d'arrosage (durée, cycles, soak).

Fonction pure — aucune dépendance HA, aucun mock nécessaire.
Couvre core/watering_plan.py — source unique partagée par coordinator et sensor.
"""
import pytest

from custom_components.my_garden_irrigation.core.watering_plan import (
    WateringPlan,
    compute_watering_plan,
)


def _plan(**overrides) -> WateringPlan:
    args = {
        "target_volume_liters": 30.0,
        "flow_rate_lph": 60.0,
        "is_fractioned": False,
        "cycles_count": 1,
        "soak_duration_minutes": 0,
    }
    args.update(overrides)
    return compute_watering_plan(**args)


def test_duration_from_volume_and_flow():
    # 30 L à 60 L/h = 0,5 h = 30 min
    assert _plan().duration_minutes == pytest.approx(30.0)


def test_zero_volume_gives_zero_duration():
    assert _plan(target_volume_liters=0.0).duration_minutes == 0.0


def test_negative_volume_gives_zero_duration():
    assert _plan(target_volume_liters=-5.0).duration_minutes == 0.0


def test_zero_flow_rate_gives_zero_duration():
    assert _plan(flow_rate_lph=0.0).duration_minutes == 0.0


def test_negative_flow_rate_gives_zero_duration():
    assert _plan(flow_rate_lph=-10.0).duration_minutes == 0.0


def test_continuous_mode_has_single_cycle():
    plan = _plan(is_fractioned=False, cycles_count=4)
    assert plan.cycles_count == 4
    assert plan.duration_per_cycle_minutes == pytest.approx(7.5)  # 30 / 4


def test_fractioned_splits_duration_per_cycle():
    plan = _plan(is_fractioned=True, cycles_count=3, soak_duration_minutes=10)
    assert plan.is_fractioned is True
    assert plan.cycles_count == 3
    assert plan.duration_per_cycle_minutes == pytest.approx(10.0)  # 30 / 3
    assert plan.soak_duration_minutes == 10


def test_cycles_count_floored_to_one():
    plan = _plan(cycles_count=0)
    assert plan.cycles_count == 1
    assert plan.duration_per_cycle_minutes == pytest.approx(30.0)


def test_target_volume_rounded():
    assert _plan(target_volume_liters=12.345).target_volume_liters == pytest.approx(12.3)
