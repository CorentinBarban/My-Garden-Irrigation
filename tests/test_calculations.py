"""Tests des fonctions de calcul FAO-56 (core/calculations.py).

Fonctions pures — aucune dépendance HA, aucun mock nécessaire.
"""
import pytest
from custom_components.my_garden_irrigation.const import FAO56_MULCH_STAGE_FACTORS
from custom_components.my_garden_irrigation.core.calculations import (
    apply_mulch_factor,
    compute_balance_liters,
    compute_crop_result,
    compute_effective_rainfall_mm,
    compute_etc_liters,
    compute_irrigation_data,
    compute_net_liters,
    compute_surface_m2,
)


# ---------------------------------------------------------------------------
# compute_surface_m2
# ---------------------------------------------------------------------------

def test_surface_basic():
    assert compute_surface_m2(10, 2.0) == pytest.approx(5.0)

def test_surface_high_density():
    # 60 carottes à 60 plants/m² → 1 m²
    assert compute_surface_m2(60, 60.0) == pytest.approx(1.0)

def test_surface_fraction():
    # 1 plant à 0.5 plants/m² → 2 m²
    assert compute_surface_m2(1, 0.5) == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# compute_etc_liters
# ---------------------------------------------------------------------------

def test_etc_liters_basic():
    # Kc=0.5, ETo=4mm, surface=10m² → 0.5×4×10 = 20 L
    assert compute_etc_liters(0.5, 4.0, 10.0) == pytest.approx(20.0)

def test_etc_liters_zero_eto():
    assert compute_etc_liters(1.0, 0.0, 5.0) == pytest.approx(0.0)

def test_etc_liters_zero_surface():
    assert compute_etc_liters(1.0, 4.0, 0.0) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# compute_effective_rainfall_mm
# ---------------------------------------------------------------------------

def test_effective_rainfall_factor():
    # ADR-007 : facteur 0.8
    assert compute_effective_rainfall_mm(10.0) == pytest.approx(8.0)

def test_effective_rainfall_zero():
    assert compute_effective_rainfall_mm(0.0) == pytest.approx(0.0)

def test_effective_rainfall_heavy():
    assert compute_effective_rainfall_mm(50.0) == pytest.approx(40.0)


# ---------------------------------------------------------------------------
# compute_net_liters
# ---------------------------------------------------------------------------

def test_net_liters_no_rain():
    # ETc=20L, rain=0mm, surface=10m² → 20L net
    assert compute_net_liters(20.0, 0.0, 10.0) == pytest.approx(20.0)

def test_net_liters_rain_covers_all():
    # ETc=10L sur 10m² = 1mm, rain efficace=5mm → max(0, 1-5)×10 = 0
    assert compute_net_liters(10.0, 5.0, 10.0) == pytest.approx(0.0)

def test_net_liters_partial_rain():
    # ETc=20L sur 10m² = 2mm, rain=1mm → (2-1)×10 = 10L
    assert compute_net_liters(20.0, 1.0, 10.0) == pytest.approx(10.0)

def test_net_liters_zero_surface():
    assert compute_net_liters(0.0, 5.0, 0.0) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# compute_balance_liters (signé, ADR-028)
# ---------------------------------------------------------------------------

def test_balance_liters_deficit_positive():
    # ETc=20L sur 10m² = 2mm, pluie eff=1mm → (2-1)×10 = +10L (dette)
    assert compute_balance_liters(20.0, 1.0, 10.0) == pytest.approx(10.0)

def test_balance_liters_rain_surplus_negative():
    # ETc=10L sur 10m² = 1mm, pluie eff=5mm → (1-5)×10 = −40L (surplus → réserve)
    assert compute_balance_liters(10.0, 5.0, 10.0) == pytest.approx(-40.0)

def test_balance_liters_no_eto_full_surplus():
    # Besoin nul, 12mm de pluie efficace sur 6m² → −72L
    assert compute_balance_liters(0.0, 12.0, 6.0) == pytest.approx(-72.0)

def test_net_liters_is_floored_balance():
    """compute_net_liters = max(0, compute_balance_liters)."""
    assert compute_net_liters(10.0, 5.0, 10.0) == pytest.approx(0.0)
    assert compute_balance_liters(10.0, 5.0, 10.0) == pytest.approx(-40.0)


# ---------------------------------------------------------------------------
# apply_mulch_factor (paillage phasé FAO 56, ADR-029)
# ---------------------------------------------------------------------------

