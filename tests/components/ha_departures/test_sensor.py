"""Tests for the DeparturesSensor entity."""

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from apyefa import Departure, Line, TransportType
import pytest

from homeassistant.components.ha_departures.const import (
    ATTR_DIRECTION,
    ATTR_ESTIMATED_DEPARTURE_TIME,
    ATTR_LINE_ID,
    ATTR_LINE_NAME,
    ATTR_PLANNED_DEPARTURE_TIME,
    ATTR_PROVIDER_URL,
    ATTR_TIMES,
    ATTR_TRANSPORT_TYPE,
    CONF_API_URL,
    CONF_STOP_COORD,
    CONF_STOP_NAME,
)
from homeassistant.components.ha_departures.helper import (
    UnstableDepartureTime,
    replace_year_in_id,
)
from homeassistant.components.ha_departures.sensor import DeparturesSensor
from homeassistant.const import ATTR_LATITUDE, ATTR_LONGITUDE, Platform
from homeassistant.core import HomeAssistant

from .conftest import (
    ENTRY_TEST_DATA,
    MOCK_DEPARTURES_LINE_A,
    MOCK_DEPARTURES_LINE_B,
    MOCK_LINES,
    add_mock_config_entry,
    mock_efa_client,
)


def get_sensor_name(stop_name: str, line_name: str, destination_name: str):
    """Returns sensor name."""
    return f"{stop_name}-{line_name}-{destination_name}"


def get_sensor(hass: HomeAssistant, line: Line | dict) -> DeparturesSensor:
    """Return sensor instance."""

    if isinstance(line, dict):
        line_inst = Line.from_dict(line)
    else:
        line_inst = line

    assert line_inst, "Line object is invalid"

    sensor_name = f"{ENTRY_TEST_DATA[CONF_STOP_NAME]}-{line_inst.name}-{line_inst.destination.name}"

    return next(e for e in hass.data[Platform.SENSOR].entities if e.name == sensor_name)


#####################################
#     Sensor unit tests             #
#####################################
@pytest.mark.parametrize(
    ("transport_type", "expected_icon"),
    [
        (TransportType.CITY_BUS, "mdi:bus"),
        (TransportType.REGIONAL_BUS, "mdi:bus"),
        (TransportType.EXPRESS_BUS, "mdi:bus"),
        (TransportType.SUBWAY, "mdi:subway"),
        (TransportType.TRAM, "mdi:tram"),
        (TransportType.AST, "mdi:taxi"),
        (TransportType.SUBURBAN, "mdi:train"),
        (TransportType.TRAIN, "mdi:train"),
        (TransportType.CITY_RAIL, "mdi:train"),
        (TransportType.FERRY, "mdi:train-bus"),
    ],
)
def test_sensor_icon(mock_sensor, transport_type, expected_icon) -> None:
    """Test native_value and icon properties of DeparturesSensor."""
    mock_sensor._transport = transport_type

    # Test icon based on transport type
    assert mock_sensor.icon == expected_icon


def test_sensor_clear_times(mock_sensor) -> None:
    """Test clearing times in DeparturesSensor."""

    time_1 = Mock(spec=UnstableDepartureTime)
    time_2 = Mock(spec=UnstableDepartureTime)
    time_3 = Mock(spec=UnstableDepartureTime)

    # Simulate adding times
    mock_sensor._times = [
        time_1,
        time_2,
        time_3,
    ]
    mock_sensor._value = "Mock value"

    assert mock_sensor.native_value == "Mock value"

    # Clear times
    mock_sensor.clear_times()

    assert mock_sensor.native_value is None
    assert mock_sensor._attr_extra_state_attributes[ATTR_TIMES] == []

    assert time_1.clear.called
    assert time_2.clear.called
    assert time_3.clear.called


@pytest.mark.parametrize(("departure"), [(None), (1), ({"hello": "world"})])
def test_calculate_datetime_departure_is_invalid(mock_sensor, departure) -> None:
    """Tests that by an invalid departure argument, the function _calculate_datetime() returns None."""
    assert mock_sensor._calculate_datetime(departure) is None


