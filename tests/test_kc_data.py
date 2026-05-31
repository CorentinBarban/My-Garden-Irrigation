"""Tests des accesseurs Kc FAO-56 (core/kc_data.py).

Fonctions pures — aucune dépendance HA, aucun mock nécessaire.
"""
import pytest
from custom_components.my_garden_irrigation.core.kc_data import (
    get_default_density,
    get_kc,
    is_valid_crop,
    list_crop_types,
)

_KC_DATA = {
    "crops": {
        "tomate": {"ini": 0.6, "mid": 1.15, "end": 0.8, "density_default": "3.0"},
        "laitue": {"ini": 0.7, "mid": 1.0,  "end": 0.95},
    }
}


# ---------------------------------------------------------------------------
# get_kc
# ---------------------------------------------------------------------------

def test_get_kc_valid():
    assert get_kc(_KC_DATA, "tomate", "mid") == pytest.approx(1.15)

def test_get_kc_all_stages():
    assert get_kc(_KC_DATA, "tomate", "ini") == pytest.approx(0.6)
    assert get_kc(_KC_DATA, "tomate", "end") == pytest.approx(0.8)

def test_get_kc_unknown_crop():
    assert get_kc(_KC_DATA, "papaya", "mid") is None

def test_get_kc_unknown_stage():
    assert get_kc(_KC_DATA, "tomate", "unknown_stage") is None

def test_get_kc_empty_data():
    assert get_kc({}, "tomate", "mid") is None


# ---------------------------------------------------------------------------
# get_default_density
# ---------------------------------------------------------------------------

def test_get_default_density_present():
    assert get_default_density(_KC_DATA, "tomate") == pytest.approx(3.0)

def test_get_default_density_absent():
    # laitue n'a pas de density_default dans nos données de test
    assert get_default_density(_KC_DATA, "laitue") is None

def test_get_default_density_unknown_crop():
    assert get_default_density(_KC_DATA, "unknown") is None


# ---------------------------------------------------------------------------
# list_crop_types
# ---------------------------------------------------------------------------

def test_list_crop_types():
    crops = list_crop_types(_KC_DATA)
    assert "tomate" in crops
    assert "laitue" in crops

def test_list_crop_types_empty():
    assert list_crop_types({}) == []

def test_list_crop_types_count():
    assert len(list_crop_types(_KC_DATA)) == 2


# ---------------------------------------------------------------------------
# is_valid_crop
# ---------------------------------------------------------------------------

def test_is_valid_crop_known():
    assert is_valid_crop(_KC_DATA, "tomate") is True

def test_is_valid_crop_unknown():
    assert is_valid_crop(_KC_DATA, "unknown_plant") is False

def test_is_valid_crop_empty_data():
    assert is_valid_crop({}, "tomate") is False