def test_mulch_inactive_returns_etc_unchanged():
    assert apply_mulch_factor(100.0, "ini", mulch_active=False) == pytest.approx(100.0)

def test_mulch_active_ini_strong_attenuation():
    # Stade initial : sol nu, abattement fort (−45 %)
    assert apply_mulch_factor(100.0, "ini", mulch_active=True) == pytest.approx(55.0)

def test_mulch_active_mid_marginal_attenuation():
    # Mi-saison : canopée complète, abattement marginal (−10 %)
    assert apply_mulch_factor(100.0, "mid", mulch_active=True) == pytest.approx(90.0)

def test_mulch_active_end_attenuation():
    assert apply_mulch_factor(100.0, "end", mulch_active=True) == pytest.approx(85.0)

def test_mulch_unknown_stage_no_attenuation():
    # Stade inconnu (ex. "dev" non défini) → facteur 1,0 (comportement sûr)
    assert apply_mulch_factor(100.0, "dev", mulch_active=True) == pytest.approx(100.0)

def test_mulch_factors_match_stage_ordering():
    # L'abattement décroît à mesure que la canopée ombrage le sol : ini < mid < end < 1
    assert (
        FAO56_MULCH_STAGE_FACTORS["ini"]
        < FAO56_MULCH_STAGE_FACTORS["end"]
        < FAO56_MULCH_STAGE_FACTORS["mid"]
        < 1.0
    )


# ---------------------------------------------------------------------------
# compute_crop_result
# ---------------------------------------------------------------------------

def test_crop_result_basic():
    result = compute_crop_result(
        nb_plants=10,
        density=2.0,
        kc=0.7,
        eto_mm=4.0,
        precipitation_mm=0.0,
        crop_type="tomate",
        stage="mid",
    )
    assert result.surface_m2 == pytest.approx(5.0)
    assert result.etc_liters == pytest.approx(0.7 * 4.0 * 5.0)
    assert result.effective_rainfall_mm == pytest.approx(0.0)
    assert result.liters == pytest.approx(result.etc_liters, abs=0.1)
    assert result.crop_type == "tomate"
    assert result.stage == "mid"
    assert result.nb_plants == 10

def test_crop_result_with_rain():
    # Tomate, 10 plants, 2 pl/m², surface=5m², Kc=1.05, ETo=5mm
    # ETc = 1.05*5*5 = 26.25L, rain=20mm → eff_rain=16mm
    # net_mm = max(0, 26.25/5 - 16) = max(0, 5.25-16) = 0 → 0L
    result = compute_crop_result(
        nb_plants=10, density=2.0, kc=1.05, eto_mm=5.0,
        precipitation_mm=20.0, crop_type="tomate", stage="mid",
    )
    assert result.liters == pytest.approx(0.0)
    assert result.effective_rainfall_mm == pytest.approx(16.0)
    # daily_balance_liters reste signé : ETc 26.25L − pluie eff 16mm×5m²=80L → −53.75L
    assert result.daily_balance_liters == pytest.approx(-53.8, abs=0.2)
    # le besoin affiché reste planché à 0
    assert result.daily_need_liters == pytest.approx(0.0)

def test_crop_result_watering_applied_tracked_but_does_not_reduce_daily_need():
    """ADR-019 : daily_need_liters = net_liters indépendamment du volume arrosé.

    L'arrosage appliqué est tracé dans CropResult pour l'affichage mais
    ne modifie plus le besoin journalier — la déduction est portée par le
    bilan cumulé via apply_watering_volumes (RuntimeConfigState).
    """
    base = compute_crop_result(
        nb_plants=10, density=2.0, kc=0.7, eto_mm=4.0,
        precipitation_mm=0.0, crop_type="tomate", stage="mid",
        watering_applied_today_liters=0.0,
    )
    half = base.liters / 2
    result_half = compute_crop_result(
        nb_plants=10, density=2.0, kc=0.7, eto_mm=4.0,
        precipitation_mm=0.0, crop_type="tomate", stage="mid",
        watering_applied_today_liters=half,
    )
    # daily_need_liters doit rester égal au besoin net — pas réduit par l'arrosage
    assert result_half.daily_need_liters == pytest.approx(base.liters, abs=0.2)
    # le volume arrosé est bien conservé dans CropResult pour l'affichage
    assert result_half.watering_applied_today_liters == pytest.approx(half, abs=0.2)

