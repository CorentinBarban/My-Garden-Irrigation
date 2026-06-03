"""Tests de résilience et cohérence — bugs critiques.

Approche : duck-typing sur les méthodes non-bornées pour éviter d'instancier
HomeAssistant. Chaque test cible un bug précis identifié lors de l'analyse.

Bugs couverts :
    #1  scheduler     : _handle_midnight reschedule même si _on_midnight() lève
    #2  coordinator   : update_crop_field déclenche _schedule_config_save()
    #3  coordinator   : fire_irrigation_event — pas de ZeroDivisionError si cycles_count=0
    #4  coordinator   : _on_midnight utilise _last_daily_needs quand self.data is None
    #5  coordinator   : _persist_config log WARNING si la sauvegarde échoue (pas silence)
    #6  coordinator   : _async_update_data met à jour _last_daily_needs après chaque succès
    #7  valve_tracker : _restore_valve_state absorbe les exceptions (try/except)
    #8  valve_tracker : warning loggué si valve_entity_id est absent
    #A  coordinator   : async_update_crop_field rescale le cumulatif proportionnellement
    #B  config_flow   : async_step_init synchro depuis coordinator.config
    #C  config_state  : cleanup_stale_crops() retire les entrées cumulées orphelines
    #D  init          : _cleanup_removed_crop_entities supprime les entités HA orphelines
"""
import asyncio
import logging
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.my_garden_irrigation.config_state import RuntimeConfigState
from custom_components.my_garden_irrigation.core.journal import DailyWaterLedger
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
# Fix #2 — coordinator : update_crop_field (boot) ne déclenche aucune sauvegarde
# ---------------------------------------------------------------------------

def test_update_crop_field_memory_only():
    """`update_crop_field` met à jour la mémoire sans déclencher de sauvegarde Store."""
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

    assert coord._save_calls == [], "update_crop_field (boot) ne doit pas déclencher de sauvegarde"
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
            self.data.total_daily_need_liters = 0.0

        def _resolve_watering_strategy(self):
            return IrrigationCoordinator._resolve_watering_strategy(self)

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
            self.data.total_daily_need_liters = 0.0

        def _resolve_watering_strategy(self):
            return IrrigationCoordinator._resolve_watering_strategy(self)

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
            self._daily_ledger = DailyWaterLedger()

        def _build_storage(self):
            return self.config.to_storage("2026-05-31")

        def _resolve_daily_needs(self):
            return IrrigationCoordinator._resolve_daily_needs(self)

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
            self._daily_ledger = DailyWaterLedger()

        def _build_storage(self):
            return self.config.to_storage("2026-05-31")

        def _resolve_daily_needs(self):
            return IrrigationCoordinator._resolve_daily_needs(self)

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
            self._daily_ledger = DailyWaterLedger()

        def _build_storage(self):
            return self.config.to_storage("2026-05-31")

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
            self.data = None
            self._daily_ledger = DailyWaterLedger()

        async def _fetch_weather(self):
            return 4.0, 0.0

        def _cancel_weather_retry(self) -> None:
            pass

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
    from custom_components.my_garden_irrigation.const import CONF_GLOBAL_VALVE_ENTITY_ID

    hass = MagicMock()
    hass.states.get = MagicMock(side_effect=RuntimeError("HA not ready"))

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
    from custom_components.my_garden_irrigation.const import CONF_GLOBAL_VALVE_ENTITY_ID

    hass = MagicMock()
    hass.states.get = MagicMock(return_value=None)

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
    hass.states.get = MagicMock(return_value=None)
    config = _make_state()  # valve_entity_id = None par défaut

    tracker = ValveTracker(hass, config, AsyncMock())

    with caplog.at_level(
        logging.WARNING, logger="custom_components.my_garden_irrigation.valve_tracker"
    ):
        cleanup = _run(tracker.setup())

    assert "Aucune vanne globale configurée" in caplog.text
    cleanup()  # le callable de nettoyage ne doit pas crasher


# ---------------------------------------------------------------------------
# Mode Cycle & Soak — ValveTracker accumulation inter-cycles
# ---------------------------------------------------------------------------

def _make_valve_tracker_env(cycles: int, flow_rate: float = 360.0):
    """Crée un ValveTracker configuré pour N cycles avec crop c1 (1 m²)."""
    from custom_components.my_garden_irrigation.valve_tracker import ValveTracker
    from custom_components.my_garden_irrigation.const import CONF_GLOBAL_VALVE_ENTITY_ID

    config = _make_state(**{
        CONF_GLOBAL_VALVE_ENTITY_ID: "switch.vanne",
        CONF_GLOBAL_FLOW_RATE: flow_rate,
    })
    config.begin_irrigation_session(cycles)

    callback = AsyncMock()
    hass = MagicMock()
    tracker = ValveTracker(hass, config, callback)
    return tracker, config, callback


