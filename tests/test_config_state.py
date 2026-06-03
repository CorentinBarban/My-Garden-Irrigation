"""Tests de RuntimeConfigState (config_state.py).

Zéro import homeassistant.* — toutes les instanciations se font directement
depuis le dict d'options, sans ConfigEntry HA.
"""
import pytest
from datetime import datetime, timezone

from custom_components.my_garden_irrigation.config_state import RuntimeConfigState
from custom_components.my_garden_irrigation.const import (
    CONF_CROP_ID,
    CONF_CROP_TYPE,
    CONF_CROPS,
    CONF_CYCLES_COUNT,
    CONF_DENSITY,
    CONF_GLOBAL_FLOW_RATE,
    CONF_GLOBAL_VALVE_ENTITY_ID,
    CONF_IRRIGATION_TIME,
    CONF_NB_PLANTS,
    CONF_SOAK_DURATION,
    CONF_STAGE,
    CONF_WATERING_FREQUENCY,
    CONF_WATERING_INTERVAL_DAYS,
    CONF_WATERING_MODE,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _options(**overrides):
    """Retourne un dict options minimal valide, avec surcharges optionnelles."""
    base = {
        CONF_CROPS: [],
        CONF_GLOBAL_FLOW_RATE: 300.0,
        CONF_WATERING_FREQUENCY: "daily",
        CONF_WATERING_MODE: "continuous",
        CONF_WATERING_INTERVAL_DAYS: 2,
        CONF_IRRIGATION_TIME: "06:00:00",
        CONF_CYCLES_COUNT: 3,
        CONF_SOAK_DURATION: 15,
    }
    base.update(overrides)
    return base

def _crop(crop_id="c1", nb_plants=10, density=2.0, crop_type="tomate", stage="mid"):
    return {
        CONF_CROP_ID: crop_id,
        CONF_CROP_TYPE: crop_type,
        CONF_STAGE: stage,
        CONF_NB_PLANTS: nb_plants,
        CONF_DENSITY: density,
    }

def _make_state(**overrides):
    return RuntimeConfigState(_options(**overrides))


# ---------------------------------------------------------------------------
# Construction depuis options
# ---------------------------------------------------------------------------

def test_init_reads_flow_rate():
    state = _make_state(**{CONF_GLOBAL_FLOW_RATE: 500.0})
    assert state.flow_rate == pytest.approx(500.0)

def test_init_reads_irrigation_time():
    state = _make_state(**{CONF_IRRIGATION_TIME: "08:30:00"})
    assert state.irrigation_time == "08:30:00"

def test_init_defaults_empty_state():
    state = _make_state()
    assert state.cumulative_need == {}
    assert state.watering_applied_today == {}
    assert state.auto_irrigation_enabled is False
    assert state.last_auto_watering_date is None
    assert state.get_valve_open_time() is None

def test_init_reads_crops():
    crops = [_crop("c1"), _crop("c2")]
    state = RuntimeConfigState(_options(**{CONF_CROPS: crops}))
    assert len(state.crops) == 2


# ---------------------------------------------------------------------------
# Setters config
# ---------------------------------------------------------------------------

def test_set_flow_rate():
    state = _make_state()
    state.set_flow_rate(999.9)
    assert state.flow_rate == pytest.approx(999.9)

def test_set_irrigation_time():
    state = _make_state()
    state.set_irrigation_time("20:00:00")
    assert state.irrigation_time == "20:00:00"

def test_set_watering_mode():
    state = _make_state()
    state.set_watering_mode("fractioned")
    assert state.watering_mode == "fractioned"

def test_set_cycles_count():
    state = _make_state()
    state.set_cycles_count(5)
    assert state.cycles_count == 5

def test_set_soak_duration():
    state = _make_state()
    state.set_soak_duration_minutes(30)
    assert state.soak_duration_minutes == 30

def test_set_watering_frequency():
    state = _make_state()
    state.set_watering_frequency("interval")
    assert state.watering_frequency == "interval"

def test_set_watering_interval_days():
    state = _make_state()
    state.set_watering_interval_days(7)
    assert state.watering_interval_days == 7

def test_set_valve_open_time():
    state = _make_state()
    dt = datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc)
    state.set_valve_open_time(dt)
    assert state.get_valve_open_time() == dt

def test_set_valve_open_time_none():
    state = _make_state()
    state.set_valve_open_time(datetime(2026, 5, 31, 12, 0))
    state.set_valve_open_time(None)
    assert state.get_valve_open_time() is None


