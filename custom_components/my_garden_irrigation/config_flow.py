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
    CONF_NAME,
    CONF_NB_PLANTS,
    CONF_STAGE,
    DOMAIN,
    FAO_DEFAULT_DENSITIES,
    STAGE_MID,
    STAGES,
    SUPPORTED_CROPS,
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
    """Options Flow — gestion post-installation des cultures."""

    def __init__(self, entry: ConfigEntry) -> None:
        self._crops: list[dict] = list(entry.options.get(CONF_CROPS, []))

    # ------------------------------------------------------------------
    # Menu principal
    # ------------------------------------------------------------------

    async def async_step_init(
        self, user_input: dict | None = None  # noqa: ARG002
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=["add_crop", "remove_crop"],
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
    # Persistance
    # ------------------------------------------------------------------

    def _save(self) -> ConfigFlowResult:
        """Enregistre les options et déclenche le rechargement de l'entrée."""
        return self.async_create_entry(data={CONF_CROPS: self._crops})