def _simulate_close(tracker, config, open_dt, close_dt):
    """Simule une fermeture de vanne avec mocking du temps."""
    from unittest.mock import patch

    config.set_valve_open_time(open_dt)
    with patch("custom_components.my_garden_irrigation.valve_tracker.dt_util") as mock_dt:
        mock_dt.utcnow.return_value = close_dt
        with patch.object(config, "get_crop_surfaces", return_value={"c1": 1.0}):
            _run(tracker._handle_valve_close())


def test_valve_tracker_defers_callback_on_intermediate_closes():
    """En mode fractionné (3 cycles), le callback n'est déclenché qu'à la 3e fermeture."""
    from datetime import datetime, timezone, timedelta

    tracker, config, callback = _make_valve_tracker_env(cycles=3)
    t0 = datetime(2024, 1, 1, 6, 0, 0, tzinfo=timezone.utc)
    t10 = t0 + timedelta(minutes=10)

    _simulate_close(tracker, config, t0, t10)
    callback.assert_not_called()

    _simulate_close(tracker, config, t0, t10)
    callback.assert_not_called()

    _simulate_close(tracker, config, t0, t10)
    callback.assert_called_once()


def test_valve_tracker_accumulates_volumes_from_all_cycles():
    """Le callback reçoit la somme des volumes de tous les cycles (3 × 10 min à 360 L/h = 180 L)."""
    from datetime import datetime, timezone, timedelta

    tracker, config, callback = _make_valve_tracker_env(cycles=3, flow_rate=360.0)
    t0 = datetime(2024, 1, 1, 6, 0, 0, tzinfo=timezone.utc)
    t10 = t0 + timedelta(minutes=10)  # 10 min → 60 L par cycle

    _simulate_close(tracker, config, t0, t10)
    _simulate_close(tracker, config, t0, t10)
    _simulate_close(tracker, config, t0, t10)

    volumes = callback.call_args[0][0]
    assert volumes["c1"] == pytest.approx(180.0)  # 3 × 60 L


def test_valve_tracker_single_cycle_fires_immediately():
    """En mode continu (1 cycle), le callback est déclenché immédiatement à la fermeture."""
    from datetime import datetime, timezone, timedelta

    tracker, config, callback = _make_valve_tracker_env(cycles=1, flow_rate=360.0)
    t0 = datetime(2024, 1, 1, 6, 0, 0, tzinfo=timezone.utc)
    t10 = t0 + timedelta(minutes=10)

    _simulate_close(tracker, config, t0, t10)
    callback.assert_called_once()
    volumes = callback.call_args[0][0]
    assert volumes["c1"] == pytest.approx(60.0)


def test_valve_tracker_no_session_fires_immediately():
    """Sans session active (fermeture manuelle), le callback est déclenché immédiatement."""
    from datetime import datetime, timezone, timedelta

    tracker, config, callback = _make_valve_tracker_env(cycles=1, flow_rate=360.0)
    # On ne démarre pas de session — simule une ouverture manuelle
    config._session_remaining_closes = 0

    t0 = datetime(2024, 1, 1, 6, 0, 0, tzinfo=timezone.utc)
    t10 = t0 + timedelta(minutes=1)

    _simulate_close(tracker, config, t0, t10)
    callback.assert_called_once()


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
            self._daily_ledger = DailyWaterLedger()

        def _build_storage(self):
            return self.config.to_storage("2026-05-31")

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
            self._daily_ledger = DailyWaterLedger()

        def _build_storage(self):
            return self.config.to_storage("2026-05-31")

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
            self._daily_ledger = DailyWaterLedger()

        def _build_storage(self):
            return self.config.to_storage("2026-05-31")

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
            self._daily_ledger = DailyWaterLedger()

        def _build_storage(self):
            return self.config.to_storage("2026-05-31")

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


# ---------------------------------------------------------------------------
# Fix #C — config_state : cleanup_stale_crops retire les entrées orphelines
# ---------------------------------------------------------------------------

