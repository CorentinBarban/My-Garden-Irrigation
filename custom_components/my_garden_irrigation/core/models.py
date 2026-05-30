"""Dataclasses de domaine — My Garden Irrigation.

Aucune dépendance externe : ce fichier peut être importé dans n'importe
quel contexte (tests, scripts, future CLI…).
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Résultats de calcul
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CropResult:
    """Besoin en eau calculé pour une culture à un instant donné."""

    liters: float
    """Litres/jour pour cette culture."""

    surface_m2: float
    """Surface occupée en m² (nb_plants ÷ densité)."""

    kc: float
    """Coefficient cultural Kc utilisé."""

    eto_mm: float
    """ETo source utilisée (mm/j)."""

    liters_per_plant: float
    """Litres/jour par plant."""

    weekly_projection_l: float
    """Projection hebdomadaire (litres × 7)."""

    # Métadonnées de la culture — utiles pour les attributs HA
    crop_type: str
    stage: str
    nb_plants: int
    density: float


@dataclass(frozen=True)
class IrrigationData:
    """Snapshot de tous les calculs pour un potager."""

    crops: dict[str, CropResult] = field(default_factory=dict)
    """crop_id → CropResult pour chaque culture configurée."""

    total_liters: float = 0.0
    """Somme de toutes les cultures (litres/jour)."""

    eto_mm: float = 0.0
    """ETo du jour utilisée pour tous les calculs (mm/j)."""


# ---------------------------------------------------------------------------
# Entrées pour le calcul ETo
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EToInput:
    """Données météorologiques nécessaires au calcul ETo Penman-Monteith (FAO-56).

    Toutes les valeurs représentent les conditions journalières.
    """

    t_min: float
    """Température minimale journalière (°C)."""

    t_max: float
    """Température maximale journalière (°C)."""

    humidity_min: float
    """Humidité relative minimale journalière (%, 0–100)."""

    humidity_max: float
    """Humidité relative maximale journalière (%, 0–100)."""

    wind_speed_2m: float
    """Vitesse du vent à 2 m de hauteur (m/s)."""

    sunshine_hours: float
    """Durée d'insolation journalière (heures)."""

    latitude: float
    """Latitude en degrés décimaux (positif = Nord)."""

    altitude: float
    """Altitude en mètres au-dessus du niveau de la mer."""

    @property
    def t_mean(self) -> float:
        return (self.t_min + self.t_max) / 2
