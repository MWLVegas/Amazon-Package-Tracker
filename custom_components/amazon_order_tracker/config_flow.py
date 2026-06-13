"""Config flow for Amazon Order Tracker."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_ARCHIVE_AFTER_HOURS,
    CONF_IMAP_PORT,
    CONF_IMAP_SERVER,
    CONF_INCLUDE_PHARMACY,
    CONF_LOOKBACK_DAYS,
    CONF_MAILBOX,
    CONF_PASSWORD,
    CONF_RESET_SCAN_FROM,
    CONF_USERNAME,
    DEFAULT_ARCHIVE_AFTER_HOURS,
    DEFAULT_IMAP_PORT,
    DEFAULT_IMAP_SERVER,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_MAILBOX,
    DOMAIN,
)
from .mail import ImapSettings, test_imap_login


class AmazonOrderTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Amazon Order Tracker."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        suggested_values = dict(user_input or {})

        if user_input is not None:
            settings = ImapSettings(
                server=user_input[CONF_IMAP_SERVER],
                port=user_input[CONF_IMAP_PORT],
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                mailbox=user_input[CONF_MAILBOX],
            )
            result = await self.hass.async_add_executor_job(test_imap_login, settings)
            if result.success:
                await self.async_set_unique_id(user_input[CONF_USERNAME])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME) or user_input[CONF_USERNAME],
                    data=user_input,
                )
            errors["base"] = result.error or "cannot_connect"

        schema = _schema_with_defaults(suggested_values)
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return AmazonOrderTrackerOptionsFlow(config_entry)


class AmazonOrderTrackerOptionsFlow(config_entries.OptionsFlow):
    """Handle Amazon Order Tracker options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage integration options."""
        errors: dict[str, str] = {}
        options = dict(self.config_entry.options)

        if user_input is not None:
            reset_scan_from = str(user_input.get(CONF_RESET_SCAN_FROM, "")).strip()
            if reset_scan_from and not _valid_date(reset_scan_from):
                errors[CONF_RESET_SCAN_FROM] = "invalid_date"
            else:
                if reset_scan_from:
                    options[CONF_RESET_SCAN_FROM] = reset_scan_from
                else:
                    options.pop(CONF_RESET_SCAN_FROM, None)
                return self.async_create_entry(title="", data=options)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_RESET_SCAN_FROM,
                        default=options.get(CONF_RESET_SCAN_FROM, ""),
                    ): str,
                }
            ),
            errors=errors,
        )


def _schema_with_defaults(values: dict[str, Any]) -> vol.Schema:
    """Build the setup form, preserving values after validation errors."""
    return vol.Schema(
        {
            vol.Optional(CONF_NAME, default=values.get(CONF_NAME, "Amazon Orders")): str,
            vol.Required(CONF_USERNAME, default=values.get(CONF_USERNAME, "")): str,
            vol.Required(CONF_PASSWORD, default=values.get(CONF_PASSWORD, "")): str,
            vol.Optional(
                CONF_IMAP_SERVER,
                default=values.get(CONF_IMAP_SERVER, DEFAULT_IMAP_SERVER),
            ): str,
            vol.Optional(
                CONF_IMAP_PORT,
                default=values.get(CONF_IMAP_PORT, DEFAULT_IMAP_PORT),
            ): int,
            vol.Optional(
                CONF_MAILBOX,
                default=values.get(CONF_MAILBOX, DEFAULT_MAILBOX),
            ): str,
            vol.Optional(
                CONF_LOOKBACK_DAYS,
                default=values.get(CONF_LOOKBACK_DAYS, DEFAULT_LOOKBACK_DAYS),
            ): vol.All(int, vol.Range(min=1, max=365)),
            vol.Optional(
                CONF_ARCHIVE_AFTER_HOURS,
                default=values.get(
                    CONF_ARCHIVE_AFTER_HOURS, DEFAULT_ARCHIVE_AFTER_HOURS
                ),
            ): vol.All(int, vol.Range(min=1, max=720)),
            vol.Optional(
                CONF_INCLUDE_PHARMACY,
                default=values.get(CONF_INCLUDE_PHARMACY, True),
            ): bool,
        }
    )


def _valid_date(value: str) -> bool:
    """Return whether a value is a YYYY-MM-DD date."""
    try:
        from datetime import date

        date.fromisoformat(value)
    except ValueError:
        return False
    return True
