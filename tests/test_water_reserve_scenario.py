"""Scénarios de validation — bilan hydrique signé, réserve, décision inclusive,
réancrage sur arrosage réel (ADR-028).

Chaque scénario déroule plusieurs jours de bout en bout au niveau des fonctions pures,
en suivant le même enchaînement que le coordinator et le scheduler :

    météo → bilan signé du jour → journal → (intervalle atteint ?) → décision d'arrosage
    → (arrosage + réancrage) → clôture de minuit

Règles validées (toutes implémentées) :
  - Bilan jour = ETc − pluie efficace (signé ; pluie déjà ×0,8).
  - Arrosage si intervalle atteint ET (cumulé + bilan jour) > 0 ; volume = cumulé + bilan jour.
  - Cumulé fin = 0 si arrosage, sinon cumulé début + bilan jour.
  - Réancrage du cycle uniquement si un arrosage a lieu.

Surface : 6 m² (6 plants, densité 1) → 1 mm = 6 L, pluie efficace = pluie brute × 0,8.
"""
from dataclasses import dataclass
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
_SURFACE_M2 = 6.0
_RAIN_FACTOR = 0.8


def _kc_getter(kc_data, crop_type, stage):
    return kc_data.get("crops", {}).get(crop_type, {}).get(stage)


@dataclass
class DayOutcome:
    """Grandeurs clés d'une journée simulée."""

    balance: float          # bilan signé du jour (L)
    interval_reached: bool  # le scheduler a-t-il évalué l'arrosage ce jour ?
    volume: float           # volume arrosé (L), 0 si aucun
    watered: bool           # un arrosage a-t-il été émis ?
    reanchored: bool        # le cycle d'intervalle a-t-il été réancré ?
    cumulative: float       # bilan cumulé après la clôture de minuit (L)


class _Garden:
    """Simulateur jour par jour câblé sur les vraies fonctions du domaine.

    Le bilan cumulé vit dans un RuntimeConfigState (apply_watering / clôture réels) ;
    le journal, la stratégie inclusive et la clôture de minuit sont les modules réels.
    Le besoin et la pluie sont exprimés en **litres** (Kc=1, surface 6 m²) ; la pluie
    fournie est la pluie *efficace* (le facteur 0,8 est appliqué en interne via precip brute).
    """

    def __init__(self, interval_days: int = 1) -> None:
        crop = {
            CONF_CROP_ID: _CROP_ID,
            CONF_CROP_TYPE: "tomate",
            CONF_STAGE: "mid",
            CONF_NB_PLANTS: 6,
            CONF_DENSITY: 1.0,
        }
        self.state = RuntimeConfigState({CONF_CROPS: [crop], CONF_GLOBAL_FLOW_RATE: 360.0})
        self.state._cumulative_need = {_CROP_ID: 0.0}
        self.interval_days = interval_days
        self.day_index = 0
        self.last_watering_day = 0  # ancrage initial du cycle au « jour 0 »
        self._strategy = WateringStrategyFactory.from_irrigation_time("06:00:00")

    @property
    def cumulative(self) -> float:
        return self.state.cumulative_need[_CROP_ID]

    def set_initial_debt(self, litres: float) -> None:
        self.state._cumulative_need[_CROP_ID] = litres

    def manual_water(self, litres: float) -> None:
        """Arrosage manuel : impute le volume au cumulé SANS réancrer le calendrier.

        Reflète une ouverture/fermeture de vanne hors planificateur (_on_volumes_applied
        appelle apply_watering_volumes mais pas update_last_watering_date).
        """
        self.state.apply_watering_volumes({_CROP_ID: litres})

    def day(self, *, besoin_l: float = 0.0, pluie_eff_l: float = 0.0) -> DayOutcome:
        self.day_index += 1
        ledger = DailyWaterLedger()

        # Conversion litres → météo : ETc = Kc·ETo·surface (Kc=1), pluie efficace = brute·0,8.
        eto_mm = besoin_l / _SURFACE_M2
        precipitation_mm = pluie_eff_l / (_SURFACE_M2 * _RAIN_FACTOR)

        data = compute_irrigation_data(
            crops=self.state.crops,
            kc_data=_KC_DATA,
            eto_mm=eto_mm,
            precipitation_mm=precipitation_mm,
            kc_getter=_kc_getter,
            cumulative_need=self.state.cumulative_need,
        )
        ledger.set_daily_need(_CROP_ID, data.crops[_CROP_ID].daily_balance_liters, _NOW)

        # Le scheduler n'évalue l'arrosage que si l'intervalle est atteint.
        interval_reached = (self.day_index - self.last_watering_day) >= self.interval_days

        volume = 0.0
        watered = False
        reanchored = False
        if interval_reached:
            target = self._strategy.calculate_target_volume(
                sum(self.state.cumulative_need.values()), data.total_daily_balance_liters
            )
            if target > 0:
                volume = target
                watered = True
                self.state.apply_watering_volumes({_CROP_ID: target})
                ledger.record(
                    WaterTransaction(_CROP_ID, -target, WaterSource.IRRIGATION, _NOW)
                )
                self.last_watering_day = self.day_index  # réancrage sur arrosage réel
                reanchored = True

        # Clôture de minuit : ajoute le bilan signé du jour (arrosage exclu de replay).
        new_cumulative = MidnightClosureOrchestrator().execute(
            self.state.cumulative_need, ledger.replay()
        )
        self.state.apply_midnight_result(new_cumulative)

        return DayOutcome(
            balance=data.total_daily_balance_liters,
            interval_reached=interval_reached,
            volume=volume,
            watered=watered,
            reanchored=reanchored,
            cumulative=self.cumulative,
        )


