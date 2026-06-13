"""Data update coordinator for Amazon Order Tracker."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

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
    CONF_RESET_SCAN_FROM,
    CONF_USERNAME,
    DEFAULT_ARCHIVE_AFTER_HOURS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SCAN_OVERLAP_HOURS,
    DOMAIN,
)
from .mail import SCAN_PASSES, ImapSettings, fetch_messages_by_pass
from .parser import ParsedOrderEvent, parse_message_event, parse_unknown_order_event
from .store import OrderStore

LOGGER = logging.getLogger(__name__)


class AmazonOrderTrackerCoordinator(DataUpdateCoordinator[dict[str, object]]):
    """Fetch email updates and maintain order state."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.store = OrderStore(hass, entry.entry_id)
        self.last_scan: dict[str, Any] = {
            "emails_scanned": 0,
            "ordered_messages_found": 0,
            "delivered_messages_found": 0,
            "problem_messages_found": 0,
            "shipped_messages_found": 0,
            "unknown_order_messages_found": 0,
            "updates_parsed": 0,
            "records_changed": 0,
            "records_archived": 0,
            "records_stale_archived": 0,
        }
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )

    async def async_load_stored_data(self) -> None:
        """Load persisted orders before the first email scan completes."""
        await self.store.async_load()
        self.async_set_updated_data(self._stored_data())

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
        scan_from = self._scan_from(lookback_days)

        try:
            messages_by_pass = await self.hass.async_add_executor_job(
                fetch_messages_by_pass, settings, scan_from
            )
        except Exception as err:
            raise UpdateFailed(f"Could not fetch Gmail messages: {err}") from err

        updates: list[ParsedOrderEvent] = []
        processed_messages: set[str] = set()
        unknown_order_samples: list[dict[str, Any]] = []
        pass_counts = {
            f"{pass_name}_messages_found": len(messages_by_pass.get(pass_name, []))
            for pass_name in SCAN_PASSES
        }
        pass_counts["unknown_order_messages_found"] = 0

        for pass_name in SCAN_PASSES:
            for message in messages_by_pass.get(pass_name, []):
                if message.message_id in processed_messages:
                    continue
                if pass_name == "unknown":
                    parsed = parse_unknown_order_event(message)
                else:
                    parsed = parse_message_event(message, pass_name, include_pharmacy)
                if parsed is None:
                    continue
                if pass_name == "unknown":
                    pass_counts["unknown_order_messages_found"] += 1
                    if parsed.order_id not in self.store.orders:
                        unknown_order_samples = _append_unknown_sample(
                            unknown_order_samples, parsed
                        )
                updates.append(parsed)
                processed_messages.add(message.message_id)

        successful_scan_at = datetime.now().astimezone()
        merge_stats = await self.store.async_merge_updates(
            updates, archive_after, successful_scan_at
        )
        if self.entry.options.get(CONF_RESET_SCAN_FROM):
            self._clear_reset_scan_from_option()
        self.last_scan = {
            "emails_scanned": len(
                {message.message_id for messages in messages_by_pass.values() for message in messages}
            ),
            "updates_parsed": len(updates),
            "scan_from": scan_from.isoformat(),
            "last_successful_scan_at": successful_scan_at.isoformat(),
            "unknown_order_samples": unknown_order_samples,
            **pass_counts,
            **merge_stats,
        }

        return self._stored_data()

    def _scan_from(self, lookback_days: int) -> datetime:
        """Return the timestamp to use for the next mailbox scan."""
        reset_scan_from = self.entry.options.get(CONF_RESET_SCAN_FROM)
        if reset_scan_from:
            try:
                return datetime.fromisoformat(str(reset_scan_from)).astimezone()
            except ValueError:
                LOGGER.warning("Ignoring invalid reset scan date: %s", reset_scan_from)

        last_successful_scan = self.store.last_successful_scan_at
        if last_successful_scan:
            try:
                parsed = datetime.fromisoformat(last_successful_scan)
            except ValueError:
                parsed = None
            if parsed is not None:
                return parsed - timedelta(hours=DEFAULT_SCAN_OVERLAP_HOURS)
        return datetime.now().astimezone() - timedelta(days=lookback_days)

    def _clear_reset_scan_from_option(self) -> None:
        """Clear one-shot reset scan date after a successful scan."""
        options = dict(self.entry.options)
        options.pop(CONF_RESET_SCAN_FROM, None)
        self.hass.config_entries.async_update_entry(self.entry, options=options)

    def _stored_data(self) -> dict[str, object]:
        """Return current stored data in coordinator format."""
        counts = self.store.counts()
        counts.update(self.last_scan)
        return {
            "counts": counts,
            "orders": self.store.active_orders(),
            "last_scan": self.last_scan,
        }


def _append_unknown_sample(
    samples: list[dict[str, Any]], event: ParsedOrderEvent
) -> list[dict[str, Any]]:
    """Append a limited unknown sample for diagnostics."""
    samples.append(
        {
            "subject": event.subject[:160],
            "order_id": event.order_id,
            "date": event.updated_at.isoformat() if event.updated_at else None,
            "reason": event.diagnostic_reason,
        }
    )
    return samples[-5:]
