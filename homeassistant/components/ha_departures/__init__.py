"""Custom integration to integrate Public Transport Departures with Home Assistant.

For more details about this integration, please refer to
https://github.com/alex-jung/ha-departures
"""

from dataclasses import dataclass
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import CONF_API_URL, CONF_STOP_ID, DOMAIN, STARTUP_MESSAGE
from .coordinator import DeparturesDataUpdateCoordinator

_LOGGER: logging.Logger = logging.getLogger(__package__)

PLATFORMS = [Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass
class RuntimeData:
    """Data class for runtime data."""

    coordinator: DeparturesDataUpdateCoordinator


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up this integration using YAML is not supported."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up this integration using UI."""

    _LOGGER.info(STARTUP_MESSAGE)

    url: str = entry.data.get(CONF_API_URL, "")
    stop_id: str = entry.data.get(CONF_STOP_ID, "")

    if not url:
        raise ConfigEntryNotReady("No endpoint API url configured")

    if not stop_id:
        raise ConfigEntryNotReady("No stop id configured")

    coordinator = DeparturesDataUpdateCoordinator(hass, url, stop_id, entry)

    await coordinator.async_config_entry_first_refresh()

    if not coordinator.last_update_success:
        raise ConfigEntryNotReady("Failed to get data from endpoint API")

    entry.runtime_data = RuntimeData(coordinator)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def _async_update_listener(hass: HomeAssistant, entry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload ha-departures config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old entry."""
    _LOGGER.debug(
        "Migrating configuration from version %s.%s",
        config_entry.version,
        config_entry.minor_version,
    )

    return True