def test_cleanup_stale_crops_removes_from_cumulative():
    """Les crop_ids absents des options sont retirés du cumulatif et daily."""
    crop = {
        CONF_CROP_ID: "c1",
        CONF_CROP_TYPE: "tomate",
        CONF_STAGE: "mid",
        CONF_NB_PLANTS: 10,
        CONF_DENSITY: 2.0,
    }
    state = RuntimeConfigState(_options(**{CONF_CROPS: [crop]}))
    state._cumulative_need = {"c1": 10.0, "c_old": 25.0}
    state._watering_applied_today = {"c1": 2.0, "c_old": 8.0}

    state.cleanup_stale_crops()

    assert "c_old" not in state.cumulative_need
    assert "c_old" not in state.watering_applied_today
    assert state.cumulative_need["c1"] == pytest.approx(10.0)
    assert state.watering_applied_today["c1"] == pytest.approx(2.0)


def test_cleanup_stale_crops_empty_noop():
    """Sans données, cleanup_stale_crops ne lève pas."""
    state = _make_state()
    state.cleanup_stale_crops()
    assert state.cumulative_need == {}


def test_cleanup_stale_crops_current_preserved():
    """Les cultures actuelles ne sont pas touchées."""
    crop = {CONF_CROP_ID: "c1", CONF_CROP_TYPE: "tomate", CONF_STAGE: "mid",
            CONF_NB_PLANTS: 10, CONF_DENSITY: 2.0}
    state = RuntimeConfigState(_options(**{CONF_CROPS: [crop]}))
    state._cumulative_need = {"c1": 15.0}
    state.cleanup_stale_crops()
    assert state.cumulative_need == {"c1": pytest.approx(15.0)}


# ---------------------------------------------------------------------------
# Fix #D — __init__ : _cleanup_removed_crop_entities
# ---------------------------------------------------------------------------

def _patch_registry(entities, registry_mock):
    return (
        patch("custom_components.my_garden_irrigation.__init__.er.async_get",
              return_value=registry_mock),
        patch("custom_components.my_garden_irrigation.__init__.er.async_entries_for_config_entry",
              return_value=entities),
    )


def test_cleanup_removes_nb_plants_orphan():
    """unique_id {entry_id}_{crop_id}_nb_plants est supprimé si culture absente."""
    from custom_components.my_garden_irrigation.__init__ import _cleanup_removed_crop_entities

    crop_id = "550e8400-e29b-41d4-a716-446655440000"
    entry_id = "entry-abc"
    entry = MagicMock(); entry.entry_id = entry_id

    entity = MagicMock()
    entity.unique_id = f"{entry_id}_{crop_id}_nb_plants"
    entity.entity_id = "number.crop_nb_plants"

    registry = MagicMock()
    p1, p2 = _patch_registry([entity], registry)
    with p1, p2:
        _cleanup_removed_crop_entities(MagicMock(), entry, set())
    registry.async_remove.assert_called_once_with(entity.entity_id)


def test_cleanup_preserves_current_crop():
    """L'entité d'une culture encore présente n'est pas supprimée."""
    from custom_components.my_garden_irrigation.__init__ import _cleanup_removed_crop_entities

    crop_id = "550e8400-e29b-41d4-a716-446655440000"
    entry_id = "entry-abc"
    entry = MagicMock(); entry.entry_id = entry_id

    entity = MagicMock()
    entity.unique_id = f"{entry_id}_{crop_id}_nb_plants"

    registry = MagicMock()
    p1, p2 = _patch_registry([entity], registry)
    with p1, p2:
        _cleanup_removed_crop_entities(MagicMock(), entry, {crop_id})
    registry.async_remove.assert_not_called()


def test_cleanup_preserves_global_entities():
    """Les entités globales (eto, total, flow_rate) ne sont jamais supprimées."""
    from custom_components.my_garden_irrigation.__init__ import _cleanup_removed_crop_entities

    entry_id = "entry-abc"
    entry = MagicMock(); entry.entry_id = entry_id

    globals_ = [
        MagicMock(unique_id=f"{entry_id}_eto",              entity_id="sensor.eto"),
        MagicMock(unique_id=f"{entry_id}_total_cumulative", entity_id="sensor.total"),
        MagicMock(unique_id=f"{entry_id}_global_flow_rate", entity_id="number.flow"),
        MagicMock(unique_id=f"{entry_id}_next_watering",    entity_id="sensor.next"),
    ]
    registry = MagicMock()
    p1, p2 = _patch_registry(globals_, registry)
    with p1, p2:
        _cleanup_removed_crop_entities(MagicMock(), entry, set())
    registry.async_remove.assert_not_called()


