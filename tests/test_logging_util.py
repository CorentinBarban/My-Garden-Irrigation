"""Tests de la journalisation contextuelle (logging_util.py).

Fonctions pures — l'adaptateur fonctionne par duck-typing sur l'entrée
(attributs .title / .entry_id), aucune instance HA réelle n'est nécessaire.
"""
import logging
from types import SimpleNamespace

from custom_components.my_garden_irrigation.logging_util import (
    IrrigationLoggerAdapter,
    instance_logger,
)


def test_process_prefixes_message_with_garden_name():
    """process() préfixe le message avec le nom du jardin."""
    base = logging.getLogger("test.base")
    adapter = IrrigationLoggerAdapter(base, {"garden": "Potager Sud"})

    msg, kwargs = adapter.process("vanne ouverte", {})

    assert msg == "[Potager Sud] vanne ouverte"
    assert kwargs == {}


def test_instance_logger_uses_entry_title():
    """instance_logger privilégie le titre de l'entrée comme contexte."""
    entry = SimpleNamespace(title="Jardin Nord", entry_id="abcdef0123456789")
    adapter = instance_logger(logging.getLogger("test.coord"), entry)

    msg, _ = adapter.process("message", {})

    assert msg == "[Jardin Nord] message"


def test_instance_logger_falls_back_to_short_entry_id():
    """Sans titre, instance_logger se rabat sur les 8 premiers caractères de l'entry_id."""
    entry = SimpleNamespace(title="", entry_id="abcdef0123456789")
    adapter = instance_logger(logging.getLogger("test.coord"), entry)

    msg, _ = adapter.process("message", {})

    assert msg == "[abcdef01] message"


def test_adapter_derives_from_base_logger():
    """L'adaptateur conserve le logger hiérarchique sous-jacent (filtrage HA préservé)."""
    base = logging.getLogger("custom_components.my_garden_irrigation.coordinator")
    adapter = instance_logger(base, SimpleNamespace(title="X", entry_id="y"))

    assert adapter.logger is base
