"""Config Flow et Options Flow — My Garden Irrigation.

Config Flow (installation) :
  step_user  → nom du potager

Options Flow (post-installation) :
  step_init        → menu principal (ajouter / supprimer une culture)
  step_add_crop    → formulaire d'ajout d'une culture
  step_remove_crop → sélection de la culture à supprimer
"""
from __future__ import annotations

import uuid
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CROP_ID,
    CONF_CROP_NAME,
    CONF_CROP_TYPE,
    CONF_CROPS,
    CONF_DENSITY,
    CONF_GLOBAL_FLOW_RATE,
    CONF_GLOBAL_VALVE_ENTITY_ID,
    CONF_IRRIGATION_TIME,
    CONF_NAME,
    CONF_NB_PLANTS,
    CONF_STAGE,
    CONF_WATERING_FREQUENCY,
    CONF_WATERING_INTERVAL_DAYS,
    CONF_WATERING_MODE,
    DEFAULT_IRRIGATION_TIME,
    DOMAIN,
    FAO_DEFAULT_DENSITIES,
    STAGE_MID,
    STAGES,
    SUPPORTED_CROPS,
    WATERING_FREQUENCIES,
    WATERING_FREQUENCY_DAILY,
    WATERING_MODE_CONTINUOUS,
    WATERING_MODES,
)


class MyGardenIrrigationConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config Flow — installation initiale de l'intégration."""

    VERSION = 2

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            if not name:
                errors[CONF_NAME] = "invalid_name"
            else:
                await self.async_set_unique_id(name.lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=name,
                    data={CONF_NAME: name},
                    options={CONF_CROPS: []},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_NAME): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return IrrigationOptionsFlowHandler(config_entry)