def test_cleanup_removes_irrigation_sensor_no_suffix():
    """IrrigationDataSensor (unique_id = {entry_id}_{uuid}) est aussi nettoyé."""
    from custom_components.my_garden_irrigation.__init__ import _cleanup_removed_crop_entities

    crop_id = "550e8400-e29b-41d4-a716-446655440000"
    entry_id = "entry-abc"
    entry = MagicMock(); entry.entry_id = entry_id

    entity = MagicMock()
    entity.unique_id = f"{entry_id}_{crop_id}"  # pas de suffix
    entity.entity_id = "sensor.irrigation_data"

    registry = MagicMock()
    p1, p2 = _patch_registry([entity], registry)
    with p1, p2:
        _cleanup_removed_crop_entities(MagicMock(), entry, set())
    registry.async_remove.assert_called_once_with(entity.entity_id)


# ===========================================================================
# NOUVEAUX TESTS — 6 bugs identifiés lors de l'analyse approfondie
# ===========================================================================

# ---------------------------------------------------------------------------
# Bug #1 — Reset Fantôme : la date n'est mise à jour QUE si l'événement a été émis
# ---------------------------------------------------------------------------

def test_on_trigger_no_date_update_when_data_unavailable():
    """Règle 3 spec : si data is None (météo indispo), la date NE doit PAS être mise à jour."""
    from custom_components.my_garden_irrigation.coordinator import IrrigationCoordinator

    class FakeCoord:
        data = None          # données météo indisponibles
        _date_updated = False

        def fire_irrigation_event(self) -> bool:
            return False

        async def update_last_watering_date(self, date_iso: str) -> None:
            FakeCoord._date_updated = True

        async def _on_interval_reached_calendar(self, date_iso: str) -> None:
            await IrrigationCoordinator._on_interval_reached_calendar(self, date_iso)

        async def _on_interval_reached_agronomic(self) -> None:
            await IrrigationCoordinator._on_interval_reached_agronomic(self)

    coord = FakeCoord()
    _run(IrrigationCoordinator._on_trigger(coord, "2026-06-01"))

    assert not coord._date_updated, (
        "La date ne doit pas être mise à jour si les données météo sont indisponibles"
    )


def test_on_trigger_updates_date_when_event_fired():
    """`_on_trigger` met à jour la date quand data est disponible et l'événement est émis."""
    from custom_components.my_garden_irrigation.coordinator import IrrigationCoordinator

    class FakeCoord:
        _date_updated = False
        _persistence = MagicMock()
        _persistence.async_save = AsyncMock()
        data = MagicMock()   # données météo disponibles

        def __init__(self):
            self.config = _make_state()

        def fire_irrigation_event(self) -> bool:
            return True

        async def update_last_watering_date(self, date_iso: str) -> None:
            FakeCoord._date_updated = True

        async def _on_interval_reached_calendar(self, date_iso: str) -> None:
            await IrrigationCoordinator._on_interval_reached_calendar(self, date_iso)

        async def _on_interval_reached_agronomic(self) -> None:
            await IrrigationCoordinator._on_interval_reached_agronomic(self)

    coord = FakeCoord()
    _run(IrrigationCoordinator._on_trigger(coord, "2026-06-01"))

    assert coord._date_updated


def test_on_trigger_updates_date_even_when_volume_zero():
    """Règle 3 spec : si data dispo mais besoin=0 (pluie), la date DOIT être mise à jour."""
    from custom_components.my_garden_irrigation.coordinator import IrrigationCoordinator

    class FakeCoord:
        _date_updated = False
        data = MagicMock()   # données disponibles

        def fire_irrigation_event(self) -> bool:
            return False     # volume nul — annulation agronomique (pluie)

        async def update_last_watering_date(self, date_iso: str) -> None:
            FakeCoord._date_updated = True

        async def _on_interval_reached_calendar(self, date_iso: str) -> None:
            await IrrigationCoordinator._on_interval_reached_calendar(self, date_iso)

        async def _on_interval_reached_agronomic(self) -> None:
            await IrrigationCoordinator._on_interval_reached_agronomic(self)

    coord = FakeCoord()
    _run(IrrigationCoordinator._on_trigger(coord, "2026-06-01"))

    assert coord._date_updated, (
        "Règle 3 : la date doit être ancrée même si aucun litre n'est distribué (pluie)"
    )


def test_fire_irrigation_event_returns_false_when_cumulative_zero():
    """`fire_irrigation_event` retourne False si le volume cible est nul (matin, cumul=0)."""
    from custom_components.my_garden_irrigation.coordinator import IrrigationCoordinator

    class FakeCoord:
        hass = MagicMock()
        _entry = MagicMock()
        _entry.entry_id = "test"

        def __init__(self):
            self.config = _make_state(**{
                CONF_GLOBAL_FLOW_RATE: 300.0,
                CONF_IRRIGATION_TIME: "06:00:00",   # matin → pas d'inclusif journalier
            })
            self.data = MagicMock()
            self.data.cumulative_need = {"c1": 0.0}
            self.data.total_daily_need_liters = 0.0

        def _resolve_watering_strategy(self):
            return IrrigationCoordinator._resolve_watering_strategy(self)

    coord = FakeCoord()
    result = IrrigationCoordinator.fire_irrigation_event(coord)

    assert result is False
    coord.hass.bus.async_fire.assert_not_called()


