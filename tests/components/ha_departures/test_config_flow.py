"""Tests for the config flow of the integration."""

from unittest.mock import AsyncMock, patch

from apyefa import Line, Location
from apyefa.exceptions import EfaConnectionError, EfaResponseInvalid
import pytest

from homeassistant.components.ha_departures.const import (
    CONF_ENDPOINT,
    CONF_ERROR_CONNECTION_FAILED,
    CONF_ERROR_INVALID_RESPONSE,
    CONF_ERROR_NO_STOP_FOUND,
    CONF_HUB_NAME,
    CONF_LINES,
    CONF_STOP_NAME,
    DOMAIN,
    EFA_ENDPOINTS,
)
from homeassistant.components.ha_departures.helper import line_hash
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import (
    MOCK_LINES,
    MOCK_LOCATION_A,
    add_mock_config_entry,
    mock_efa_client,
)


#####################################
#         ConfigFlow tests          #
#####################################
async def test_config_flow_success(hass: HomeAssistant) -> None:
    """Test the entire config flow."""

    stop = Location.from_dict(MOCK_LOCATION_A)
    line = Line.from_dict(MOCK_LINES[0])
    hub_name = "My hub"

    assert stop, "Mock stop invalid!"
    assert line, "Mock line invalid!"

    with patch(
        "homeassistant.components.ha_departures.config_flow.EfaClient",
        return_value=mock_efa_client(
            stops=[stop],
            lines=[line],
        ),
    ):
        # STEP 1: user
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
        )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "user"

        # STEP 2: submit endpoint + stop name
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_ENDPOINT: EFA_ENDPOINTS["General EFA"],
                CONF_STOP_NAME: stop.name,
            },
        )

        assert result["step_id"] == "stop"

        # STEP 3: choose a stop
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_STOP_NAME: stop.id,
            },
        )

        assert result["step_id"] == "lines"

        # STEP 4: choose lines
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_LINES: [line_hash(line)],
            },
        )

        assert result["step_id"] == "hubname"

        # STEP 5: choose hub name
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HUB_NAME: hub_name,
            },
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == hub_name

        # check data
        assert result["data"]["stop_id"] == stop.id
        assert result["data"]["api_url"] == EFA_ENDPOINTS["General EFA"]

        # check lines (options)
        assert len(result["options"][CONF_LINES]) == 1
        assert result["options"][CONF_LINES][0]["id"] == line.id