# ---------------------------------------------------------------------------
# update_crop_field
# ---------------------------------------------------------------------------

def test_update_crop_field():
    crops = [_crop("c1", nb_plants=5)]
    state = RuntimeConfigState(_options(**{CONF_CROPS: crops}))
    state.update_crop_field("c1", CONF_NB_PLANTS, 20)
    assert state.crops[0][CONF_NB_PLANTS] == 20

def test_update_crop_field_unknown_id_noop():
    crops = [_crop("c1")]
    state = RuntimeConfigState(_options(**{CONF_CROPS: crops}))
    original_nb = state.crops[0][CONF_NB_PLANTS]
    state.update_crop_field("nonexistent", CONF_NB_PLANTS, 99)
    assert state.crops[0][CONF_NB_PLANTS] == original_nb


# ---------------------------------------------------------------------------
# auto_irrigation
# ---------------------------------------------------------------------------

def test_set_auto_irrigation_enables():
    state = _make_state()
    state.set_auto_irrigation(True, "2026-05-31")
    assert state.auto_irrigation_enabled is True

def test_set_auto_irrigation_sets_date_when_none():
    state = _make_state()
    state.set_auto_irrigation(True, "2026-05-31")
    assert state.last_auto_watering_date == "2026-05-31"

def test_set_auto_irrigation_does_not_override_existing_date():
    state = _make_state()
    state.update_last_watering_date("2026-05-01")
    state.set_auto_irrigation(True, "2026-05-31")
    # Date existante conservée
    assert state.last_auto_watering_date == "2026-05-01"

def test_set_auto_irrigation_disables():
    state = _make_state()
    state.set_auto_irrigation(True, "2026-05-31")
    state.set_auto_irrigation(False, "2026-05-31")
    assert state.auto_irrigation_enabled is False

def test_update_last_watering_date():
    state = _make_state()
    state.update_last_watering_date("2026-06-01")
    assert state.last_auto_watering_date == "2026-06-01"


# ---------------------------------------------------------------------------
# apply_watering_volumes
# ---------------------------------------------------------------------------

def test_apply_watering_volumes_accumulates():
    state = _make_state()
    state.apply_watering_volumes({"c1": 5.0})
    state.apply_watering_volumes({"c1": 3.0})
    assert state.watering_applied_today["c1"] == pytest.approx(8.0)

def test_apply_watering_volumes_partial_reduces_deficit():
    """Arrosage partiel : le déficit résiduel (déficit − volume) est conservé."""
    crops = [_crop("c1")]
    state = RuntimeConfigState(_options(**{CONF_CROPS: crops}))
    state._cumulative_need = {"c1": 10.0}
    state.apply_watering_volumes({"c1": 3.0})
    assert state.cumulative_need["c1"] == pytest.approx(7.0)
    assert state.watering_applied_today["c1"] == pytest.approx(3.0)

def test_apply_watering_volumes_exceeds_deficit_clamps_to_zero():
    """Volume distribué ≥ déficit : le cumulé est ramené à 0, pas en négatif."""
    crops = [_crop("c1")]
    state = RuntimeConfigState(_options(**{CONF_CROPS: crops}))
    state._cumulative_need = {"c1": 2.0}
    state.apply_watering_volumes({"c1": 50.0})
    assert state.cumulative_need["c1"] == pytest.approx(0.0)

def test_apply_watering_volumes_unwatered_crop_unchanged():
    """La culture non arrosée (absente du dict volumes) conserve son déficit intégralement."""
    crops = [_crop("c1"), _crop("c2")]
    state = RuntimeConfigState(_options(**{CONF_CROPS: crops}))
    state._cumulative_need = {"c1": 10.0, "c2": 8.0}
    # Seule c1 reçoit de l'eau
    state.apply_watering_volumes({"c1": 5.0})
    assert state.cumulative_need["c1"] == pytest.approx(5.0)
    assert state.cumulative_need["c2"] == pytest.approx(8.0)

def test_apply_watering_volumes_empty():
    state = _make_state()
    state.apply_watering_volumes({})
    assert state.watering_applied_today == {}


# ---------------------------------------------------------------------------
# apply_midnight_transfer
# ---------------------------------------------------------------------------

def test_apply_midnight_transfer_accumulates():
    state = _make_state()
    state._cumulative_need = {"c1": 5.0}
    state.apply_midnight_transfer({"c1": 3.0})
    assert state.cumulative_need["c1"] == pytest.approx(8.0)