def test_fire_irrigation_event_returns_true_when_fired():
    """`fire_irrigation_event` retourne True si l'événement est émis."""
    from custom_components.my_garden_irrigation.coordinator import IrrigationCoordinator

    class FakeCoord:
        hass = MagicMock()
        _entry = MagicMock()
        _entry.entry_id = "test"

        def __init__(self):
            self.config = _make_state(**{CONF_GLOBAL_FLOW_RATE: 300.0})
            self.data = MagicMock()
            self.data.cumulative_need = {"c1": 10.0}
            self.data.total_daily_need_liters = 0.0

        def _resolve_watering_strategy(self):
            return IrrigationCoordinator._resolve_watering_strategy(self)

    coord = FakeCoord()
    result = IrrigationCoordinator.fire_irrigation_event(coord)

    assert result is True
    coord.hass.bus.async_fire.assert_called_once()


# ---------------------------------------------------------------------------
# Bug #3 — États réseau : _was_open survit aux états unavailable/unknown
# ---------------------------------------------------------------------------

def _make_event(new_state_str: str, old_state_str: str = "on"):
    """Crée un faux événement de changement d'état de vanne."""
    old = MagicMock()
    old.state = old_state_str
    new = MagicMock()
    new.state = new_state_str
    event = MagicMock()
    event.data = {"old_state": old, "new_state": new}
    return event


def test_unavailable_does_not_reset_was_open():
    """`unavailable` après `open` ne remet pas _was_open à False."""
    from custom_components.my_garden_irrigation.valve_tracker import ValveTracker
    from custom_components.my_garden_irrigation.const import CONF_GLOBAL_VALVE_ENTITY_ID

    config = _make_state(**{CONF_GLOBAL_VALVE_ENTITY_ID: "switch.vanne"})
    tracker = ValveTracker(MagicMock(), config, AsyncMock())
    tracker._was_open = True
    config.set_valve_open_time(MagicMock())  # simule une vanne ouverte

    tracker._handle_valve_state_change(_make_event("unavailable"))

    assert tracker._was_open is True, "_was_open doit rester True pendant unavailable"


def test_unknown_does_not_reset_was_open():
    """`unknown` après `open` ne remet pas _was_open à False."""
    from custom_components.my_garden_irrigation.valve_tracker import ValveTracker
    from custom_components.my_garden_irrigation.const import CONF_GLOBAL_VALVE_ENTITY_ID

    config = _make_state(**{CONF_GLOBAL_VALVE_ENTITY_ID: "switch.vanne"})
    tracker = ValveTracker(MagicMock(), config, AsyncMock())
    tracker._was_open = True

    tracker._handle_valve_state_change(_make_event("unknown"))

    assert tracker._was_open is True


def test_close_after_unavailable_triggers_handle_close():
    """`open → unavailable → closed` : la fermeture est correctement détectée."""
    from custom_components.my_garden_irrigation.valve_tracker import ValveTracker
    from custom_components.my_garden_irrigation.const import CONF_GLOBAL_VALVE_ENTITY_ID

    hass = MagicMock()
    # Fermer la coroutine pour éviter RuntimeWarning : coroutine never awaited
    hass.async_create_task.side_effect = lambda coro: coro.close()
    config = _make_state(**{
        CONF_GLOBAL_VALVE_ENTITY_ID: "switch.vanne",
        CONF_GLOBAL_FLOW_RATE: 300.0,
    })
    tracker = ValveTracker(hass, config, AsyncMock())
    tracker._was_open = True
    config.set_valve_open_time(MagicMock())

    tracker._handle_valve_state_change(_make_event("unavailable"))
    assert tracker._was_open  # toujours ouvert

    tracker._handle_valve_state_change(_make_event("off", "unavailable"))
    assert not tracker._was_open  # fermé maintenant
    hass.async_create_task.assert_called_once()  # _handle_valve_close déclenché


