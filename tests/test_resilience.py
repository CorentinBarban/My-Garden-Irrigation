"""Tests de résilience — bugs critiques #1–#8.

Approche : duck-typing sur les méthodes non-bornées pour éviter d'instancier
HomeAssistant. Chaque test cible un bug précis identifié lors de l'analyse.

Bugs couverts :
    #1  scheduler  : _handle_midnight reschedule même si _on_midnight() lève
    #2  coordinator: update_crop_field déclenche _schedule_config_save()
    #3  coordinator: fire_irrigation_event ne lève pas ZeroDivisionError si cycles_count=0
    #4  coordinator: _on_midnight utilise _last_daily_needs quand self.data is None
    #5  coordinator: _persist_config log WARNING si la sauvegarde échoue (pas silence)
    #6  coordinator: _async_update_data met à jour _last_daily_needs après chaque succès
    #7  valve_tracker: _restore_valve_state absorbe les exceptions (try/except)
    #8  valve_tracker: warning loggué si valve_entity_id est absent
"""
import asyncio
import logging
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.my_garden_irrigation.config_state import RuntimeConfigState
from custom_components.my_garden_irrigation.const import (
    CONF_CROPS,
    CONF_CROP_ID,
    CONF_CROP_TYPE,
    CONF_CYCLES_COUNT,
    CONF_DENSITY,
    CONF_GLOBAL_FLOW_RATE,
    CONF_IRRIGATION_TIME,
    CONF_NB_PLANTS,
    CONF_SOAK_DURATION,
    CONF_STAGE,
    CONF_WATERING_FREQUENCY,
    CONF_WATERING_INTERVAL_DAYS,
    CONF_WATERING_MODE,
    WATERING_MODE_FRACTIONED,
)


# ---------------------------------------------------------------------------
# Helpers partagés
# ---------------------------------------------------------------------------

def _options(**overrides):
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


def _make_state(**overrides) -> RuntimeConfigState:
    return RuntimeConfigState(_options(**overrides))