# ===========================================================================
# Scénario de référence — réserve de pluie puis reprise (ADR-028, intervalle 3 j)
# ===========================================================================

def test_scenario_ref_rain_reserve_then_waters_when_depleted():
    """4 jours : surplus de pluie banqué, J3 sauté sans réancrage, arrosage 40 L au J4."""
    g = _Garden(interval_days=3)

    j1 = g.day(besoin_l=0.0, pluie_eff_l=72.0)   # pluie 15 mm → 72 L efficaces
    assert j1.balance == pytest.approx(-72.0)
    assert j1.watered is False
    assert j1.cumulative == pytest.approx(-72.0)

    j2 = g.day(besoin_l=0.0, pluie_eff_l=48.0)   # pluie 10 mm → 48 L efficaces
    assert j2.balance == pytest.approx(-48.0)
    assert j2.watered is False
    assert j2.cumulative == pytest.approx(-120.0)

    j3 = g.day(besoin_l=40.0, pluie_eff_l=0.0)
    assert j3.interval_reached is True, "L'intervalle de 3 j est atteint au J3"
    assert j3.watered is False, "La réserve couvre le besoin → aucun arrosage"
    assert j3.reanchored is False, "Pas d'arrosage → pas de réancrage du cycle"
    assert j3.cumulative == pytest.approx(-80.0)

    j4 = g.day(besoin_l=120.0, pluie_eff_l=0.0)
    assert j4.interval_reached is True, "Réévalué dès le lendemain (cycle non réancré au J3)"
    assert j4.watered is True
    assert j4.volume == pytest.approx(40.0)
    assert j4.reanchored is True
    assert j4.cumulative == pytest.approx(0.0)


# ===========================================================================
# Scénario A — Régime sec quotidien (intervalle 1 j, besoin 10 L/j)
# ===========================================================================

def test_scenario_a_daily_dry_waters_exact_need():
    """En quotidien, on arrose exactement le besoin du jour et le cumulé reste à 0."""
    g = _Garden(interval_days=1)
    for _ in range(3):
        d = g.day(besoin_l=10.0, pluie_eff_l=0.0)
        assert d.watered is True
        assert d.volume == pytest.approx(10.0)
        assert d.reanchored is True
        assert d.cumulative == pytest.approx(0.0)


# ===========================================================================
# Scénario B — Dette sur 3 jours puis arrosage inclusif (intervalle 3 j, besoin 4 L/j)
# ===========================================================================

def test_scenario_b_debt_accumulates_then_inclusive_watering():
    """La dette monte à 8 L, le J3 arrose 12 L (8 dette + 4 jour), cumulé remis à 0."""
    g = _Garden(interval_days=3)

    j1 = g.day(besoin_l=4.0)
    assert j1.interval_reached is False
    assert j1.cumulative == pytest.approx(4.0)

    j2 = g.day(besoin_l=4.0)
    assert j2.interval_reached is False
    assert j2.cumulative == pytest.approx(8.0)

    j3 = g.day(besoin_l=4.0)
    assert j3.interval_reached is True
    assert j3.watered is True
    assert j3.volume == pytest.approx(12.0), "Volume inclusif = 8 dette + 4 besoin du jour"
    assert j3.reanchored is True
    assert j3.cumulative == pytest.approx(0.0)

    j4 = g.day(besoin_l=4.0)
    assert j4.interval_reached is False, "Cycle réancré au J3 → J4 hors intervalle"
    assert j4.cumulative == pytest.approx(4.0)