def test_crop_result_daily_need_equals_net_liters_regardless_of_watering():
    """ADR-019 : même un arrosage massif ne réduit pas daily_need_liters."""
    result = compute_crop_result(
        nb_plants=10, density=2.0, kc=0.7, eto_mm=4.0,
        precipitation_mm=0.0, crop_type="tomate", stage="mid",
        watering_applied_today_liters=1000.0,
    )
    # daily_need_liters == net_liters, pas 0
    assert result.daily_need_liters == pytest.approx(result.liters, abs=0.2)
    assert result.daily_need_liters > 0

def test_crop_result_mulch_attenuates_etc_and_need():
    """ADR-029 : avec paillage, l'ETc (et donc le besoin) est atténué selon le stade."""
    base = compute_crop_result(
        nb_plants=10, density=2.0, kc=1.0, eto_mm=5.0,
        precipitation_mm=0.0, crop_type="tomate", stage="ini",
    )
    mulched = compute_crop_result(
        nb_plants=10, density=2.0, kc=1.0, eto_mm=5.0,
        precipitation_mm=0.0, crop_type="tomate", stage="ini",
        mulch_active=True,
    )
    # Stade ini → facteur 0,55 : ETc et besoin réduits d'autant.
    assert mulched.etc_liters == pytest.approx(base.etc_liters * 0.55, abs=0.1)
    assert mulched.liters == pytest.approx(base.liters * 0.55, abs=0.1)
    assert mulched.mulch_active is True
    assert base.mulch_active is False

def test_crop_result_mulch_applied_before_rainfall_deduction():
    """ADR-029 : l'atténuation porte sur l'ETc, la pluie efficace reste pleine.

    ETc brut = 1,0×5×5 = 25L sur 5m² = 5mm ; paillage mid (0,9) → 22,5L = 4,5mm.
    Pluie 5mm → eff 4mm. Bilan = (4,5 − 4)×5 = 2,5L (et non (5−4)×5 = 5L sans paillage).
    """
    mulched = compute_crop_result(
        nb_plants=10, density=2.0, kc=1.0, eto_mm=5.0,
        precipitation_mm=5.0, crop_type="tomate", stage="mid",
        mulch_active=True,
    )
    assert mulched.effective_rainfall_mm == pytest.approx(4.0)
    assert mulched.daily_balance_liters == pytest.approx(2.5, abs=0.1)

def test_crop_result_weekly_projection():
    result = compute_crop_result(
        nb_plants=10, density=2.0, kc=0.7, eto_mm=4.0,
        precipitation_mm=0.0, crop_type="tomate", stage="mid",
    )
    assert result.weekly_projection_l == pytest.approx(result.liters * 7, abs=0.2)

def test_crop_result_liters_per_plant():
    result = compute_crop_result(
        nb_plants=10, density=2.0, kc=0.7, eto_mm=4.0,
        precipitation_mm=0.0, crop_type="tomate", stage="mid",
    )
    assert result.liters_per_plant == pytest.approx(result.liters / 10, abs=0.01)


# ---------------------------------------------------------------------------
# compute_irrigation_data
# ---------------------------------------------------------------------------

_KC_DATA = {
    "crops": {
        "tomate": {"mid": 1.15, "ini": 0.6, "end": 0.8},
        "laitue": {"mid": 1.0,  "ini": 0.7, "end": 0.95},
    }
}

_CROPS = [
    {"crop_id": "c1", "crop_type": "tomate", "stage": "mid", "nb_plants": 10, "density": 2.0},
    {"crop_id": "c2", "crop_type": "laitue", "stage": "mid", "nb_plants": 20, "density": 8.0},
]

def _kc_getter(kc_data, crop_type, stage):
    return kc_data.get("crops", {}).get(crop_type, {}).get(stage)

def test_irrigation_data_basic():
    data = compute_irrigation_data(
        crops=_CROPS, kc_data=_KC_DATA, eto_mm=4.0, kc_getter=_kc_getter,
    )
    assert "c1" in data.crops
    assert "c2" in data.crops
    assert data.eto_mm == 4.0
    assert data.total_liters >= 0

def test_irrigation_data_totals_match_sum():
    data = compute_irrigation_data(
        crops=_CROPS, kc_data=_KC_DATA, eto_mm=4.0, kc_getter=_kc_getter,
    )
    expected_total = sum(r.liters for r in data.crops.values())
    assert data.total_liters == pytest.approx(expected_total, abs=0.1)

