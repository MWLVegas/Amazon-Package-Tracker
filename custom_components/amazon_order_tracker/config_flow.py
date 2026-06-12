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

        if user_input is not None:
            settings = ImapSettings(
                server=user_input[CONF_IMAP_SERVER],
                port=user_input[CONF_IMAP_PORT],
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                mailbox=user_input[CONF_MAILBOX],
            )
            login_ok = await self.hass.async_add_executor_job(test_imap_login, settings)
            if login_ok:
                await self.async_set_unique_id(user_input[CONF_USERNAME])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME) or user_input[CONF_USERNAME],
                    data=user_input,
                )
            errors["base"] = "cannot_connect"

        schema = vol.Schema(
            {
                vol.Optional(CONF_NAME, default="Amazon Orders"): str,
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(CONF_IMAP_SERVER, default=DEFAULT_IMAP_SERVER): str,
                vol.Optional(CONF_IMAP_PORT, default=DEFAULT_IMAP_PORT): int,
                vol.Optional(CONF_MAILBOX, default=DEFAULT_MAILBOX): str,
                vol.Optional(
                    CONF_LOOKBACK_DAYS, default=DEFAULT_LOOKBACK_DAYS
                ): vol.All(int, vol.Range(min=1, max=365)),
                vol.Optional(
                    CONF_ARCHIVE_AFTER_HOURS,
                    default=DEFAULT_ARCHIVE_AFTER_HOURS,
                ): vol.All(int, vol.Range(min=1, max=720)),
                vol.Optional(CONF_INCLUDE_PHARMACY, default=True): bool,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )
