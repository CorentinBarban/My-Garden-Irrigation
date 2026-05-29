"""Logique métier de My Garden Irrigation — sans dépendance Home Assistant.

Ce package est volontairement isolé de HA pour permettre :
- des tests unitaires rapides (pytest standard, sans hass fixture)
- une réutilisabilité hors HA si besoin

Modules :
  models       — dataclasses de domaine (CropResult, IrrigationData, EToInput…)
  kc_data      — accès aux coefficients culturaux Kc (FAO Paper 56)
  calculations — formules FAO ETc = Kc × ETo × surface
  eto          — calcul ETo via PyETo (Penman-Monteith, Hargreaves-Samani)
"""
