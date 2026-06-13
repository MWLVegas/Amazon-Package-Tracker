"""Runtime settings helpers for Amazon Order Tracker."""

from __future__ import annotations

from typing import Any, TypedDict

from homeassistant.config_entries import ConfigEntry

from .const import (
    CONF_ARCHIVE_AFTER_HOURS,
    CONF_IMAP_PORT,
    CONF_IMAP_SERVER,
    CONF_INCLUDE_PHARMACY,
    CONF_LOOKBACK_DAYS,
    CONF_MAILBOX,
    CONF_PASSWORD,
    CONF_SCAN_OVERLAP_HOURS,
    CONF_STALE_ACTIVE_DAYS,
    CONF_USERNAME,
    DEFAULT_ARCHIVE_AFTER_HOURS,
    DEFAULT_IMAP_PORT,
    DEFAULT_IMAP_SERVER,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_MAILBOX,
    DEFAULT_SCAN_OVERLAP_HOURS,
    DEFAULT_STALE_ACTIVE_DAYS,
)


class EntrySettings(TypedDict):
    """Effective settings for one config entry."""

    imap_server: str
    imap_port: int
    username: str
    password: str
    mailbox: str
    lookback_days: int
    archive_after_hours: int
    include_pharmacy: bool
    scan_overlap_hours: int
    stale_active_days: int


def get_entry_settings(entry: ConfigEntry) -> EntrySettings:
    """Return effective settings with options overriding setup data."""
    values: dict[str, Any] = {
        **entry.data,
        **entry.options,
    }
    return {
        "imap_server": str(values.get(CONF_IMAP_SERVER, DEFAULT_IMAP_SERVER)),
        "imap_port": int(values.get(CONF_IMAP_PORT, DEFAULT_IMAP_PORT)),
        "username": str(values.get(CONF_USERNAME, "")),
        "password": str(values.get(CONF_PASSWORD, "")),
        "mailbox": str(values.get(CONF_MAILBOX, DEFAULT_MAILBOX)),
        "lookback_days": int(values.get(CONF_LOOKBACK_DAYS, DEFAULT_LOOKBACK_DAYS)),
        "archive_after_hours": int(
            values.get(CONF_ARCHIVE_AFTER_HOURS, DEFAULT_ARCHIVE_AFTER_HOURS)
        ),
        "include_pharmacy": bool(values.get(CONF_INCLUDE_PHARMACY, True)),
        "scan_overlap_hours": int(
            values.get(CONF_SCAN_OVERLAP_HOURS, DEFAULT_SCAN_OVERLAP_HOURS)
        ),
        "stale_active_days": int(
            values.get(CONF_STALE_ACTIVE_DAYS, DEFAULT_STALE_ACTIVE_DAYS)
        ),
    }