def test_apply_midnight_transfer_resets_daily():
    state = _make_state()
    state._watering_applied_today = {"c1": 7.0}
    state.apply_midnight_transfer({"c1": 3.0})
    assert state.watering_applied_today == {}

def test_apply_midnight_transfer_new_crop():
    state = _make_state()
    state.apply_midnight_transfer({"c_new": 4.0})
    assert state.cumulative_need["c_new"] == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# reset_irrigation
# ---------------------------------------------------------------------------

def test_reset_irrigation_clears_cumulative():
    state = _make_state()
    state._cumulative_need = {"c1": 20.0}
    state._watering_applied_today = {"c1": 5.0}
    state.reset_irrigation()
    assert state.cumulative_need == {}
    assert state.watering_applied_today == {}


# ---------------------------------------------------------------------------
# init_cumulative_need
# ---------------------------------------------------------------------------

def test_init_cumulative_need():
    state = _make_state()
    state.init_cumulative_need({"c1": 12.0, "c2": 8.0})
    assert state.cumulative_need == {"c1": pytest.approx(12.0), "c2": pytest.approx(8.0)}


# ---------------------------------------------------------------------------
# init_missing_crops
# ---------------------------------------------------------------------------

def test_init_missing_crops_empty_state():
    """Premier démarrage : toutes les cultures sont absentes → toutes initialisées."""
    state = _make_state()
    added = state.init_missing_crops({"c1": 12.0, "c2": 8.0})
    assert added is True
    assert state.cumulative_need == {"c1": pytest.approx(12.0), "c2": pytest.approx(8.0)}


def test_init_missing_crops_new_crop_added():
    """Nouvelle culture ajoutée à un système existant → seule la nouvelle est initialisée."""
    state = _make_state()
    state._cumulative_need = {"c1": 5.0}
    added = state.init_missing_crops({"c1": 12.0, "c2": 8.0})
    assert added is True
    assert state.cumulative_need["c1"] == pytest.approx(5.0)  # existante inchangée
    assert state.cumulative_need["c2"] == pytest.approx(8.0)  # nouvelle initialisée


def test_init_missing_crops_all_present():
    """Toutes les cultures déjà présentes → aucune modification, retourne False."""
    state = _make_state()
    state._cumulative_need = {"c1": 5.0, "c2": 3.0}
    added = state.init_missing_crops({"c1": 12.0, "c2": 8.0})
    assert added is False
    assert state.cumulative_need == {"c1": pytest.approx(5.0), "c2": pytest.approx(3.0)}


# ---------------------------------------------------------------------------
# get_crop_surfaces
# ---------------------------------------------------------------------------

def test_get_crop_surfaces():
    crops = [_crop("c1", nb_plants=10, density=2.0)]
    state = RuntimeConfigState(_options(**{CONF_CROPS: crops}))
    surfaces = state.get_crop_surfaces()
    assert surfaces["c1"] == pytest.approx(5.0)

def test_get_crop_surfaces_multiple():
    crops = [_crop("c1", nb_plants=10, density=2.0), _crop("c2", nb_plants=60, density=60.0)]
    state = RuntimeConfigState(_options(**{CONF_CROPS: crops}))
    surfaces = state.get_crop_surfaces()
    assert surfaces["c1"] == pytest.approx(5.0)
    assert surfaces["c2"] == pytest.approx(1.0)

def test_get_crop_surfaces_empty():
    state = _make_state()
    assert state.get_crop_surfaces() == {}


# ---------------------------------------------------------------------------
# Sérialisation round-trip (to_storage / restore_from_storage)
# ---------------------------------------------------------------------------

def test_storage_round_trip_config_overrides():
    state = _make_state()
    state.set_flow_rate(750.0)
    state.set_irrigation_time("19:00:00")
    state._cumulative_need = {"c1": 15.0}

    payload = state.to_storage("2026-05-31")
    assert payload["runtime_config"][CONF_GLOBAL_FLOW_RATE] == pytest.approx(750.0)

    # Restauration dans un état fraîchement initialisé
    restored = _make_state()
    restored.restore_from_storage(payload, "2026-05-31")
    assert restored.flow_rate == pytest.approx(750.0)
    assert restored.irrigation_time == "19:00:00"
    assert restored.cumulative_need == {"c1": pytest.approx(15.0)}