def test_open_after_unavailable_sets_open_time_once():
    """`closed → unavailable → open` : l'ouverture n'est enregistrée qu'une fois."""
    from custom_components.my_garden_irrigation.valve_tracker import ValveTracker
    from custom_components.my_garden_irrigation.const import CONF_GLOBAL_VALVE_ENTITY_ID

    config = _make_state(**{CONF_GLOBAL_VALVE_ENTITY_ID: "switch.vanne"})
    tracker = ValveTracker(MagicMock(), config, AsyncMock())
    tracker._was_open = False

    tracker._handle_valve_state_change(_make_event("unavailable", "off"))
    assert not tracker._was_open  # toujours fermé

    with patch("custom_components.my_garden_irrigation.valve_tracker.dt_util") as mock_dt:
        mock_dt.utcnow.return_value = MagicMock()
        tracker._handle_valve_state_change(_make_event("on", "unavailable"))

    assert tracker._was_open  # ouvert maintenant
    assert config.get_valve_open_time() is not None


# ---------------------------------------------------------------------------
# Bug #4 — Affichage figé : les listeners sont notifiés après un set_*
# ---------------------------------------------------------------------------

def test_set_flow_rate_notifies_listeners():
    """`set_flow_rate` notifie les listeners sans déclencher d'appel météo."""
    from custom_components.my_garden_irrigation.coordinator import IrrigationCoordinator

    class FakeCoord:
        _save_calls: list = []
        _notify_calls: list = []

        def __init__(self):
            self.config = _make_state()
            self.data = MagicMock()  # non-None → listeners notifiés

        def _schedule_config_save(self) -> None:
            self._save_calls.append(1)

        def _notify_listeners(self) -> None:
            self._notify_calls.append(1)

    coord = FakeCoord()
    IrrigationCoordinator.set_flow_rate(coord, 450.0)

    assert coord.config.flow_rate == pytest.approx(450.0)
    assert coord._save_calls == [1]
    assert coord._notify_calls == [1]


def test_set_watering_mode_notifies_listeners():
    """`set_watering_mode` notifie les listeners."""
    from custom_components.my_garden_irrigation.coordinator import IrrigationCoordinator

    class FakeCoord:
        _notify_calls: list = []

        def __init__(self):
            self.config = _make_state()
            self.data = MagicMock()

        def _schedule_config_save(self) -> None:
            pass

        def _notify_listeners(self) -> None:
            self._notify_calls.append(1)

    coord = FakeCoord()
    IrrigationCoordinator.set_watering_mode(coord, WATERING_MODE_FRACTIONED)

    assert coord._notify_calls == [1]


def test_notify_listeners_noop_when_no_data():
    """`_notify_listeners` ne lève pas si self.data est None."""
    from custom_components.my_garden_irrigation.coordinator import IrrigationCoordinator

    class FakeCoord:
        data = None
        _listener_calls: list = []

        def async_update_listeners(self) -> None:
            self._listener_calls.append(1)

    coord = FakeCoord()
    IrrigationCoordinator._notify_listeners(coord)

    assert coord._listener_calls == []


# ---------------------------------------------------------------------------
# Bug #5 — Double-polling : _async_recompute_from_cache évite le 2e appel HTTP
# ---------------------------------------------------------------------------

def test_async_recompute_from_cache_uses_cached_weather():
    """`_async_recompute_from_cache` utilise le cache météo sans appel HTTP."""
    from custom_components.my_garden_irrigation.coordinator import IrrigationCoordinator
    from custom_components.my_garden_irrigation.core.models import IrrigationData

    fake_data = MagicMock(spec=IrrigationData)
    fake_data.crops = {}

    class FakeCoord:
        _last_weather = (3.5, 1.2)
        _last_daily_needs: dict = {}

        def __init__(self):
            self.config = _make_state()
            self._kc_data = {}
            self._updated_data = None

        def async_set_updated_data(self, data) -> None:
            self._updated_data = data

    coord = FakeCoord()

    with patch(
        "custom_components.my_garden_irrigation.coordinator.compute_irrigation_data",
        return_value=fake_data,
    ) as mock_compute:
        _run(IrrigationCoordinator._async_recompute_from_cache(coord))

    mock_compute.assert_called_once()
    call_kwargs = mock_compute.call_args[1]
    assert call_kwargs["eto_mm"] == pytest.approx(3.5)
    assert call_kwargs["precipitation_mm"] == pytest.approx(1.2)
    assert coord._updated_data is fake_data


def test_async_recompute_from_cache_noop_when_no_cache():
    """`_async_recompute_from_cache` ne fait rien si le cache météo est absent."""
    from custom_components.my_garden_irrigation.coordinator import IrrigationCoordinator

    class FakeCoord:
        _last_weather = None
        _updated = False

        def __init__(self):
            self.config = _make_state()

        def async_set_updated_data(self, data) -> None:
            self._updated = True

    coord = FakeCoord()

    with patch(
        "custom_components.my_garden_irrigation.coordinator.compute_irrigation_data"
    ) as mock_compute:
        _run(IrrigationCoordinator._async_recompute_from_cache(coord))

    mock_compute.assert_not_called()
    assert not coord._updated