async def test_config_flow_init(hass: HomeAssistant) -> None:
    """Test the first step of the config flow."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_config_flow_step_user_no_stop_found(hass: HomeAssistant) -> None:
    """Test the first step of the config flow."""
    with patch(
        "homeassistant.components.ha_departures.config_flow.EfaClient",
        return_value=mock_efa_client(stops=[]),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "endpoint": EFA_ENDPOINTS["General EFA"],
                "stop_name": "Unknown",
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": CONF_ERROR_NO_STOP_FOUND}


@pytest.mark.parametrize(
    ("exception", "expected_error"),
    [
        (EfaConnectionError("fail"), CONF_ERROR_CONNECTION_FAILED),
        (EfaResponseInvalid("bad"), CONF_ERROR_INVALID_RESPONSE),
    ],
)
async def test_config_flow_step_user_connection_error(
    hass: HomeAssistant, exception, expected_error
) -> None:
    """Test behavior of the flow by client exceptions."""

    efa = AsyncMock()
    efa.__aenter__.side_effect = exception

    with patch(
        "homeassistant.components.ha_departures.config_flow.EfaClient",
        return_value=efa,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "endpoint": EFA_ENDPOINTS["General EFA"],
                "stop_name": "Test",
            },
        )

    assert result["errors"] == {"base": expected_error}


async def test_config_flow_step_user_invalid_response(hass: HomeAssistant) -> None:
    """Test the first step of the config flow."""
    efa = AsyncMock()
    efa.__aenter__.side_effect = EfaResponseInvalid("bad answer")

    with patch(
        "homeassistant.components.ha_departures.config_flow.EfaClient",
        return_value=efa,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "endpoint": EFA_ENDPOINTS["General EFA"],
                "stop_name": "Test",
            },
        )

    assert result["errors"] == {"base": CONF_ERROR_INVALID_RESPONSE}


async def test_abort_duplicate_unique_id(hass: HomeAssistant) -> None:
    """Test that duplicate hub_name aborts the flow."""

    stop = Location.from_dict(MOCK_LOCATION_A)
    line = Line.from_dict(MOCK_LINES[0])
    hub_name = "My hub"

    # 1. Create first flow
    with patch(
        "homeassistant.components.ha_departures.config_flow.EfaClient",
        return_value=mock_efa_client(
            stops=[stop],
            lines=[line],
        ),
    ):
        # STEP 1: user
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
        )

        # STEP 2: submit endpoint + stop name
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_ENDPOINT: EFA_ENDPOINTS["General EFA"],
                CONF_STOP_NAME: stop.name,
            },
        )

        # STEP 3: choose a stop
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_STOP_NAME: stop.id,
            },
        )

        # STEP 4: choose lines
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_LINES: [line_hash(line)],
            },
        )

        # STEP 5: choose hub name
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HUB_NAME: hub_name,
            },
        )

        # 2. Create second flow (same hub_name)

        # STEP 1: user
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
        )

        # STEP 2: submit endpoint + stop name
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_ENDPOINT: EFA_ENDPOINTS["General EFA"],
                CONF_STOP_NAME: stop.name,
            },
        )

        # STEP 3: choose a stop
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_STOP_NAME: stop.id,
            },
        )

        # STEP 4: choose lines
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_LINES: [line_hash(line)],
            },
        )

        # STEP 5: choose hub name
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HUB_NAME: hub_name,
            },
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


#####################################
#         OptionsFlow tests         #
#####################################
async def test_options_abort_no_changes(hass: HomeAssistant) -> None:
    """Test that options flow aborts when no changes are made."""

    line = Line.from_dict(MOCK_LINES[0])

    entry = add_mock_config_entry(hass, lines=[MOCK_LINES[0]])

    # Start options flow
    with patch(
        "homeassistant.components.ha_departures.config_flow.EfaClient",
        return_value=mock_efa_client(
            stops=[],
            lines=[line],
        ),
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "init"

        # Submit same data, that entry had
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_LINES: [str(hash(line))],
            },
        )

        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "no_changes_configured"


async def test_options_add_a_new_line(hass: HomeAssistant) -> None:
    """Test that two new lines can be added via the options flow."""
    line_1 = Line.from_dict(MOCK_LINES[0])
    line_2 = Line.from_dict(MOCK_LINES[1])

    entry = add_mock_config_entry(hass, lines=[MOCK_LINES[0]])

    # Start options flow
    with patch(
        "homeassistant.components.ha_departures.config_flow.EfaClient",
        return_value=mock_efa_client(
            stops=[],
            lines=[line_1, line_2],
        ),
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "init"

        # Submit new selected lines
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_LINES: [str(hash(line_1)), str(hash(line_2))],
            },
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY

        updated_entry = hass.config_entries.async_get_entry(entry.entry_id)

        assert updated_entry.options["lines"] == [
            line_1.to_dict(),
            line_2.to_dict(),
        ]


async def test_options_remove_all_line(hass: HomeAssistant) -> None:
    """Test that all lines can be removed via the options flow."""
    line_1 = Line.from_dict(MOCK_LINES[0])
    line_2 = Line.from_dict(MOCK_LINES[1])

    entry = add_mock_config_entry(hass, lines=[MOCK_LINES[0], MOCK_LINES[1]])

    # Start options flow
    with patch(
        "homeassistant.components.ha_departures.config_flow.EfaClient",
        return_value=mock_efa_client(
            stops=[],
            lines=[line_1, line_2],
        ),
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "init"

        # Submit data with line removed
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_LINES: [],
            },
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        updated_entry = hass.config_entries.async_get_entry(entry.entry_id)

        assert len(updated_entry.options[CONF_LINES]) == 0


async def test_options_remove_a_line(hass: HomeAssistant) -> None:
    """Test that a line can be removed via the options flow."""
    line_1 = Line.from_dict(MOCK_LINES[0])
    line_2 = Line.from_dict(MOCK_LINES[1])

    entry = add_mock_config_entry(hass, lines=[MOCK_LINES[0], MOCK_LINES[1]])

    # Start options flow
    with patch(
        "homeassistant.components.ha_departures.config_flow.EfaClient",
        return_value=mock_efa_client(
            stops=[],
            lines=[line_1, line_2],
        ),
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "init"

        # Submit data with line removed
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_LINES: [str(hash(line_1))],
            },
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        updated_entry = hass.config_entries.async_get_entry(entry.entry_id)

        assert updated_entry.options[CONF_LINES] == [line_1.to_dict()]