def test_storage_date_boundary_resets_daily():
    state = _make_state()
    state._watering_applied_today = {"c1": 5.0}
    payload = state.to_storage("2026-05-30")  # sauvegardé hier

    restored = _make_state()
    restored.restore_from_storage(payload, "2026-05-31")  # aujourd'hui = demain
    # watering_applied_today doit être remis à zéro (nouveau jour)
    assert restored.watering_applied_today == {}

def test_storage_same_day_restores_daily():
    state = _make_state()
    state._watering_applied_today = {"c1": 5.0}
    payload = state.to_storage("2026-05-31")

    restored = _make_state()
    restored.restore_from_storage(payload, "2026-05-31")
    assert restored.watering_applied_today == {"c1": pytest.approx(5.0)}

def test_storage_options_hash_mismatch_discards_overrides():
    """Si options ont changé depuis le save, les overrides runtime sont ignorés."""
    state = _make_state()
    state.set_flow_rate(750.0)
    payload = state.to_storage("2026-05-31")

    # Nouvel état avec des options DIFFÉRENTES (flow_rate différent → hash différent)
    new_options = _options(**{CONF_GLOBAL_FLOW_RATE: 200.0})
    restored = RuntimeConfigState(new_options)
    restored.restore_from_storage(payload, "2026-05-31")
    # Le hash ne correspond plus → override ignoré → valeur de l'option
    assert restored.flow_rate == pytest.approx(200.0)

def test_storage_restore_empty_noop():
    state = _make_state()
    state.restore_from_storage({}, "2026-05-31")
    assert state.flow_rate == pytest.approx(300.0)  # valeur par défaut des options


# ---------------------------------------------------------------------------
# begin_irrigation_session / consume_session_close (Mode Cycle & Soak)
# ---------------------------------------------------------------------------

def test_begin_irrigation_session_three_cycles():
    """3 cycles : les 2 premières fermetures ne sont pas finales, la 3e l'est."""
    state = _make_state()
    state.begin_irrigation_session(3)
    assert state.consume_session_close() is False
    assert state.consume_session_close() is False
    assert state.consume_session_close() is True

def test_begin_irrigation_session_single_cycle():
    """1 cycle (mode continu) : la première fermeture est finale."""
    state = _make_state()
    state.begin_irrigation_session(1)
    assert state.consume_session_close() is True

def test_begin_irrigation_session_clamps_zero_to_one():
    """cycles=0 est normalisé à 1 — la fermeture est immédiatement finale."""
    state = _make_state()
    state.begin_irrigation_session(0)
    assert state.consume_session_close() is True

def test_consume_session_close_without_active_session_returns_true():
    """Sans session active (compteur à 0), toute fermeture est traitée comme finale."""
    state = _make_state()
    assert state.consume_session_close() is True


# ---------------------------------------------------------------------------
# apply_midnight_transfer — déduction arrosage (Règle 1 spec)
# ---------------------------------------------------------------------------

def test_apply_midnight_transfer_deducts_watering_to_zero():
    """Scénario I spec : arrosage matinal couvre cumul + journalier → dette = 0 au matin J+1."""
    state = _make_state(**{CONF_CROPS: [_crop("c1")]})
    # cumul déjà soldé par apply_watering_volumes (simulate post-morning-irrigation state)
    state._cumulative_need = {"c1": 0.0}
    state._watering_applied_today = {"c1": 8.0}

    state.apply_midnight_transfer({"c1": 4.0})

    assert state.cumulative_need["c1"] == pytest.approx(0.0)
    assert state.watering_applied_today == {}   # remis à zéro

def test_apply_midnight_transfer_residual_debt():
    """Arrosage partiel : dette résiduelle = cumul + journalier - arrosé."""
    state = _make_state(**{CONF_CROPS: [_crop("c1")]})
    state._cumulative_need = {"c1": 5.0}
    state._watering_applied_today = {"c1": 3.0}

    state.apply_midnight_transfer({"c1": 2.0})

    # max(0, 5 + 2 - 3) = 4
    assert state.cumulative_need["c1"] == pytest.approx(4.0)
    assert state.watering_applied_today == {}

def test_apply_midnight_transfer_no_watering_accumulates_normally():
    """Sans arrosage dans la journée, accumulation simple (comportement antérieur)."""
    state = _make_state(**{CONF_CROPS: [_crop("c1")]})
    state._cumulative_need = {"c1": 6.0}
    state._watering_applied_today = {}

    state.apply_midnight_transfer({"c1": 2.0})

    assert state.cumulative_need["c1"] == pytest.approx(8.0)