def _run(coro):
    """Exécute une coroutine dans une nouvelle boucle (Python 3.10+ safe)."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fix #1 — Scheduler : _handle_midnight reschedule malgré exception
# ---------------------------------------------------------------------------

def test_midnight_reschedules_after_on_midnight_exception():
    """`_schedule_midnight()` appelé même si `_on_midnight()` lève."""
    from custom_components.my_garden_irrigation.scheduler import IrrigationScheduler

    hass = MagicMock()
    config = _make_state()
    on_midnight = AsyncMock(side_effect=RuntimeError("Store failed"))
    on_trigger = AsyncMock()

    with patch(
        "custom_components.my_garden_irrigation.scheduler.async_track_point_in_time"
    ) as mock_track:
        mock_track.return_value = MagicMock()
        scheduler = IrrigationScheduler(hass, config, on_midnight, on_trigger)

        calls = []
        scheduler._schedule_midnight = lambda: calls.append(1)

        _run(scheduler._handle_midnight(None))

    assert calls == [1], "_schedule_midnight doit être appelé même après exception"


def test_midnight_reschedules_on_success():
    """`_schedule_midnight()` appelé dans le cas nominal (contrôle)."""
    from custom_components.my_garden_irrigation.scheduler import IrrigationScheduler

    hass = MagicMock()
    config = _make_state()
    on_midnight = AsyncMock()
    on_trigger = AsyncMock()

    with patch(
        "custom_components.my_garden_irrigation.scheduler.async_track_point_in_time"
    ) as mock_track:
        mock_track.return_value = MagicMock()
        scheduler = IrrigationScheduler(hass, config, on_midnight, on_trigger)

        calls = []
        scheduler._schedule_midnight = lambda: calls.append(1)

        _run(scheduler._handle_midnight(None))

    assert calls == [1]


# ---------------------------------------------------------------------------
# Fix #2 — coordinator : update_crop_field déclenche _schedule_config_save
# ---------------------------------------------------------------------------

def test_update_crop_field_triggers_save():
    """`update_crop_field` doit appeler `_schedule_config_save()`."""
    from custom_components.my_garden_irrigation.coordinator import IrrigationCoordinator

    crop = {
        CONF_CROP_ID: "c1",
        CONF_CROP_TYPE: "tomate",
        CONF_STAGE: "mid",
        CONF_NB_PLANTS: 10,
        CONF_DENSITY: 2.0,
    }

    class FakeCoord:
        config = _make_state(**{CONF_CROPS: [crop]})
        _save_calls: list = []

        def _schedule_config_save(self) -> None:
            self._save_calls.append(1)

    coord = FakeCoord()
    IrrigationCoordinator.update_crop_field(coord, "c1", CONF_NB_PLANTS, 25)

    assert coord._save_calls == [1], "update_crop_field doit appeler _schedule_config_save()"
    assert coord.config.crops[0][CONF_NB_PLANTS] == 25


# ---------------------------------------------------------------------------
# Fix #3 — coordinator : fire_irrigation_event — pas de ZeroDivisionError
# ---------------------------------------------------------------------------

def test_fire_irrigation_event_cycles_count_zero_no_crash():
    """`cycles_count=0` ne doit pas lever `ZeroDivisionError`."""
    from custom_components.my_garden_irrigation.coordinator import IrrigationCoordinator

    class FakeCoord:
        data = MagicMock()
        hass = MagicMock()
        _entry = MagicMock()
        _entry.entry_id = "test"

        def __init__(self) -> None:
            self.config = _make_state(**{
                CONF_WATERING_MODE: WATERING_MODE_FRACTIONED,
                CONF_CYCLES_COUNT: 0,
                CONF_GLOBAL_FLOW_RATE: 60.0,
            })
            self.config._cumulative_need = {"c1": 10.0}
            type(self).data.cumulative_need = {"c1": 10.0}
            self.data = MagicMock()
            self.data.cumulative_need = {"c1": 10.0}

    coord = FakeCoord()
    IrrigationCoordinator.fire_irrigation_event(coord)

    assert coord.hass.bus.async_fire.called


def test_fire_irrigation_event_cycles_payload_uses_max():
    """Le payload contient `cycles_count >= 1` même si la config est à 0."""
    from custom_components.my_garden_irrigation.coordinator import IrrigationCoordinator

    class FakeCoord:
        hass = MagicMock()
        _entry = MagicMock()
        _entry.entry_id = "test"

        def __init__(self) -> None:
            self.config = _make_state(**{
                CONF_WATERING_MODE: WATERING_MODE_FRACTIONED,
                CONF_CYCLES_COUNT: 0,
                CONF_GLOBAL_FLOW_RATE: 60.0,
            })
            self.config._cumulative_need = {"c1": 6.0}
            self.data = MagicMock()
            self.data.cumulative_need = {"c1": 6.0}

    coord = FakeCoord()
    IrrigationCoordinator.fire_irrigation_event(coord)

    payload = coord.hass.bus.async_fire.call_args[0][1]
    assert payload["cycles_count"] >= 1
    assert payload["duration_per_cycle_minutes"] > 0


# ---------------------------------------------------------------------------
# Fix #4 — coordinator : _on_midnight utilise _last_daily_needs si data=None
# ---------------------------------------------------------------------------

def test_on_midnight_uses_last_daily_needs_when_data_none():
    """Si `self.data is None`, le transfert doit utiliser `_last_daily_needs`."""
    from custom_components.my_garden_irrigation.coordinator import IrrigationCoordinator

    class FakeCoord:
        data = None
        _last_daily_needs = {"c1": 5.0, "c2": 3.0}

        def __init__(self) -> None:
            self.config = _make_state()
            self._persistence = MagicMock()
            self._persistence.async_save = AsyncMock()
            self.async_refresh = AsyncMock()

    coord = FakeCoord()

    with patch("custom_components.my_garden_irrigation.coordinator.dt_util") as mock_dt:
        mock_dt.now.return_value.date.return_value.isoformat.return_value = "2026-05-31"
        _run(IrrigationCoordinator._on_midnight(coord))

    assert coord.config.cumulative_need.get("c1") == pytest.approx(5.0)
    assert coord.config.cumulative_need.get("c2") == pytest.approx(3.0)


def test_on_midnight_empty_when_no_data_and_no_last():
    """Sans data ni _last_daily_needs, le transfert est vide sans crash."""
    from custom_components.my_garden_irrigation.coordinator import IrrigationCoordinator

    class FakeCoord:
        data = None
        _last_daily_needs: dict = {}

        def __init__(self) -> None:
            self.config = _make_state()
            self._persistence = MagicMock()
            self._persistence.async_save = AsyncMock()
            self.async_refresh = AsyncMock()

    coord = FakeCoord()

    with patch("custom_components.my_garden_irrigation.coordinator.dt_util") as mock_dt:
        mock_dt.now.return_value.date.return_value.isoformat.return_value = "2026-05-31"
        _run(IrrigationCoordinator._on_midnight(coord))

    assert coord.config.cumulative_need == {}


# ---------------------------------------------------------------------------
# Fix #5 — coordinator : _persist_config log warning si save échoue
# ---------------------------------------------------------------------------

def test_persist_config_logs_warning_on_exception(caplog):
    """`_persist_config` doit logguer un WARNING si la sauvegarde échoue."""
    from custom_components.my_garden_irrigation.coordinator import IrrigationCoordinator

    class FakeCoord:
        def __init__(self) -> None:
            self.config = _make_state()
            self._persistence = MagicMock()
            self._persistence.async_save = AsyncMock(side_effect=OSError("disk full"))

    coord = FakeCoord()

    with patch("custom_components.my_garden_irrigation.coordinator.dt_util") as mock_dt:
        mock_dt.now.return_value.date.return_value.isoformat.return_value = "2026-05-31"
        with caplog.at_level(logging.WARNING, logger="custom_components.my_garden_irrigation.coordinator"):
            _run(IrrigationCoordinator._persist_config(coord))

    assert "Échec de la sauvegarde" in caplog.text


# ---------------------------------------------------------------------------
# Fix #6 — coordinator : _last_daily_needs mis à jour après update réussi
# ---------------------------------------------------------------------------

def test_async_update_data_caches_daily_needs():
    """`_last_daily_needs` est mis à jour après chaque `_async_update_data` réussi."""
    from custom_components.my_garden_irrigation.coordinator import IrrigationCoordinator
    from custom_components.my_garden_irrigation.core.models import CropResult, IrrigationData

    crop_result = MagicMock(spec=CropResult)
    crop_result.daily_need_liters = 7.5

    fake_data = MagicMock(spec=IrrigationData)
    fake_data.crops = {"c1": crop_result}

    class FakeCoord:
        _last_daily_needs: dict = {}

        def __init__(self) -> None:
            self.config = _make_state()
            self._kc_data = {}

        async def _fetch_weather(self):
            return 4.0, 0.0

    coord = FakeCoord()

    with patch(
        "custom_components.my_garden_irrigation.coordinator.compute_irrigation_data",
        return_value=fake_data,
    ):
        _run(IrrigationCoordinator._async_update_data(coord))

    assert coord._last_daily_needs == {"c1": pytest.approx(7.5)}


# ---------------------------------------------------------------------------
# Fix #7 — valve_tracker : _restore_valve_state absorbe les exceptions
# ---------------------------------------------------------------------------

def test_restore_valve_state_catches_exception(caplog):
    """`_restore_valve_state` doit logguer un warning si une exception survient."""
    from custom_components.my_garden_irrigation.valve_tracker import ValveTracker

    hass = MagicMock()
    hass.states.get = MagicMock(side_effect=RuntimeError("HA not ready"))

    from custom_components.my_garden_irrigation.const import CONF_GLOBAL_VALVE_ENTITY_ID
    config = _make_state(**{CONF_GLOBAL_VALVE_ENTITY_ID: "switch.vanne"})

    tracker = ValveTracker(hass, config, AsyncMock())

    with caplog.at_level(
        logging.WARNING, logger="custom_components.my_garden_irrigation.valve_tracker"
    ):
        _run(tracker._restore_valve_state())

    assert "Erreur lors de la restauration" in caplog.text


def test_restore_valve_state_no_crash_on_unknown_valve():
    """`_restore_valve_state` ne plante pas si la vanne retourne None."""
    from custom_components.my_garden_irrigation.valve_tracker import ValveTracker

    hass = MagicMock()
    hass.states.get = MagicMock(return_value=None)

    from custom_components.my_garden_irrigation.const import CONF_GLOBAL_VALVE_ENTITY_ID
    config = _make_state(**{CONF_GLOBAL_VALVE_ENTITY_ID: "switch.vanne"})

    tracker = ValveTracker(hass, config, AsyncMock())
    _run(tracker._restore_valve_state())  # ne doit pas lever


# ---------------------------------------------------------------------------
# Fix #8 — valve_tracker : warning si valve_entity_id absent
# ---------------------------------------------------------------------------

def test_valve_tracker_warns_when_no_valve_id(caplog):
    """`setup()` doit logguer un WARNING si `valve_entity_id` est absent."""
    from custom_components.my_garden_irrigation.valve_tracker import ValveTracker

    hass = MagicMock()
    # async_create_task reçoit une coroutine — on la ferme pour éviter le RuntimeWarning
    hass.async_create_task.side_effect = lambda coro: coro.close()
    config = _make_state()  # valve_entity_id = None par défaut

    tracker = ValveTracker(hass, config, AsyncMock())

    with caplog.at_level(
        logging.WARNING, logger="custom_components.my_garden_irrigation.valve_tracker"
    ):
        cleanup = tracker.setup()

    assert "Aucune vanne globale configurée" in caplog.text
    cleanup()  # le callable de nettoyage ne doit pas crasher


# ---------------------------------------------------------------------------
# Cohérence #A — async_update_crop_field : rescalage cumulatif proportionnel
# ---------------------------------------------------------------------------

def _crop_options(crop_id="c1", nb_plants=10, density=2.0):
    """Options avec une culture pré-configurée."""
    crop = {
        CONF_CROP_ID: crop_id,
        CONF_CROP_TYPE: "tomate",
        CONF_STAGE: "mid",
        CONF_NB_PLANTS: nb_plants,
        CONF_DENSITY: density,
    }
    return _options(**{CONF_CROPS: [crop]})


def test_async_update_nb_plants_scales_cumulative():
    """Doubler nb_plants → surface double → cumulatif doublé proportionnellement."""
    from custom_components.my_garden_irrigation.coordinator import IrrigationCoordinator

    class FakeCoord:
        def __init__(self) -> None:
            self.config = RuntimeConfigState(_crop_options(nb_plants=10, density=2.0))
            # Surface initiale = 10/2 = 5 m² → cumulatif de départ = 20 L
            self.config._cumulative_need = {"c1": 20.0}
            self._persistence = MagicMock()
            self._persistence.async_save = AsyncMock()
            self.async_refresh = AsyncMock()

    coord = FakeCoord()
    with patch("custom_components.my_garden_irrigation.coordinator.dt_util") as mock_dt:
        mock_dt.now.return_value.date.return_value.isoformat.return_value = "2026-05-31"
        _run(IrrigationCoordinator.async_update_crop_field(coord, "c1", CONF_NB_PLANTS, 20))

    # Surface nouvelle = 20/2 = 10 m² → scale = 10/5 = 2 → cumulatif = 40 L
    assert coord.config.cumulative_need["c1"] == pytest.approx(40.0, abs=0.01)
    coord.async_refresh.assert_awaited_once()


def test_async_update_density_scales_cumulative():
    """Doubler la densité → surface divisée par 2 → cumulatif divisé par 2."""
    from custom_components.my_garden_irrigation.coordinator import IrrigationCoordinator

    class FakeCoord:
        def __init__(self) -> None:
            self.config = RuntimeConfigState(_crop_options(nb_plants=10, density=2.0))
            self.config._cumulative_need = {"c1": 20.0}
            self._persistence = MagicMock()
            self._persistence.async_save = AsyncMock()
            self.async_refresh = AsyncMock()

    coord = FakeCoord()
    with patch("custom_components.my_garden_irrigation.coordinator.dt_util") as mock_dt:
        mock_dt.now.return_value.date.return_value.isoformat.return_value = "2026-05-31"
        _run(IrrigationCoordinator.async_update_crop_field(coord, "c1", CONF_DENSITY, 4.0))

    # Surface nouvelle = 10/4 = 2.5 m², ancienne = 5 m² → scale = 0.5 → cumulatif = 10 L
    assert coord.config.cumulative_need["c1"] == pytest.approx(10.0, abs=0.01)


def test_async_update_stage_no_cumulative_scaling():
    """Changer le stage (Kc change, pas la surface) → cumulatif inchangé."""
    from custom_components.my_garden_irrigation.coordinator import IrrigationCoordinator

    class FakeCoord:
        def __init__(self) -> None:
            self.config = RuntimeConfigState(_crop_options())
            self.config._cumulative_need = {"c1": 20.0}
            self._persistence = MagicMock()
            self._persistence.async_save = AsyncMock()
            self.async_refresh = AsyncMock()

    coord = FakeCoord()
    with patch("custom_components.my_garden_irrigation.coordinator.dt_util") as mock_dt:
        mock_dt.now.return_value.date.return_value.isoformat.return_value = "2026-05-31"
        _run(IrrigationCoordinator.async_update_crop_field(coord, "c1", CONF_STAGE, "end"))

    # Le stage ne modifie pas la surface → cumulatif doit rester à 20 L
    assert coord.config.cumulative_need["c1"] == pytest.approx(20.0)
    coord.async_refresh.assert_awaited_once()


def test_async_update_no_cumulative_when_zero_old_surface():
    """Si l'ancienne surface est 0, pas de rescalage (évite division par zéro)."""
    from custom_components.my_garden_irrigation.coordinator import IrrigationCoordinator

    class FakeCoord:
        def __init__(self) -> None:
            # density=0 n'est pas permis via le formulaire, mais on teste la robustesse
            from custom_components.my_garden_irrigation.config_state import RuntimeConfigState as RCS
            opts = _crop_options(nb_plants=0, density=2.0)
            self.config = RCS(opts)
            self.config._cumulative_need = {"c1": 15.0}
            self._persistence = MagicMock()
            self._persistence.async_save = AsyncMock()
            self.async_refresh = AsyncMock()

    coord = FakeCoord()
    with patch("custom_components.my_garden_irrigation.coordinator.dt_util") as mock_dt:
        mock_dt.now.return_value.date.return_value.isoformat.return_value = "2026-05-31"
        _run(IrrigationCoordinator.async_update_crop_field(coord, "c1", CONF_NB_PLANTS, 10))

    # Pas de crash — le cumulatif peut avoir changé mais aucune exception
    coord.async_refresh.assert_awaited_once()


