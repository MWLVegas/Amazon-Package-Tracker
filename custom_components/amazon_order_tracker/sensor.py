"""Sensors for Amazon Order Tracker."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    STATUS_ARCHIVED,
    STATUS_CANCELLED,
    STATUS_DELAYED,
    STATUS_DELIVERED,
    STATUS_LABELS,
    STATUS_OUT_FOR_DELIVERY,
    STATUS_PENDING,
    STATUS_SHIPPED,
)
from .coordinator import AmazonOrderTrackerCoordinator


@dataclass(frozen=True, kw_only=True)
class AmazonOrderSensorDescription(SensorEntityDescription):
    """Description for an order count sensor."""

    count_key: str


SENSORS: tuple[AmazonOrderSensorDescription, ...] = (
    AmazonOrderSensorDescription(
        key="active_orders",
        translation_key="active_orders",
        name="Active Orders",
        count_key="active",
    ),
    AmazonOrderSensorDescription(
        key="pending_shipping",
        name=STATUS_LABELS[STATUS_PENDING],
        count_key=STATUS_PENDING,
    ),
    AmazonOrderSensorDescription(
        key="shipped",
        name=STATUS_LABELS[STATUS_SHIPPED],
        count_key=STATUS_SHIPPED,
    ),
    AmazonOrderSensorDescription(
        key="out_for_delivery",
        name=STATUS_LABELS[STATUS_OUT_FOR_DELIVERY],
        count_key=STATUS_OUT_FOR_DELIVERY,
    ),
    AmazonOrderSensorDescription(
        key="delivered",
        name=STATUS_LABELS[STATUS_DELIVERED],
        count_key=STATUS_DELIVERED,
    ),
    AmazonOrderSensorDescription(
        key="delayed",
        name=STATUS_LABELS[STATUS_DELAYED],
        count_key=STATUS_DELAYED,
    ),
    AmazonOrderSensorDescription(
        key="cancelled",
        name=STATUS_LABELS[STATUS_CANCELLED],
        count_key=STATUS_CANCELLED,
    ),
    AmazonOrderSensorDescription(
        key="pharmacy_active",
        name="Pharmacy Active Orders",
        count_key="pharmacy_active",
    ),
    AmazonOrderSensorDescription(
        key="archived_orders",
        name=STATUS_LABELS[STATUS_ARCHIVED],
        count_key="archived",
    ),
    AmazonOrderSensorDescription(
        key="stored_orders",
        name="Stored Orders",
        count_key="stored",
    ),
    AmazonOrderSensorDescription(
        key="emails_scanned",
        name="Emails Scanned Last Scan",
        count_key="emails_scanned",
    ),
    AmazonOrderSensorDescription(
        key="updates_parsed",
        name="Updates Parsed Last Scan",
        count_key="updates_parsed",
    ),
    AmazonOrderSensorDescription(
        key="records_archived",
        name="Archived Last Scan",
        count_key="records_archived",
    ),
    AmazonOrderSensorDescription(
        key="records_stale_archived",
        name="Stale Archived Last Scan",
        count_key="records_stale_archived",
    ),
    AmazonOrderSensorDescription(
        key="ordered_messages_found",
        name="Ordered Messages Found",
        count_key="ordered_messages_found",
    ),
    AmazonOrderSensorDescription(
        key="delivered_messages_found",
        name="Delivered Messages Found",
        count_key="delivered_messages_found",
    ),
    AmazonOrderSensorDescription(
        key="problem_messages_found",
        name="Problem Messages Found",
        count_key="problem_messages_found",
    ),
    AmazonOrderSensorDescription(
        key="shipped_messages_found",
        name="Shipped Messages Found",
        count_key="shipped_messages_found",
    ),
    AmazonOrderSensorDescription(
        key="unknown_order_messages_found",
        name="Unknown Order Messages Found",
        count_key="unknown_order_messages_found",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors."""
    coordinator: AmazonOrderTrackerCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        AmazonOrderCountSensor(coordinator, entry, description)
        for description in SENSORS
    )


class AmazonOrderCountSensor(
    CoordinatorEntity[AmazonOrderTrackerCoordinator], SensorEntity
):
    """Order count sensor."""

    entity_description: AmazonOrderSensorDescription

    def __init__(
        self,
        coordinator: AmazonOrderTrackerCoordinator,
        entry: ConfigEntry,
        description: AmazonOrderSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Personal",
        }

    @property
    def native_value(self) -> int:
        """Return sensor value."""
        counts = self.coordinator.data.get("counts", {}) if self.coordinator.data else {}
        return int(counts.get(self.entity_description.count_key, 0))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose useful details on diagnostic sensors."""
        if not self.coordinator.data:
            return {}
        if self.entity_description.key != "active_orders":
            if self.entity_description.key in {
                "emails_scanned",
                "updates_parsed",
                "records_archived",
                "records_stale_archived",
                "ordered_messages_found",
                "delivered_messages_found",
                "problem_messages_found",
                "shipped_messages_found",
                "unknown_order_messages_found",
            }:
                return {"last_scan": self.coordinator.data.get("last_scan", {})}
            return {}
        return {"orders": self.coordinator.data.get("orders", [])}