def test_irrigation_data_unknown_crop_skipped():
    crops = [
        {"crop_id": "x1", "crop_type": "unknown_plant", "stage": "mid",
         "nb_plants": 5, "density": 1.0},
    ]
    data = compute_irrigation_data(
        crops=crops, kc_data=_KC_DATA, eto_mm=4.0, kc_getter=_kc_getter,
    )
    assert "x1" not in data.crops
    assert data.total_liters == pytest.approx(0.0)

def test_irrigation_data_empty_crops():
    data = compute_irrigation_data(
        crops=[], kc_data=_KC_DATA, eto_mm=4.0, kc_getter=_kc_getter,
    )
    assert data.crops == {}
    assert data.total_liters == pytest.approx(0.0)

def test_irrigation_data_total_balance_negative_on_rain():
    """ADR-028 : total_daily_balance_liters peut être négatif (surplus de pluie) alors que
    total_daily_need_liters (affiché) reste ≥ 0."""
    # Forte pluie : besoin net affiché = 0, mais bilan signé négatif.
    data = compute_irrigation_data(
        crops=_CROPS, kc_data=_KC_DATA, eto_mm=0.0, precipitation_mm=20.0,
        kc_getter=_kc_getter,
    )
    assert data.total_daily_need_liters == pytest.approx(0.0)
    assert data.total_daily_balance_liters < 0.0


def test_irrigation_data_mulch_per_crop_attenuates():
    """ADR-029 : le drapeau mulch_active par culture atténue son besoin, sans toucher les autres."""
    crops = [
        {"crop_id": "c1", "crop_type": "tomate", "stage": "ini",
         "nb_plants": 10, "density": 2.0, "mulch_active": True},
        {"crop_id": "c2", "crop_type": "tomate", "stage": "ini",
         "nb_plants": 10, "density": 2.0, "mulch_active": False},
    ]
    data = compute_irrigation_data(
        crops=crops, kc_data=_KC_DATA, eto_mm=5.0, kc_getter=_kc_getter,
    )
    assert data.crops["c1"].mulch_active is True
    assert data.crops["c2"].mulch_active is False
    # La culture paillée (stade ini, facteur 0,55) consomme moins que la non paillée.
    assert data.crops["c1"].liters == pytest.approx(data.crops["c2"].liters * 0.55, abs=0.1)

def test_irrigation_data_mulch_absent_defaults_off():
    """Rétrocompatibilité : une culture sans clé mulch_active n'est pas atténuée."""
    crops = [
        {"crop_id": "c1", "crop_type": "tomate", "stage": "ini",
         "nb_plants": 10, "density": 2.0},
    ]
    data = compute_irrigation_data(
        crops=crops, kc_data=_KC_DATA, eto_mm=5.0, kc_getter=_kc_getter,
    )
    assert data.crops["c1"].mulch_active is False

def test_irrigation_data_cumulative_need_passthrough():
    cumulative = {"c1": 12.5, "c2": 7.0}
    data = compute_irrigation_data(
        crops=_CROPS, kc_data=_KC_DATA, eto_mm=4.0,
        kc_getter=_kc_getter, cumulative_need=cumulative,
    )
    assert data.cumulative_need == cumulative

def test_irrigation_data_watering_tracked_but_does_not_reduce_daily_need():
    """ADR-019 : total_daily_need_liters = net_liters — non affecté par watering_applied_today.

    La déduction est portée par le bilan cumulé (apply_watering_volumes),
    pas par le calcul agronomique pur.
    """
    data_no_water = compute_irrigation_data(
        crops=_CROPS[:1], kc_data=_KC_DATA, eto_mm=4.0, kc_getter=_kc_getter,
    )
    data_watered = compute_irrigation_data(
        crops=_CROPS[:1], kc_data=_KC_DATA, eto_mm=4.0, kc_getter=_kc_getter,
        watering_applied_today={"c1": 1000.0},
    )
    # Le besoin journalier ne dépend pas du volume déjà arrosé
    assert data_no_water.total_daily_need_liters > 0
    assert data_watered.total_daily_need_liters == pytest.approx(
        data_no_water.total_daily_need_liters, abs=0.2
    )
    # Le volume arrosé est bien tracé dans CropResult
    assert data_watered.crops["c1"].watering_applied_today_liters == pytest.approx(1000.0)
