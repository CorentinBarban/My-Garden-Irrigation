"""Accès aux coefficients culturaux Kc (FAO Paper 56).

Opère sur le dict brut chargé depuis kc_fao56.json.
Aucune dépendance I/O : le chargement du fichier est délégué à kc_loader.py (niveau HA).
"""
from __future__ import annotations


def get_kc(kc_data: dict, crop_type: str, stage: str) -> float | None:
    """Retourne le Kc pour une culture et un stade (ini / mid / end)."""
    crop = kc_data.get("crops", {}).get(crop_type)
    if crop is None:
        return None
    return crop.get(stage)


def get_default_density(kc_data: dict, crop_type: str) -> float | None:
    """Densité FAO par défaut (plants/m²) pour une culture."""
    crop = kc_data.get("crops", {}).get(crop_type)
    if crop is None:
        return None
    raw = crop.get("density_default")
    return float(raw) if raw else None


def list_crop_types(kc_data: dict) -> list[str]:
    """Liste des cultures disponibles dans les données Kc."""
    return list(kc_data.get("crops", {}).keys())


def is_valid_crop(kc_data: dict, crop_type: str) -> bool:
    return crop_type in kc_data.get("crops", {})
