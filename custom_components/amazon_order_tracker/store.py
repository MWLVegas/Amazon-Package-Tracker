"""Local order storage."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import ACTIVE_STATUSES, STATUS_ARCHIVED, STATUS_DELIVERED
from .parser import ParsedOrder

STORAGE_VERSION = 1


class OrderStore:
    """Persist parsed order state in Home Assistant storage."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"amazon_order_tracker.{entry_id}"
        )
        self.orders: dict[str, dict[str, Any]] = {}

    async def async_load(self) -> None:
        """Load stored orders."""
        data = await self._store.async_load()
        self.orders = dict(data.get("orders", {})) if data else {}

    async def async_save(self) -> None:
        """Save stored orders."""
        await self._store.async_save({"orders": self.orders})

    async def async_merge_updates(
        self, updates: list[ParsedOrder], archive_after: timedelta
    ) -> None:
        """Merge parsed email updates into local order state."""
        now = datetime.now().astimezone()
        for update in updates:
            existing = self.orders.get(update.order_id, {})
            seen_messages = set(existing.get("seen_messages", []))
            if update.message_id in seen_messages:
                continue

            seen_messages.add(update.message_id)
            record = {
                **existing,
                **_serializable_update(update),
                "seen_messages": sorted(seen_messages),
                "last_subject": update.subject,
                "last_updated": _serialize_datetime(update.updated_at) or now.isoformat(),
            }
            if "created_at" not in record:
                record["created_at"] = _serialize_datetime(update.updated_at) or now.isoformat()
            if update.status == STATUS_DELIVERED and "delivered_at" not in record:
                record["delivered_at"] = _serialize_datetime(update.updated_at) or now.isoformat()
            self.orders[update.order_id] = record

        self._archive_delivered(now, archive_after)
        await self.async_save()

    def counts(self) -> dict[str, int]:
        """Return counts grouped by source and status."""
        counts: dict[str, int] = {
            "amazon_active": 0,
            "pharmacy_active": 0,
            "active": 0,
        }
        for order in self.orders.values():
            status = order.get("status")
            source = order.get("source", "amazon")
            if status not in ACTIVE_STATUSES:
                continue
            counts["active"] += 1
            counts[f"{source}_active"] = counts.get(f"{source}_active", 0) + 1
            counts[status] = counts.get(status, 0) + 1
            counts[f"{source}_{status}"] = counts.get(f"{source}_{status}", 0) + 1
        return counts

    def active_orders(self) -> list[dict[str, Any]]:
        """Return active order records."""
        return [
            {"order_id": order_id, **order}
            for order_id, order in sorted(self.orders.items())
            if order.get("status") in ACTIVE_STATUSES
        ]

    def _archive_delivered(self, now: datetime, archive_after: timedelta) -> None:
        for order in self.orders.values():
            if order.get("status") != STATUS_DELIVERED:
                continue
            delivered_at = _parse_datetime(order.get("delivered_at"))
            if delivered_at is not None and now - delivered_at >= archive_after:
                order["status"] = STATUS_ARCHIVED
                order["archived_at"] = now.isoformat()


def _serializable_update(update: ParsedOrder) -> dict[str, Any]:
    data = asdict(update)
    data.pop("message_id")
    data.pop("subject")
    data["updated_at"] = _serialize_datetime(update.updated_at)
    return data


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.astimezone().isoformat()
    return value.isoformat()


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.astimezone()
    return parsed
