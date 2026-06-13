"""Local order storage."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    ACTIVE_STATUSES,
    DEFAULT_STALE_ACTIVE_DAYS,
    STATUS_ARCHIVED,
    STATUS_CANCELLED,
    STATUS_DELIVERED,
    STATUS_RANK,
)
from .parser import ParsedOrderEvent

STORAGE_VERSION = 1


class OrderStore:
    """Persist parsed order state in Home Assistant storage."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"amazon_order_tracker.{entry_id}"
        )
        self.orders: dict[str, dict[str, Any]] = {}
        self.last_successful_scan_at: str | None = None

    async def async_load(self) -> None:
        """Load stored orders."""
        data = await self._store.async_load()
        self.orders = dict(data.get("orders", {})) if data else {}
        self.last_successful_scan_at = (
            data.get("last_successful_scan_at") if data else None
        )

    async def async_save(self) -> None:
        """Save stored orders."""
        await self._store.async_save(
            {
                "orders": self.orders,
                "last_successful_scan_at": self.last_successful_scan_at,
            }
        )

    async def async_merge_updates(
        self,
        updates: list[ParsedOrderEvent],
        archive_after: timedelta,
        successful_scan_at: datetime | None = None,
    ) -> dict[str, int]:
        """Merge parsed email updates into local order state."""
        now = datetime.now().astimezone()
        previous_scan_at = self.last_successful_scan_at
        added_or_updated = 0
        diagnostic_updates = 0
        for update in sorted(updates, key=_update_sort_key):
            existing = self.orders.get(update.order_id, {})
            seen_messages = set(existing.get("seen_messages", []))
            was_seen = update.message_id in seen_messages

            seen_messages.add(update.message_id)
            record = self._merge_update(existing, update, now)
            if record is None:
                continue
            record["seen_messages"] = sorted(seen_messages)
            if update.diagnostic_reason:
                diagnostic_updates += 1
            elif not was_seen:
                added_or_updated += 1
            if "created_at" not in record:
                record["created_at"] = _serialize_datetime(update.updated_at) or now.isoformat()
            self.orders[update.order_id] = record

        archived_now = self._archive_delivered(now, archive_after)
        stale_archived_now = self._archive_stale_active(now)
        if successful_scan_at is not None:
            self.set_last_successful_scan(successful_scan_at)
        try:
            await self.async_save()
        except Exception:
            self.last_successful_scan_at = previous_scan_at
            raise
        return {
            "records_changed": added_or_updated,
            "records_archived": archived_now,
            "records_stale_archived": stale_archived_now,
            "diagnostic_updates": diagnostic_updates,
        }

    def _merge_update(
        self,
        existing: dict[str, Any],
        update: ParsedOrderEvent,
        now: datetime,
    ) -> dict[str, Any] | None:
        update_data = _serializable_update(update)
        update_time = _serialize_datetime(update.updated_at) or now.isoformat()

        if update.diagnostic_reason:
            if not existing:
                return None
            diagnostics = list(existing.get("diagnostics", []))
            diagnostics.append(
                {
                    "message_id": update.message_id,
                    "subject": update.subject,
                    "event_type": update.event_type,
                    "reason": update.diagnostic_reason,
                    "updated_at": update_time,
                }
            )
            return {
                **existing,
                "diagnostics": diagnostics[-10:],
                "last_subject": update.subject,
                "last_updated": max(existing.get("last_updated", ""), update_time),
            }

        if existing.get("status") == STATUS_ARCHIVED:
            return {
                **existing,
                "last_subject": update.subject,
                "last_updated": max(existing.get("last_updated", ""), update_time),
            }

        existing_status = str(existing.get("status") or "")
        existing_rank = STATUS_RANK.get(existing_status, 0)
        update_rank = STATUS_RANK.get(update.status, 0)

        should_promote = update_rank >= existing_rank
        if existing_status == STATUS_DELIVERED and update.status != STATUS_DELIVERED:
            should_promote = False
        elif existing_status == STATUS_CANCELLED and update.status != STATUS_DELIVERED:
            should_promote = False
        elif not should_promote:
            existing_time = _parse_datetime(existing.get("last_updated"))
            parsed_update_time = _parse_datetime(update_time)
            should_promote = (
                existing_time is None
                or parsed_update_time is None
                or parsed_update_time > existing_time
            )

        if not should_promote:
            return {
                **existing,
                "last_subject": update.subject,
                "last_updated": max(existing.get("last_updated", ""), update_time),
            }

        record = {
            **existing,
            **update_data,
            "last_subject": update.subject,
            "last_updated": update_time,
        }
        if existing and update.origin and update.origin.endswith("_without_order_created"):
            if "origin" in existing:
                record["origin"] = existing["origin"]
            else:
                record.pop("origin", None)
        if update.status == STATUS_DELIVERED:
            record["delivered_at"] = update_time
        if update.status == STATUS_CANCELLED:
            record["cancelled_at"] = update_time
        return record

    def set_last_successful_scan(self, value: datetime) -> None:
        """Persist the last completed scan timestamp."""
        self.last_successful_scan_at = _serialize_datetime(value)

    def counts(self) -> dict[str, int]:
        """Return counts grouped by source and status."""
        counts: dict[str, int] = {
            "amazon_active": 0,
            "pharmacy_active": 0,
            "active": 0,
            "archived": 0,
            "cancelled": 0,
            "stored": len(self.orders),
        }
        for order in self.orders.values():
            status = order.get("status")
            source = order.get("source", "amazon")
            if status == STATUS_ARCHIVED:
                counts["archived"] += 1
                counts[f"{source}_archived"] = counts.get(f"{source}_archived", 0) + 1
                continue
            if status == STATUS_CANCELLED:
                counts["cancelled"] += 1
                counts[f"{source}_cancelled"] = counts.get(f"{source}_cancelled", 0) + 1
                continue
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

    def _archive_delivered(self, now: datetime, archive_after: timedelta) -> int:
        archived_now = 0
        for order in self.orders.values():
            if order.get("status") != STATUS_DELIVERED:
                continue
            delivered_at = _parse_datetime(order.get("delivered_at"))
            if delivered_at is not None and now - delivered_at >= archive_after:
                order["status"] = STATUS_ARCHIVED
                order["archived_at"] = now.isoformat()
                archived_now += 1
        return archived_now

    def _archive_stale_active(self, now: datetime) -> int:
        archived_now = 0
        stale_after = timedelta(days=DEFAULT_STALE_ACTIVE_DAYS)
        for order in self.orders.values():
            if order.get("status") not in ACTIVE_STATUSES:
                continue
            if order.get("status") == STATUS_DELIVERED:
                continue
            last_updated = _parse_datetime(order.get("last_updated"))
            if last_updated is not None and now - last_updated >= stale_after:
                order["status"] = STATUS_ARCHIVED
                order["archived_at"] = now.isoformat()
                order["archive_reason"] = "stale_active"
                archived_now += 1
        return archived_now


def _serializable_update(update: ParsedOrderEvent) -> dict[str, Any]:
    data = asdict(update)
    data.pop("message_id")
    data.pop("subject")
    data.pop("diagnostic_reason")
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


def _update_sort_key(update: ParsedOrderEvent) -> tuple[datetime, int]:
    updated_at = update.updated_at
    if updated_at is None:
        updated_at = datetime.min
    elif updated_at.tzinfo is not None:
        updated_at = updated_at.replace(tzinfo=None)
    return (updated_at, STATUS_RANK.get(update.status, 0))