def test_calculate_datetime_departure_is_not_none(mock_sensor) -> None:
    """Test that by a valid departure argument, the function _calculate_datetime() returns a valid datatime object."""
    departure = Departure.from_dict(MOCK_DEPARTURES_LINE_A[0])

    value = mock_sensor._calculate_datetime(departure)

    assert value is not None
    assert isinstance(value, datetime)


def test_update_times(mock_sensor) -> None:
    """Test that after update_times() call the _times member and attributes are updated accordingly."""
    departures = [Departure.from_dict(x) for x in MOCK_DEPARTURES_LINE_A]

    assert not mock_sensor._times
    assert not mock_sensor._attr_extra_state_attributes[ATTR_TIMES]

    mock_sensor._update_times(departures)

    assert mock_sensor._times
    assert mock_sensor._attr_extra_state_attributes[ATTR_TIMES]


#####################################
#     Sensor integration tests      #
#####################################
async def test_initial_sensor_state(hass: HomeAssistant) -> None:
    """Test initialization of DeparturesSensor."""

    line = Line.from_dict(MOCK_LINES[0])

    assert line, "Mock configuration invalid!"

    entry = add_mock_config_entry(hass, lines=[MOCK_LINES[0]])

    with patch(
        "homeassistant.components.ha_departures.coordinator.EfaClient",
        return_value=mock_efa_client(),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        sensor = get_sensor(hass, line)

        assert sensor.state is None
        assert sensor.coordinator
        assert sensor._attr_unique_id is not None
        assert sensor._attr_extra_state_attributes[ATTR_LINE_NAME] == line.name
        assert sensor._attr_extra_state_attributes[ATTR_LINE_ID] == replace_year_in_id(
            line.id, False
        )
        assert (
            sensor._attr_extra_state_attributes[ATTR_TRANSPORT_TYPE]
            == line.product.name
        )
        assert (
            sensor._attr_extra_state_attributes[ATTR_DIRECTION] == line.destination.name
        )
        assert (
            sensor._attr_extra_state_attributes[ATTR_PROVIDER_URL]
            == ENTRY_TEST_DATA[CONF_API_URL]
        )
        assert (
            sensor._attr_extra_state_attributes[ATTR_LATITUDE]
            == ENTRY_TEST_DATA[CONF_STOP_COORD][0]
        )
        assert (
            sensor._attr_extra_state_attributes[ATTR_LONGITUDE]
            == ENTRY_TEST_DATA[CONF_STOP_COORD][1]
        )
        assert sensor._attr_extra_state_attributes[ATTR_TIMES] == []


async def test_sensor_update_times_first_time(mock_sensor) -> None:
    """Test updating times in DeparturesSensor."""
    dep_1 = Mock(spec=Departure)
    dep_2 = Mock(spec=Departure)
    dep_3 = Mock(spec=Departure)

    dep_1.planned_time = datetime.now() + timedelta(minutes=5)
    dep_1.estimated_time = datetime.now() + timedelta(minutes=3)

    dep_2.planned_time = datetime.now() + timedelta(minutes=15)
    dep_2.estimated_time = None

    dep_3.planned_time = datetime.now() + timedelta(minutes=25)
    dep_3.estimated_time = datetime.now() + timedelta(minutes=20)

    mock_sensor._update_times([dep_1, dep_2, dep_3])

    assert len(mock_sensor._times) == 3
    assert mock_sensor._attr_extra_state_attributes[ATTR_TIMES] == [
        {
            ATTR_PLANNED_DEPARTURE_TIME: mock_sensor._times[0].planned_time,
            ATTR_ESTIMATED_DEPARTURE_TIME: mock_sensor._times[0].estimated_time,
        },
        {
            ATTR_PLANNED_DEPARTURE_TIME: mock_sensor._times[1].planned_time,
            ATTR_ESTIMATED_DEPARTURE_TIME: mock_sensor._times[1].estimated_time,
        },
        {
            ATTR_PLANNED_DEPARTURE_TIME: mock_sensor._times[2].planned_time,
            ATTR_ESTIMATED_DEPARTURE_TIME: mock_sensor._times[2].estimated_time,
        },
    ]


async def test_sensor_update_times_second_time(mock_sensor) -> None:
    """Test updating times in DeparturesSensor."""
    dep_1 = Mock(spec=Departure)
    dep_2 = Mock(spec=Departure)
    dep_3 = Mock(spec=Departure)

    dep_1.planned_time = datetime.now() + timedelta(minutes=5)
    dep_1.estimated_time = datetime.now() + timedelta(minutes=3)

    dep_2.planned_time = datetime.now() + timedelta(minutes=15)
    dep_2.estimated_time = None

    dep_3.planned_time = datetime.now() + timedelta(minutes=25)
    dep_3.estimated_time = datetime.now() + timedelta(minutes=20)

    mock_sensor._times = [UnstableDepartureTime(dep_1)]

    assert len(mock_sensor._times) == 1

    dep_1 = Mock(spec=Departure)
    dep_2 = Mock(spec=Departure)
    dep_3 = Mock(spec=Departure)

    dep_1.planned_time = datetime.now() + timedelta(minutes=15)
    dep_1.estimated_time = datetime.now() + timedelta(minutes=16)

    dep_2.planned_time = datetime.now() + timedelta(minutes=15)
    dep_2.estimated_time = None

    dep_3.planned_time = datetime.now() + timedelta(minutes=25)
    dep_3.estimated_time = datetime.now() + timedelta(minutes=20)

    mock_sensor._update_times([dep_1, dep_2, dep_3])

    assert len(mock_sensor._times) == 3
    assert mock_sensor._attr_extra_state_attributes[ATTR_TIMES] == [
        {
            ATTR_PLANNED_DEPARTURE_TIME: mock_sensor._times[0].planned_time,
            ATTR_ESTIMATED_DEPARTURE_TIME: mock_sensor._times[0].estimated_time,
        },
        {
            ATTR_PLANNED_DEPARTURE_TIME: mock_sensor._times[1].planned_time,
            ATTR_ESTIMATED_DEPARTURE_TIME: mock_sensor._times[1].estimated_time,
        },
        {
            ATTR_PLANNED_DEPARTURE_TIME: mock_sensor._times[2].planned_time,
            ATTR_ESTIMATED_DEPARTURE_TIME: mock_sensor._times[2].estimated_time,
        },
    ]


async def test_handle_coordinator_update_success(hass: HomeAssistant) -> None:
    """Test handling coordinator update in DeparturesSensor."""
    departures = [Departure.from_dict(x) for x in MOCK_DEPARTURES_LINE_A]

    entry = add_mock_config_entry(hass, lines=[MOCK_LINES[0]])

    efa_client = mock_efa_client(departures=departures)

    with patch(
        "homeassistant.components.ha_departures.coordinator.EfaClient",
        return_value=efa_client,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        sensor = get_sensor(hass, MOCK_LINES[0])

        assert sensor.native_value is None

        coordinator = entry.runtime_data.coordinator

        await coordinator.async_refresh()
        await hass.async_block_till_done()

        assert sensor.native_value


async def test_handle_coordinator_update_no_line_match(hass: HomeAssistant) -> None:
    """Test handling coordinator update in DeparturesSensor."""
    # Departures for line B should not match to sensor line (A)
    departures = [Departure.from_dict(x) for x in MOCK_DEPARTURES_LINE_B]

    entry = add_mock_config_entry(hass, lines=[MOCK_LINES[0]])

    efa_client = mock_efa_client(departures=departures)

    with patch(
        "homeassistant.components.ha_departures.coordinator.EfaClient",
        return_value=efa_client,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        sensor = get_sensor(hass, MOCK_LINES[0])

        assert sensor.native_value is None

        coordinator = entry.runtime_data.coordinator

        await coordinator.async_refresh()
        await hass.async_block_till_done()

        assert sensor.native_value is None
