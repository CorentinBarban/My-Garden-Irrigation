"""Conversion d'un volume cible en plan d'arrosage (durée, cycles, soak).

Fonction pure, sans état ni dépendance homeassistant.* — testable directement
avec pytest. Source unique du calcul de durée, partagée par le coordinator
(émission de l'événement d'arrosage) et le sensor (durée recommandée affichée).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WateringPlan:
    """Plan d'arrosage dérivé d'un volume cible et du débit de la vanne."""

    target_volume_liters: float
    """Volume à distribuer (litres)."""

    duration_minutes: float
    """Durée totale d'ouverture de la vanne (minutes) ; 0 si volume ou débit nuls."""

    is_fractioned: bool
    """True en mode Cycle & Soak, False en arrosage continu."""

    cycles_count: int
    """Nombre de cycles d'ouverture (≥ 1)."""

    duration_per_cycle_minutes: float
    """Durée d'ouverture par cycle (minutes) = durée totale ÷ cycles."""

    soak_duration_minutes: int
    """Temps d'absorption entre deux cycles (minutes)."""


def compute_watering_plan(
    *,
    target_volume_liters: float,
    flow_rate_lph: float,
    is_fractioned: bool,
    cycles_count: int,
    soak_duration_minutes: int,
) -> WateringPlan:
    """Calcule la durée d'arrosage et sa répartition en cycles.

    Durée (min) = volume (L) ÷ débit (L/h) × 60, nulle si le volume ou le débit
    sont ≤ 0. La durée par cycle répartit la durée totale sur cycles_count cycles
    (ramené à 1 minimum). soak_duration_minutes est transporté tel quel.
    """
    if flow_rate_lph <= 0 or target_volume_liters <= 0:
        duration = 0.0
    else:
        duration = round((target_volume_liters / flow_rate_lph) * 60, 1)

    effective_cycles = max(1, cycles_count)
    return WateringPlan(
        target_volume_liters=round(target_volume_liters, 1),
        duration_minutes=duration,
        is_fractioned=is_fractioned,
        cycles_count=effective_cycles,
        duration_per_cycle_minutes=round(duration / effective_cycles, 1),
        soak_duration_minutes=soak_duration_minutes,
    )
