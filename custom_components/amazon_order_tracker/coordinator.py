"""Data update coordinator for Amazon Order Tracker."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

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
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .mail import ImapSettings, fetch_candidate_messages
from .parser import parse_message
from .store import OrderStore

LOGGER = logging.getLogger(__name__)


class AmazonOrderTrackerCoordinator(DataUpdateCoordinator[dict[str, object]]):
    """Fetch email updates and maintain order state."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.store = OrderStore(hass, entry.entry_id)
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )

    async def _async_update_data(self) -> dict[str, object]:
        data = self.entry.data
        await self.store.async_load()

        settings = ImapSettings(
            server=data[CONF_IMAP_SERVER],
            port=data[CONF_IMAP_PORT],
            username=data[CONF_USERNAME],
            password=data[CONF_PASSWORD],
            mailbox=data[CONF_MAILBOX],
        )
        lookback_days = data[CONF_LOOKBACK_DAYS]
        include_pharmacy = data.get(CONF_INCLUDE_PHARMACY, True)
        archive_after = timedelta(
            hours=data.get(CONF_ARCHIVE_AFTER_HOURS, DEFAULT_ARCHIVE_AFTER_HOURS)
        )

        try:
            messages = await self.hass.async_add_executor_job(
                fetch_candidate_messages, settings, lookback_days
            )
        except Exception as err:
            raise UpdateFailed(f"Could not fetch Gmail messages: {err}") from err

        updates = [
            parsed
            for message in messages
            if (parsed := parse_message(message, include_pharmacy)) is not None
        ]
        await self.store.async_merge_updates(updates, archive_after)

        return {
            "counts": self.store.counts(),
            "orders": self.store.active_orders(),
        }