def test_async_update_data_caches_last_weather():
    """`_async_update_data` stocke le résultat météo dans _last_weather."""
    from custom_components.my_garden_irrigation.coordinator import IrrigationCoordinator
    from custom_components.my_garden_irrigation.core.models import IrrigationData

    fake_data = MagicMock(spec=IrrigationData)
    fake_data.crops = {}

    class FakeCoord:
        _last_daily_needs: dict = {}

        def __init__(self):
            self.config = _make_state()
            self._kc_data = {}
            self.data = None

        async def _fetch_weather(self):
            return 5.0, 2.0

        def _cancel_weather_retry(self) -> None:
            pass

    coord = FakeCoord()

    with patch(
        "custom_components.my_garden_irrigation.coordinator.compute_irrigation_data",
        return_value=fake_data,
    ):
        _run(IrrigationCoordinator._async_update_data(coord))

    assert hasattr(coord, "_last_weather")
    assert coord._last_weather == (pytest.approx(5.0), pytest.approx(2.0))


# ---------------------------------------------------------------------------
# Bug #6 — Encapsulation : scale_cumulative_need() dans RuntimeConfigState
# ---------------------------------------------------------------------------

def test_scale_cumulative_need_scales_correctly():
    """`scale_cumulative_need` multiplie le cumulé par le facteur donné."""
    state = _make_state()
    state._cumulative_need = {"c1": 20.0}

    state.scale_cumulative_need("c1", 2.0)

    assert state.cumulative_need["c1"] == pytest.approx(40.0)


def test_scale_cumulative_need_rounding():
    """`scale_cumulative_need` arrondit à 3 décimales."""
    state = _make_state()
    state._cumulative_need = {"c1": 10.0}

    state.scale_cumulative_need("c1", 1 / 3)

    assert state.cumulative_need["c1"] == pytest.approx(3.333, abs=0.001)


def test_scale_cumulative_need_missing_crop_no_crash():
    """`scale_cumulative_need` ignore un crop_id inexistant sans exception."""
    state = _make_state()
    state._cumulative_need = {}

    state.scale_cumulative_need("inexistant", 3.0)  # ne doit pas lever

    assert state.cumulative_need == {}


def test_async_update_crop_field_uses_scale_method():
    """async_update_crop_field n'accède plus à config._cumulative_need directement."""
    import inspect
    from custom_components.my_garden_irrigation import coordinator as coord_module

    source = inspect.getsource(coord_module.IrrigationCoordinator.async_update_crop_field)
    # On vérifie l'absence d'accès direct à l'attribut privé (config._cumulative_need[...]).
    # La présence du nom de méthode scale_cumulative_need est normale.
    assert "._cumulative_need" not in source, (
        "async_update_crop_field ne doit plus accéder directement à config._cumulative_need ; "
        "utiliser config.scale_cumulative_need() à la place."
    )


# ---------------------------------------------------------------------------
# Règle 2 spec — volume inclusif pour arrosage tardif (Anomalie B)
# ---------------------------------------------------------------------------

def test_fire_irrigation_event_evening_includes_daily_need():
    """Scénario II spec : arrosage 21h00 → volume = cumul + journalier."""
    from custom_components.my_garden_irrigation.coordinator import IrrigationCoordinator

    fired_payload: dict = {}

    class FakeCoord:
        _entry = MagicMock()
        _entry.entry_id = "test"

        def __init__(self):
            self.config = _make_state(**{
                CONF_GLOBAL_FLOW_RATE: 300.0,
                CONF_IRRIGATION_TIME: "21:00:00",   # arrosage tardif
            })
            self.data = MagicMock()
            self.data.cumulative_need = {"c1": 8.0}
            self.data.total_daily_need_liters = 4.0

        @property
        def hass(self):
            hass = MagicMock()
            def _fire(event_type, payload):
                fired_payload.update(payload)
            hass.bus.async_fire.side_effect = _fire
            return hass

        def _resolve_watering_strategy(self):
            return IrrigationCoordinator._resolve_watering_strategy(self)

    coord = FakeCoord()
    result = IrrigationCoordinator.fire_irrigation_event(coord)

    assert result is True
    assert fired_payload.get("total_volume_liters") == pytest.approx(12.0), (
        "Volume cible soir = cumul(8L) + journalier(4L) = 12L"
    )


def test_fire_irrigation_event_morning_excludes_daily_need():
    """Arrosage 06h00 : volume = cumul seulement (besoin journalier non inclus)."""
    from custom_components.my_garden_irrigation.coordinator import IrrigationCoordinator

    fired_payload: dict = {}

    class FakeCoord:
        _entry = MagicMock()
        _entry.entry_id = "test"

        def __init__(self):
            self.config = _make_state(**{
                CONF_GLOBAL_FLOW_RATE: 300.0,
                CONF_IRRIGATION_TIME: "06:00:00",   # arrosage matinal
            })
            self.data = MagicMock()
            self.data.cumulative_need = {"c1": 8.0}
            self.data.total_daily_need_liters = 4.0

        @property
        def hass(self):
            hass = MagicMock()
            def _fire(event_type, payload):
                fired_payload.update(payload)
            hass.bus.async_fire.side_effect = _fire
            return hass

        def _resolve_watering_strategy(self):
            return IrrigationCoordinator._resolve_watering_strategy(self)

    coord = FakeCoord()
    result = IrrigationCoordinator.fire_irrigation_event(coord)

    assert result is True
    assert fired_payload.get("total_volume_liters") == pytest.approx(8.0), (
        "Volume cible matin = cumul(8L) seulement"
    )


def test_fire_irrigation_event_evening_zero_cumul_fires_if_daily_need():
    """Soir + cumul=0 mais besoin journalier > 0 : l'arrosage doit quand même s'émettre."""
    from custom_components.my_garden_irrigation.coordinator import IrrigationCoordinator

    class FakeCoord:
        hass = MagicMock()
        _entry = MagicMock()
        _entry.entry_id = "test"

        def __init__(self):
            self.config = _make_state(**{
                CONF_GLOBAL_FLOW_RATE: 300.0,
                CONF_IRRIGATION_TIME: "21:00:00",
            })
            self.data = MagicMock()
            self.data.cumulative_need = {"c1": 0.0}
            self.data.total_daily_need_liters = 4.0

        def _resolve_watering_strategy(self):
            return IrrigationCoordinator._resolve_watering_strategy(self)

    coord = FakeCoord()
    result = IrrigationCoordinator.fire_irrigation_event(coord)

    assert result is True
    coord.hass.bus.async_fire.assert_called_once()


# ---------------------------------------------------------------------------
# Règle 3 spec — immunisation calendrier (Anomalie C)
# ---------------------------------------------------------------------------

def test_on_trigger_calendar_immune_to_rain():
    """Scénario III spec : sol saturé (cumul=0) → date ancrée, calendrier préservé."""
    from custom_components.my_garden_irrigation.coordinator import IrrigationCoordinator
    from custom_components.my_garden_irrigation.core.models import IrrigationData

    dates_saved: list[str] = []

    class FakeCoord:
        def __init__(self):
            self.config = _make_state()
            # Données disponibles mais besoin cumulé nul (pluie)
            self.data = IrrigationData(
                cumulative_need={"c1": 0.0},
                total_daily_need_liters=0.0,
            )

        def fire_irrigation_event(self) -> bool:
            return False   # volume = 0

        async def update_last_watering_date(self, date_iso: str) -> None:
            dates_saved.append(date_iso)

        async def _on_interval_reached_calendar(self, date_iso: str) -> None:
            await IrrigationCoordinator._on_interval_reached_calendar(self, date_iso)

        async def _on_interval_reached_agronomic(self) -> None:
            await IrrigationCoordinator._on_interval_reached_agronomic(self)

    coord = FakeCoord()
    _run(IrrigationCoordinator._on_trigger(coord, "2026-06-03"))

    assert dates_saved == ["2026-06-03"], (
        "Règle 3 : la date doit être ancrée au Jour 3 même si 0 L distribués"
    )


def test_on_trigger_no_calendar_skip_on_technical_failure():
    """Si data is None (erreur technique), la date n'est pas ancrée pour éviter le saut."""
    from custom_components.my_garden_irrigation.coordinator import IrrigationCoordinator

    dates_saved: list[str] = []

    class FakeCoord:
        data = None

        def fire_irrigation_event(self) -> bool:
            return False

        async def update_last_watering_date(self, date_iso: str) -> None:
            dates_saved.append(date_iso)

        async def _on_interval_reached_calendar(self, date_iso: str) -> None:
            await IrrigationCoordinator._on_interval_reached_calendar(self, date_iso)

        async def _on_interval_reached_agronomic(self) -> None:
            await IrrigationCoordinator._on_interval_reached_agronomic(self)

    coord = FakeCoord()
    _run(IrrigationCoordinator._on_trigger(coord, "2026-06-03"))

    assert dates_saved == [], (
        "Erreur technique (data=None) : la date ne doit pas être avancée"
    )
