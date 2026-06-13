"""Amazon Order Tracker integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv

from .const import (
    ATTR_CONFIG_ENTRY,
    DOMAIN,
    SERVICE_REBUILD_ORDER_STATE,
    SERVICE_RESET_SCAN_CHECKPOINT,
)
from .coordinator import AmazonOrderTrackerCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]
SERVICE_SCHEMA = vol.Schema({vol.Required(ATTR_CONFIG_ENTRY): cv.string})


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up integration services."""

    async def async_reset_scan_checkpoint(call: ServiceCall) -> None:
        coordinator = _coordinator_from_service_call(hass, call)
        await coordinator.async_reset_scan_checkpoint()

    async def async_rebuild_order_state(call: ServiceCall) -> None:
        coordinator = _coordinator_from_service_call(hass, call)
        await coordinator.async_rebuild_order_state()

    hass.services.async_register(
        DOMAIN,
        SERVICE_RESET_SCAN_CHECKPOINT,
        async_reset_scan_checkpoint,
        schema=SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REBUILD_ORDER_STATE,
        async_rebuild_order_state,
        schema=SERVICE_SCHEMA,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Amazon Order Tracker from a config entry."""
    coordinator = AmazonOrderTrackerCoordinator(hass, entry)
    await coordinator.async_load_stored_data()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    entry.async_create_background_task(
        hass,
        coordinator.async_request_refresh(),
        "amazon_order_tracker_initial_refresh",
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _coordinator_from_service_call(
    hass: HomeAssistant, call: ServiceCall
) -> AmazonOrderTrackerCoordinator:
    """Return the coordinator targeted by a service call."""
    entry_id = call.data[ATTR_CONFIG_ENTRY]
    try:
        return hass.data[DOMAIN][entry_id]
    except KeyError as err:
        raise HomeAssistantError(
            "Amazon Order Tracker config entry is not loaded"
        ) from err