# ===========================================================================
# Scénario C — Pluie le jour d'intervalle, gros besoin le lendemain (intervalle 3 j)
# Valide la nouvelle Règle 3 : pas de réancrage sans arrosage → arrosage dès le lendemain.
# ===========================================================================

def test_scenario_c_rain_on_interval_day_does_not_block_next_day():
    g = _Garden(interval_days=3)

    g.day(besoin_l=0.0)                       # J1
    g.day(besoin_l=0.0)                       # J2

    j3 = g.day(besoin_l=0.0, pluie_eff_l=12.0)  # J3 : pluie le jour d'intervalle
    assert j3.interval_reached is True
    assert j3.watered is False, "Pluie → aucun arrosage"
    assert j3.reanchored is False, "Nouvelle Règle 3 : pas de réancrage sans arrosage réel"
    assert j3.cumulative == pytest.approx(-12.0)

    j4 = g.day(besoin_l=20.0)                  # J4 : gros besoin, réserve insuffisante
    assert j4.interval_reached is True, "Réévalué car le cycle n'a pas été réancré au J3"
    assert j4.watered is True
    assert j4.volume == pytest.approx(8.0), "−12 réserve + 20 besoin = 8 L"
    assert j4.reanchored is True
    assert j4.cumulative == pytest.approx(0.0)


# ===========================================================================
# Scénario D — Sur-arrosage manuel crée une réserve (intervalle 3 j, besoin 12 L/j)
# ===========================================================================

def test_scenario_d_manual_overwatering_creates_reserve():
    """50 L manuels sur 20 L de dette → réserve de 30 L, épuisée en ~2,5 jours."""
    g = _Garden(interval_days=3)
    g.set_initial_debt(20.0)
    g.manual_water(50.0)
    assert g.cumulative == pytest.approx(-30.0), "20 − 50 = −30 (réserve, sans plancher)"

    j1 = g.day(besoin_l=12.0)
    assert j1.watered is False
    assert j1.cumulative == pytest.approx(-18.0)

    j2 = g.day(besoin_l=12.0)
    assert j2.watered is False
    assert j2.cumulative == pytest.approx(-6.0)

    j3 = g.day(besoin_l=12.0)
    assert j3.interval_reached is True
    assert j3.watered is True
    assert j3.volume == pytest.approx(6.0), "−6 réserve + 12 besoin = 6 L"
    assert j3.cumulative == pytest.approx(0.0)


# ===========================================================================
# Scénario E — Pluie partielle un jour de besoin (bilan signé partiel)
# Intervalle large (7 j) pour isoler l'accumulation, sans arrosage.
# ===========================================================================

def test_scenario_e_partial_rain_signed_balance():
    """Déficit partiel (+12), surplus qui grignote la dette (−6), jour neutre (0)."""
    g = _Garden(interval_days=7)

    j1 = g.day(besoin_l=30.0, pluie_eff_l=18.0)
    assert j1.balance == pytest.approx(12.0)
    assert j1.watered is False
    assert j1.cumulative == pytest.approx(12.0)

    j2 = g.day(besoin_l=30.0, pluie_eff_l=36.0)
    assert j2.balance == pytest.approx(-6.0)
    assert j2.watered is False
    assert j2.cumulative == pytest.approx(6.0)

    j3 = g.day(besoin_l=30.0, pluie_eff_l=30.0)
    assert j3.balance == pytest.approx(0.0)
    assert j3.watered is False
    assert j3.cumulative == pytest.approx(6.0)


# ===========================================================================
# Invariant transverse — un jour d'arrosage ramène toujours le cumulé à 0
# ===========================================================================

def test_invariant_watering_day_ends_at_zero():
    """Quelle que soit la dette/réserve, dès qu'un arrosage est émis le cumulé finit à 0."""
    for debt in (-50.0, -5.0, 0.0, 5.0, 50.0):
        g = _Garden(interval_days=1)
        g.set_initial_debt(debt)
        d = g.day(besoin_l=30.0, pluie_eff_l=0.0)
        if d.watered:
            assert d.cumulative == pytest.approx(0.0)
        else:
            # Aucun arrosage uniquement si la réserve couvre le besoin du jour.
            assert debt + 30.0 <= 0
