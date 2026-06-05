"""État de configuration mutable — My Garden Irrigation.

Classe Python pure (aucun import homeassistant.* à l'exécution), testable avec
pytest sans Home Assistant. Porte l'état runtime : config globale, bilan hydrique
cumulé (ADR-008), état de la vanne et de l'arrosage automatique.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING

from .const import (
    CONF_CROP_ID,
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
    DEFAULT_CYCLES_COUNT,
    DEFAULT_IRRIGATION_TIME,
    DEFAULT_SOAK_DURATION_MINUTES,
    MAX_REASONABLE_SURFACE_M2,
)
from .core.calculations import compute_surface_m2

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)

_RUNTIME_CONFIG_KEYS = (
    CONF_GLOBAL_FLOW_RATE,
    CONF_WATERING_INTERVAL_DAYS,
    CONF_WATERING_FREQUENCY,
    CONF_WATERING_MODE,
    CONF_IRRIGATION_TIME,
    CONF_CYCLES_COUNT,
    CONF_SOAK_DURATION,
)

# Champs par culture pilotables par l'utilisateur via l'UI (number/select).
# Persistés dans le Store HA (plus de RestoreEntity) et restaurés au boot.
_CROP_OVERRIDE_FIELDS = (CONF_NB_PLANTS, CONF_DENSITY, CONF_STAGE)


def _crops_snapshot(options: dict) -> dict:
    """Snapshot des champs pilotables par culture, tel que défini par le formulaire."""
    return {
        crop[CONF_CROP_ID]: {f: crop.get(f) for f in _CROP_OVERRIDE_FIELDS}
        for crop in options.get(CONF_CROPS, [])
        if CONF_CROP_ID in crop
    }


def _options_hash(options: dict) -> str:
    """Hash stable des clés de config (globale + valeurs par culture du formulaire).

    Sert à détecter une re-soumission du formulaire entre deux sauvegardes runtime :
    si le hash stocké diffère du hash courant, les overrides persistés (globaux et
    par culture) sont ignorés et entry.options fait autorité.
    """
    relevant = {k: options.get(k) for k in _RUNTIME_CONFIG_KEYS}
    relevant["crops"] = _crops_snapshot(options)
    return hashlib.md5(
        json.dumps(relevant, sort_keys=True, default=str).encode()
    ).hexdigest()


class RuntimeConfigState:
    """État de config mutable et bilan hydrique du coordinateur.

    Aucune dépendance homeassistant à l'exécution — 100 % testable hors HA.
    Les setters sont synchrones et sans effet de bord : la persistance et les
    callbacks HA sont gérés par IrrigationCoordinator.
    """

    def __init__(self, options: dict) -> None:
        self._options = options

        # Valeurs initiales lues depuis entry.options ; remplacées au chargement par
        # les overrides runtime si l'options_hash concorde.
        # Les cultures sont copiées : update_crop_field ne doit pas muter entry.options,
        # qui sert de snapshot stable pour le hash.
        self._crop_data: list[dict] = [
            dict(crop) for crop in options.get(CONF_CROPS, [])
        ]
        self._flow_rate: float = float(options.get(CONF_GLOBAL_FLOW_RATE, 0.0))
        self._watering_interval_days: int = int(
            options.get(CONF_WATERING_INTERVAL_DAYS, 2)
        )
        self._watering_frequency: str = options.get(CONF_WATERING_FREQUENCY, "daily")
        self._watering_mode: str = options.get(CONF_WATERING_MODE, "continuous")
        self._irrigation_time: str = options.get(
            CONF_IRRIGATION_TIME, DEFAULT_IRRIGATION_TIME
        )
        self._cycles_count: int = int(
            options.get(CONF_CYCLES_COUNT, DEFAULT_CYCLES_COUNT)
        )
        self._soak_duration_minutes: int = int(
            options.get(CONF_SOAK_DURATION, DEFAULT_SOAK_DURATION_MINUTES)
        )

        # Bilan hydrique cumulé par culture (ADR-008). Le suivi des arrosages du
        # jour est dérivé du journal de transactions (DailyWaterLedger, ADR-026).
        self._cumulative_need: dict[str, float] = {}

        # État arrosage automatique
        self._auto_enabled: bool = False
        self._last_auto_watering_date: str | None = None
        # Date cible du prochain arrosage en mode interval, posée lors d'un
        # ré-ancrage explicite (changement d'intervalle/fréquence). Persistée pour
        # survivre aux redémarrages ; effacée dès qu'un arrosage réel a lieu.
        self._next_watering_override: str | None = None

        # Temps d'ouverture de la vanne (persisté pour réconciliation au redémarrage)
        self._valve_open_time: datetime | None = None

        # Suivi de session fractionné (Cycle & Soak) — non persisté
        self._session_remaining_closes: int = 0

    @classmethod
    def from_entry(cls, entry: ConfigEntry) -> RuntimeConfigState:
        """Construit l'état depuis une ConfigEntry HA."""
        return cls(dict(entry.options))

    # ------------------------------------------------------------------
    # Sérialisation / désérialisation
    # ------------------------------------------------------------------

    def restore_from_storage(self, stored: dict, now_date_iso: str) -> None:
        """Restaure l'état depuis le Store HA.

        Les overrides runtime ne sont réappliqués que si l'options_hash stocké
        concorde avec celui d'entry.options ; sinon le formulaire fait autorité.
        """
        if not stored:
            return

        self._cumulative_need = stored.get("cumulative_need", {})
        self._auto_enabled = stored.get("auto_irrigation_enabled", False)
        self._last_auto_watering_date = stored.get("last_auto_watering_date")
        self._next_watering_override = stored.get("next_watering_override")

        valve_open_time_str: str | None = stored.get("valve_open_time")
        if valve_open_time_str:
            self._valve_open_time = datetime.fromisoformat(valve_open_time_str)

        runtime = stored.get("runtime_config", {})
        if runtime and runtime.get("options_hash") == _options_hash(self._options):
            if CONF_GLOBAL_FLOW_RATE in runtime:
                self._flow_rate = float(runtime[CONF_GLOBAL_FLOW_RATE])
            if CONF_WATERING_INTERVAL_DAYS in runtime:
                self._watering_interval_days = int(runtime[CONF_WATERING_INTERVAL_DAYS])
            if CONF_WATERING_FREQUENCY in runtime:
                self._watering_frequency = str(runtime[CONF_WATERING_FREQUENCY])
            if CONF_WATERING_MODE in runtime:
                self._watering_mode = str(runtime[CONF_WATERING_MODE])
            if CONF_IRRIGATION_TIME in runtime:
                self._irrigation_time = str(runtime[CONF_IRRIGATION_TIME])
            if CONF_CYCLES_COUNT in runtime:
                self._cycles_count = int(runtime[CONF_CYCLES_COUNT])
            if CONF_SOAK_DURATION in runtime:
                self._soak_duration_minutes = int(runtime[CONF_SOAK_DURATION])
            # Overrides par culture (nb_plants/densité/stade pilotés via l'UI),
            # soumis à la même garde options_hash que la config globale.
            self._restore_crop_overrides(stored.get("crop_overrides", {}))
            _LOGGER.debug("RuntimeConfigState : runtime config restauré depuis le Store.")

    def _restore_crop_overrides(self, overrides: dict) -> None:
        """Ré-applique les valeurs par culture persistées dans la copie mémoire."""
        for crop in self._crop_data:
            crop_override = overrides.get(crop.get(CONF_CROP_ID))
            if not crop_override:
                continue
            for field in _CROP_OVERRIDE_FIELDS:
                if field in crop_override:
                    crop[field] = crop_override[field]

    def to_storage(self, now_date_iso: str) -> dict:
        """Sérialise l'état complet pour le Store HA."""
        return {
            "cumulative_need": self._cumulative_need,
            "auto_irrigation_enabled": self._auto_enabled,
            "last_auto_watering_date": self._last_auto_watering_date,
            "next_watering_override": self._next_watering_override,
            "valve_open_time": (
                self._valve_open_time.isoformat() if self._valve_open_time else None
            ),
            "crop_overrides": {
                crop[CONF_CROP_ID]: {
                    f: crop[f] for f in _CROP_OVERRIDE_FIELDS if f in crop
                }
                for crop in self._crop_data
                if CONF_CROP_ID in crop
            },
            "runtime_config": {
                "options_hash": _options_hash(self._options),
                CONF_GLOBAL_FLOW_RATE: self._flow_rate,
                CONF_WATERING_INTERVAL_DAYS: self._watering_interval_days,
                CONF_WATERING_FREQUENCY: self._watering_frequency,
                CONF_WATERING_MODE: self._watering_mode,
                CONF_IRRIGATION_TIME: self._irrigation_time,
                CONF_CYCLES_COUNT: self._cycles_count,
                CONF_SOAK_DURATION: self._soak_duration_minutes,
            },
        }

    # ------------------------------------------------------------------
    # Propriétés — lecture
    # ------------------------------------------------------------------

    @property
    def crops(self) -> list[dict]:
        return self._crop_data

    @property
    def cumulative_need(self) -> dict[str, float]:
        return self._cumulative_need

    @property
    def auto_irrigation_enabled(self) -> bool:
        return self._auto_enabled

    @property
    def last_auto_watering_date(self) -> str | None:
        return self._last_auto_watering_date

    @property
    def next_watering_override(self) -> str | None:
        return self._next_watering_override

    @property
    def flow_rate(self) -> float:
        return self._flow_rate

    @property
    def watering_frequency(self) -> str:
        return self._watering_frequency

    @property
    def watering_interval_days(self) -> int:
        return self._watering_interval_days

    @property
    def watering_mode(self) -> str:
        return self._watering_mode

    @property
    def irrigation_time(self) -> str:
        return self._irrigation_time

    @property
    def cycles_count(self) -> int:
        return self._cycles_count

    @property
    def soak_duration_minutes(self) -> int:
        return self._soak_duration_minutes

    @property
    def valve_entity_id(self) -> str | None:
        return self._options.get(CONF_GLOBAL_VALVE_ENTITY_ID)

    # ------------------------------------------------------------------
    # Mutateurs — synchrones, sans effet de bord HA
    # ------------------------------------------------------------------

    def update_crop_field(self, crop_id: str, field: str, value: object) -> None:
        """Met à jour un champ d'une culture dans la copie en mémoire."""
        for crop in self._crop_data:
            if crop[CONF_CROP_ID] == crop_id:
                crop[field] = value
                return

    def get_crop_field(self, crop_id: str, field: str, default: object = None) -> object:
        """Lit un champ d'une culture depuis la copie en mémoire (source unique)."""
        for crop in self._crop_data:
            if crop[CONF_CROP_ID] == crop_id:
                return crop.get(field, default)
        return default

    def set_flow_rate(self, value: float) -> None:
        self._flow_rate = max(0.0, float(value))

    def set_watering_interval_days(self, value: int) -> None:
        self._watering_interval_days = max(1, int(value))

    def set_watering_frequency(self, value: str) -> None:
        self._watering_frequency = value

    def set_watering_mode(self, value: str) -> None:
        self._watering_mode = value

    def set_irrigation_time(self, value: str) -> None:
        self._irrigation_time = value

    def set_cycles_count(self, value: int) -> None:
        self._cycles_count = max(1, int(value))

    def set_soak_duration_minutes(self, value: int) -> None:
        self._soak_duration_minutes = max(0, int(value))

    def set_valve_open_time(self, time: datetime | None) -> None:
        self._valve_open_time = time

    def get_valve_open_time(self) -> datetime | None:
        return self._valve_open_time

    def begin_irrigation_session(self, cycles: int) -> None:
        """Démarre une session d'arrosage avec N fermetures attendues (Cycle & Soak ou simple)."""
        self._session_remaining_closes = max(1, cycles)

    def consume_session_close(self) -> bool:
        """Enregistre une fermeture de vanne. Retourne True si c'est la dernière de la session."""
        if self._session_remaining_closes <= 0:
            return True
        self._session_remaining_closes -= 1
        return self._session_remaining_closes == 0

    def set_auto_irrigation(self, enabled: bool, now_date_iso: str) -> None:
        self._auto_enabled = enabled
        if enabled and self._last_auto_watering_date is None:
            self._last_auto_watering_date = now_date_iso

    def update_last_watering_date(self, date_iso: str) -> None:
        self._last_auto_watering_date = date_iso
        # Un arrosage réel a eu lieu : le cycle régulier reprend la main, la cible
        # de ré-ancrage n'est plus pertinente.
        self._next_watering_override = None

    def set_next_watering_override(self, value: str | None) -> None:
        self._next_watering_override = value

    def scale_cumulative_need(self, crop_id: str, scale: float) -> None:
        """Multiplie le besoin cumulé d'une culture par un facteur d'échelle.

        Appelé quand la surface change (nb_plants ou densité) pour garder le bilan
        cohérent avec la nouvelle surface.
        """
        if crop_id in self._cumulative_need:
            self._cumulative_need[crop_id] = round(
                self._cumulative_need[crop_id] * scale, 3
            )

    # ------------------------------------------------------------------
    # Opérations bilan hydrique (pure Python, aucun I/O)
    # ------------------------------------------------------------------

    def apply_watering_volumes(self, volumes: dict[str, float]) -> None:
        """Soustrait du bilan cumulé signé les volumes distribués par culture (ADR-028).

        Sans plancher : un arrosage supérieur à la dette crée une réserve (cumulé
        négatif). C'est le seul point d'imputation de l'arrosage sur le cumulé — le
        journal de minuit l'exclut pour éviter un double comptage.
        """
        for crop_id in self._get_crop_ids():
            current = self._cumulative_need.get(crop_id, 0.0)
            distributed = volumes.get(crop_id, 0.0)
            self._cumulative_need[crop_id] = current - distributed

    def apply_midnight_result(self, new_cumulative: dict[str, float]) -> None:
        """Remplace le bilan cumulé par celui calculé à la clôture de minuit (ADR-023)."""
        self._cumulative_need = new_cumulative
        _LOGGER.debug(
            "RuntimeConfigState : accumulation minuit (orchestrateur) — bilan cumulé : %s",
            {k: round(v, 1) for k, v in self._cumulative_need.items()},
        )

    def reset_irrigation(self) -> None:
        """Remet le bilan hydrique cumulé à zéro (le journal du jour est purgé par le coordinator)."""
        self._cumulative_need = {}

    def init_missing_crops(self, daily_needs: dict[str, float]) -> bool:
        """Initialise le cumulé pour les cultures absentes du bilan.

        Couvre le premier démarrage (bilan vide) et l'ajout d'une nouvelle culture
        sur un système existant. Retourne True si au moins une entrée a été créée.
        """
        added = False
        for crop_id, need in daily_needs.items():
            if crop_id not in self._cumulative_need:
                self._cumulative_need[crop_id] = need
                added = True
        return added

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def get_crop_surfaces(self) -> dict[str, float]:
        """Calcule la surface (m²) de chaque culture depuis nb_plants et densité."""
        return {
            crop[CONF_CROP_ID]: compute_surface_m2(
                crop[CONF_NB_PLANTS], crop[CONF_DENSITY]
            )
            for crop in self._crop_data
        }

    def warn_unreasonable_surfaces(self) -> None:
        """Logue un avertissement si la surface calculée d'une culture est anormalement élevée."""
        for crop in self._crop_data:
            nb_plants = crop.get(CONF_NB_PLANTS, 0)
            density = crop.get(CONF_DENSITY, 1)
            if density > 0 and (nb_plants / density) > MAX_REASONABLE_SURFACE_M2:
                _LOGGER.warning(
                    "Surface calculée (%s m²) anormalement élevée pour '%s' — "
                    "vérifiez nb_plants (%s) et densité (%s).",
                    round(nb_plants / density),
                    crop.get("crop_type"),
                    nb_plants,
                    density,
                )

    def cleanup_stale_crops(self) -> None:
        """Retire du bilan hydrique les cultures absentes des options actuelles.

        Appelé après restore_from_storage() quand une culture a été supprimée
        via le formulaire. Évite que des crop_ids fantômes persistent dans le Store.
        """
        current_ids = {crop[CONF_CROP_ID] for crop in self._crop_data}
        for stale_id in set(self._cumulative_need) - current_ids:
            del self._cumulative_need[stale_id]

    def _get_crop_ids(self) -> list[str]:
        return [crop[CONF_CROP_ID] for crop in self._crop_data]
