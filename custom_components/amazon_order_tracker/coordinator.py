"""Data update coordinator for Amazon Order Tracker."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_RESET_SCAN_FROM,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .mail import SCAN_PASSES, ImapSettings, fetch_messages_by_pass
from .parser import ParsedOrderEvent, parse_message_event, parse_unknown_order_event
from .settings import get_entry_settings
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
            "last_successful_scan_at": None,
            "scan_start_at": None,
            "scan_since": None,
            "scan_from": None,
            "used_checkpoint": False,
            "reset_checkpoint_last_run": None,
            "rebuild_last_run": None,
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
        await self.store.async_load()
        entry_settings = get_entry_settings(self.entry)

        settings = ImapSettings(
            server=entry_settings["imap_server"],
            port=entry_settings["imap_port"],
            username=entry_settings["username"],
            password=entry_settings["password"],
            mailbox=entry_settings["mailbox"],
        )
        include_pharmacy = entry_settings["include_pharmacy"]
        archive_after = timedelta(hours=entry_settings["archive_after_hours"])
        scan_from, used_checkpoint = self._scan_from(entry_settings)
        scan_start_at = datetime.now().astimezone()

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
            updates,
            archive_after,
            entry_settings["stale_active_days"],
            successful_scan_at,
        )
        if self.entry.options.get(CONF_RESET_SCAN_FROM):
            self._clear_reset_scan_from_option()
        self.last_scan = {
            "emails_scanned": len(
                {message.message_id for messages in messages_by_pass.values() for message in messages}
            ),
            "updates_parsed": len(updates),
            "scan_start_at": scan_start_at.isoformat(),
            "scan_since": scan_from.isoformat(),
            "scan_from": scan_from.isoformat(),
            "used_checkpoint": used_checkpoint,
            "last_successful_scan_at": successful_scan_at.isoformat(),
            "reset_checkpoint_last_run": self.store.reset_checkpoint_last_run,
            "rebuild_last_run": self.store.rebuild_last_run,
            "unknown_order_samples": unknown_order_samples,
            **pass_counts,
            **merge_stats,
        }

        return self._stored_data()

    async def async_reset_scan_checkpoint(self) -> None:
        """Clear the stored scan checkpoint and refresh coordinator data."""
        await self.store.async_load()
        await self.store.async_reset_checkpoint()
        self.last_scan = {
            **self.last_scan,
            "last_successful_scan_at": None,
            "reset_checkpoint_last_run": self.store.reset_checkpoint_last_run,
        }
        self.async_set_updated_data(self._stored_data())
        await self.async_request_refresh()

    async def async_rebuild_order_state(self) -> None:
        """Clear stored order state and refresh coordinator data."""
        await self.store.async_load()
        await self.store.async_rebuild()
        self.last_scan = {
            **self.last_scan,
            "last_successful_scan_at": None,
            "rebuild_last_run": self.store.rebuild_last_run,
        }
        self.async_set_updated_data(self._stored_data())
        await self.async_request_refresh()

    def _scan_from(self, entry_settings: dict[str, Any]) -> tuple[datetime, bool]:
        """Return the timestamp to use for the next mailbox scan."""
        reset_scan_from = self.entry.options.get(CONF_RESET_SCAN_FROM)
        if reset_scan_from:
            try:
                return datetime.fromisoformat(str(reset_scan_from)).astimezone(), False
            except ValueError:
                LOGGER.warning("Ignoring invalid reset scan date: %s", reset_scan_from)

        last_successful_scan = self.store.last_successful_scan_at
        if last_successful_scan:
            try:
                parsed = datetime.fromisoformat(last_successful_scan)
            except ValueError:
                parsed = None
            if parsed is not None:
                return (
                    parsed - timedelta(hours=entry_settings["scan_overlap_hours"]),
                    True,
                )
        return (
            datetime.now().astimezone()
            - timedelta(days=entry_settings["lookback_days"]),
            False,
        )

    def _clear_reset_scan_from_option(self) -> None:
        """Clear one-shot reset scan date after a successful scan."""
        options = dict(self.entry.options)
        options.pop(CONF_RESET_SCAN_FROM, None)
        self.hass.config_entries.async_update_entry(self.entry, options=options)

    def _stored_data(self) -> dict[str, object]:
        """Return current stored data in coordinator format."""
        counts = self.store.counts()
        self.last_scan["last_successful_scan_at"] = self.store.last_successful_scan_at
        self.last_scan["reset_checkpoint_last_run"] = self.store.reset_checkpoint_last_run
        self.last_scan["rebuild_last_run"] = self.store.rebuild_last_run
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