class IrrigationOptionsFlowHandler(OptionsFlow):
    """Options Flow — gestion post-installation des cultures et de la vanne globale."""

    def __init__(self, entry: ConfigEntry) -> None:
        self._crops: list[dict] = list(entry.options.get(CONF_CROPS, []))
        self._valve_entity_id: str | None = entry.options.get(CONF_GLOBAL_VALVE_ENTITY_ID)
        self._flow_rate: float = entry.options.get(CONF_GLOBAL_FLOW_RATE, 0.0)
        self._watering_frequency: str = entry.options.get(CONF_WATERING_FREQUENCY, WATERING_FREQUENCY_DAILY)
        self._watering_interval_days: int = entry.options.get(CONF_WATERING_INTERVAL_DAYS, 2)
        self._watering_mode: str = entry.options.get(CONF_WATERING_MODE, WATERING_MODE_CONTINUOUS)
        self._irrigation_time: str = entry.options.get(CONF_IRRIGATION_TIME, DEFAULT_IRRIGATION_TIME)

    # ------------------------------------------------------------------
    # Menu principal
    # ------------------------------------------------------------------

    async def async_step_init(
        self, user_input: dict | None = None  # noqa: ARG002
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=["add_crop", "remove_crop", "valve_config", "watering_config", "auto_irrigation"],
        )

    # ------------------------------------------------------------------
    # Ajouter une culture
    # ------------------------------------------------------------------

    async def async_step_add_crop(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            crop_type = user_input[CONF_CROP_TYPE]
            self._crops.append(
                {
                    CONF_CROP_ID: str(uuid.uuid4()),
                    CONF_CROP_NAME: user_input[CONF_CROP_NAME].strip(),
                    CONF_CROP_TYPE: crop_type,
                    CONF_STAGE: user_input[CONF_STAGE],
                    CONF_NB_PLANTS: int(user_input[CONF_NB_PLANTS]),
                    CONF_DENSITY: float(user_input[CONF_DENSITY]),
                }
            )
            return self._save()

        return self.async_show_form(
            step_id="add_crop",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CROP_NAME): str,
                    vol.Required(CONF_CROP_TYPE): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=SUPPORTED_CROPS,
                            translation_key="crop_type",
                        )
                    ),
                    vol.Required(CONF_STAGE, default=STAGE_MID): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=STAGES,
                            translation_key="stage",
                        )
                    ),
                    vol.Required(CONF_NB_PLANTS): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1, max=100, step=1, mode="box"
                        )
                    ),
                    vol.Required(CONF_DENSITY): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.1, max=1_000, step=0.1, mode="box"
                        )
                    ),
                }
            ),
            description_placeholders={
                "fao_densities": ", ".join(
                    f"{c}: {d}" for c, d in FAO_DEFAULT_DENSITIES.items()
                )
            },
        )

    # ------------------------------------------------------------------
    # Configurer la vanne globale (ADR-009)
    # ------------------------------------------------------------------

    async def async_step_valve_config(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._valve_entity_id = user_input.get(CONF_GLOBAL_VALVE_ENTITY_ID) or None
            self._flow_rate = float(user_input.get(CONF_GLOBAL_FLOW_RATE) or 0.0)
            return self._save()

        suggested: dict[str, Any] = {}
        if self._valve_entity_id:
            suggested[CONF_GLOBAL_VALVE_ENTITY_ID] = self._valve_entity_id
        if self._flow_rate:
            suggested[CONF_GLOBAL_FLOW_RATE] = self._flow_rate

        schema = vol.Schema(
            {
                vol.Optional(CONF_GLOBAL_VALVE_ENTITY_ID): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["valve", "switch"])
                ),
                vol.Optional(CONF_GLOBAL_FLOW_RATE): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=10_000, step=0.1, mode="box", unit_of_measurement="L/h"
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="valve_config",
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
        )

    # ------------------------------------------------------------------
    # Supprimer une culture
    # ------------------------------------------------------------------

    async def async_step_remove_crop(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        if not self._crops:
            return self.async_abort(reason="no_crops")

        if user_input is not None:
            crop_id_to_remove = user_input[CONF_CROP_ID]
            self._crops = [
                c for c in self._crops if c[CONF_CROP_ID] != crop_id_to_remove
            ]
            return self._save()

        crop_options = [
            {
                "value": c[CONF_CROP_ID],
                "label": (
                    f"{c.get(CONF_CROP_NAME, c[CONF_CROP_TYPE].capitalize())} "
                    f"({c[CONF_CROP_TYPE]}) "
                    f"— {c[CONF_NB_PLANTS]} plant(s)"
                ),
            }
            for c in self._crops
        ]
        return self.async_show_form(
            step_id="remove_crop",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CROP_ID): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=crop_options)
                    ),
                }
            ),
        )

    # ------------------------------------------------------------------
    # Configurer la fréquence et le mode d'arrosage (ADR-010)
    # ------------------------------------------------------------------

    async def async_step_watering_config(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._watering_frequency = user_input[CONF_WATERING_FREQUENCY]
            self._watering_mode = user_input[CONF_WATERING_MODE]
            interval = user_input.get(CONF_WATERING_INTERVAL_DAYS)
            if interval is not None:
                self._watering_interval_days = int(interval)
            return self._save()

        suggested: dict[str, Any] = {
            CONF_WATERING_FREQUENCY: self._watering_frequency,
            CONF_WATERING_MODE: self._watering_mode,
            CONF_WATERING_INTERVAL_DAYS: self._watering_interval_days,
        }
        schema = vol.Schema(
            {
                vol.Required(CONF_WATERING_FREQUENCY): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=WATERING_FREQUENCIES,
                        translation_key="watering_frequency",
                    )
                ),
                vol.Optional(CONF_WATERING_INTERVAL_DAYS): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1, max=30, step=1, mode="box", unit_of_measurement="jours"
                    )
                ),
                vol.Required(CONF_WATERING_MODE): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=WATERING_MODES,
                        translation_key="watering_mode",
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="watering_config",
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
        )

    # ------------------------------------------------------------------
    # Heure d'arrosage automatique
    # ------------------------------------------------------------------

    async def async_step_auto_irrigation(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._irrigation_time = user_input.get(CONF_IRRIGATION_TIME, DEFAULT_IRRIGATION_TIME)
            return self._save()

        suggested: dict[str, Any] = {CONF_IRRIGATION_TIME: self._irrigation_time}
        schema = vol.Schema(
            {
                vol.Required(CONF_IRRIGATION_TIME): selector.TimeSelector(),
            }
        )
        return self.async_show_form(
            step_id="auto_irrigation",
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
        )

    # ------------------------------------------------------------------
    # Persistance
    # ------------------------------------------------------------------

    def _save(self) -> ConfigFlowResult:
        """Enregistre toutes les options et déclenche le rechargement de l'entrée."""
        data: dict[str, Any] = {CONF_CROPS: self._crops}
        if self._valve_entity_id:
            data[CONF_GLOBAL_VALVE_ENTITY_ID] = self._valve_entity_id
        if self._flow_rate > 0:
            data[CONF_GLOBAL_FLOW_RATE] = self._flow_rate
        data[CONF_WATERING_FREQUENCY] = self._watering_frequency
        data[CONF_WATERING_MODE] = self._watering_mode
        if self._watering_frequency == WATERING_FREQUENCY_DAILY:
            data[CONF_WATERING_INTERVAL_DAYS] = 1
        else:
            data[CONF_WATERING_INTERVAL_DAYS] = self._watering_interval_days
        data[CONF_IRRIGATION_TIME] = self._irrigation_time
        return self.async_create_entry(data=data)
