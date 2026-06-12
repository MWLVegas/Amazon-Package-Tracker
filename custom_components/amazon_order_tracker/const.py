"""Constants for Amazon Order Tracker."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "amazon_order_tracker"

CONF_IMAP_SERVER = "imap_server"
CONF_IMAP_PORT = "imap_port"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_MAILBOX = "mailbox"
CONF_LOOKBACK_DAYS = "lookback_days"
CONF_ARCHIVE_AFTER_HOURS = "archive_after_hours"
CONF_INCLUDE_PHARMACY = "include_pharmacy"

DEFAULT_IMAP_SERVER = "imap.gmail.com"
DEFAULT_IMAP_PORT = 993
DEFAULT_MAILBOX = "INBOX"
DEFAULT_LOOKBACK_DAYS = 45
DEFAULT_ARCHIVE_AFTER_HOURS = 48
DEFAULT_SCAN_INTERVAL = timedelta(minutes=30)

STATUS_PENDING = "pending_shipping"
STATUS_SHIPPED = "shipped"
STATUS_OUT_FOR_DELIVERY = "out_for_delivery"
STATUS_DELIVERED = "delivered"
STATUS_DELAYED = "delayed"
STATUS_ARCHIVED = "archived"

ACTIVE_STATUSES = {
    STATUS_PENDING,
    STATUS_SHIPPED,
    STATUS_OUT_FOR_DELIVERY,
    STATUS_DELIVERED,
    STATUS_DELAYED,
}

STATUS_LABELS = {
    STATUS_PENDING: "Pending shipping",
    STATUS_SHIPPED: "Shipped",
    STATUS_OUT_FOR_DELIVERY: "Out for delivery",
    STATUS_DELIVERED: "Delivered",
    STATUS_DELAYED: "Delayed",
    STATUS_ARCHIVED: "Archived",
}
