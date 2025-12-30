"""__ini__.py tests."""

from unittest.mock import patch

from homeassistant.components.ha_departures.const import (
    CONF_API_URL,
    CONF_HUB_NAME,
    CONF_STOP_COORD,
    CONF_STOP_ID,
    CONF_STOP_NAME,
    DOMAIN,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from .test_config_flow import mock_efa_client

from tests.common import MockConfigEntry


async def test_setup_entry(hass: HomeAssistant) -> None:
    """Test setup entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_API_URL: "http://test.com",
            CONF_STOP_ID: "stop_id",
            CONF_STOP_NAME: "stop_name",
            CONF_STOP_COORD: [1.0, 2.0],
            CONF_HUB_NAME: "test_hub_name",
        },
        options={},
    )
    entry.add_to_hass(hass)

    with patch(
        "homeassistant.components.ha_departures.coordinator.EfaClient",
        return_value=mock_efa_client(),
    ):
        assert await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED
        assert entry.runtime_data is not None


async def test_unload_entry(hass: HomeAssistant) -> None:
    """Test unload entry."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
