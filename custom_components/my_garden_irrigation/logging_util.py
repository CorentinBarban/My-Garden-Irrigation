"""Journalisation contextuelle — My Garden Irrigation (ADR-027).

Le logging est une préoccupation transverse de la couche Home Assistant : le
paquet ``core/`` reste muet (testabilité pure, ADR-013) tandis que la couche HA
journalise. Ce module fournit l'adaptateur qui préfixe chaque message avec le
nom du jardin, afin de corréler les logs lorsque plusieurs instances coexistent.

L'adaptateur est construit une fois par le coordinateur puis injecté aux
sous-modules (ADR-012) : ces derniers ne fabriquent pas leur propre contexte.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry


class IrrigationLoggerAdapter(logging.LoggerAdapter):
    """Préfixe chaque message avec le nom du jardin pour la corrélation multi-instance.

    Dérive du logger hiérarchique du module appelant : le filtrage natif par
    ``logger:`` dans configuration.yaml reste opérationnel, le contexte d'instance
    est simplement ajouté par-dessus.
    """

    def process(self, msg: str, kwargs: dict) -> tuple[str, dict]:
        return f"[{self.extra['garden']}] {msg}", kwargs


def instance_logger(
    base: logging.Logger, entry: ConfigEntry
) -> IrrigationLoggerAdapter:
    """Construit un logger d'instance dérivé du logger hiérarchique du module appelant.

    Le préfixe utilise le titre de l'entrée (nom du jardin) ; à défaut, les huit
    premiers caractères de l'entry_id servent d'identifiant de repli.
    """
    garden = entry.title or entry.entry_id[:8]
    return IrrigationLoggerAdapter(base, {"garden": garden})