# ---------------------------------------------------------------------------
# Cohérence #B — config flow sync depuis coordinator live
# ---------------------------------------------------------------------------

def test_options_flow_init_syncs_from_coordinator():
    """async_step_init doit écraser les valeurs entry.options par celles du coordinator."""
    from unittest.mock import PropertyMock
    from custom_components.my_garden_irrigation.config_flow import IrrigationOptionsFlowHandler

    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.options = {
        CONF_CROPS: [],
        CONF_GLOBAL_FLOW_RATE: 100.0,  # valeur stale dans entry.options
        CONF_IRRIGATION_TIME: "06:00:00",
        CONF_WATERING_FREQUENCY: "daily",
        CONF_WATERING_MODE: "continuous",
        CONF_WATERING_INTERVAL_DAYS: 2,
        CONF_CYCLES_COUNT: 3,
        CONF_SOAK_DURATION: 15,
    }

    handler = IrrigationOptionsFlowHandler(entry)
    assert handler._flow_rate == pytest.approx(100.0)  # valeur stale

    # Coordinator live avec une valeur différente
    live_config = _make_state(**{CONF_GLOBAL_FLOW_RATE: 450.0})
    coordinator = MagicMock()
    coordinator.config = live_config

    handler.hass = MagicMock()
    handler.hass.data = {"my_garden_irrigation": {"test_entry": coordinator}}

    # Patcher config_entry (property HA, non settable directement en test)
    with patch.object(type(handler), "config_entry", new_callable=PropertyMock, return_value=entry):
        _run(handler.async_step_init())

    # La valeur live doit avoir écrasé la valeur stale
    assert handler._flow_rate == pytest.approx(450.0)


def test_options_flow_init_graceful_when_no_coordinator():
    """async_step_init ne plante pas si le coordinator n'est pas encore disponible."""
    from unittest.mock import PropertyMock
    from custom_components.my_garden_irrigation.config_flow import IrrigationOptionsFlowHandler

    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.options = {
        CONF_CROPS: [],
        CONF_GLOBAL_FLOW_RATE: 200.0,
        CONF_IRRIGATION_TIME: "06:00:00",
        CONF_WATERING_FREQUENCY: "daily",
        CONF_WATERING_MODE: "continuous",
        CONF_WATERING_INTERVAL_DAYS: 2,
        CONF_CYCLES_COUNT: 3,
        CONF_SOAK_DURATION: 15,
    }

    handler = IrrigationOptionsFlowHandler(entry)
    handler.hass = MagicMock()
    handler.hass.data = {}  # coordinator absent

    with patch.object(type(handler), "config_entry", new_callable=PropertyMock, return_value=entry):
        _run(handler.async_step_init())

    # Sans coordinator, la valeur entry.options est conservée
    assert handler._flow_rate == pytest.approx(200.0)
