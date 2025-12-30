"""Tests conftest file for ha_departures integration."""

from unittest.mock import AsyncMock, Mock

from apyefa import Line
import pytest

from homeassistant.components.ha_departures.const import (
    CONF_API_URL,
    CONF_HUB_NAME,
    CONF_LINES,
    CONF_STOP_COORD,
    CONF_STOP_ID,
    CONF_STOP_NAME,
    DOMAIN,
)
from homeassistant.components.ha_departures.coordinator import (
    DeparturesDataUpdateCoordinator,
)
from homeassistant.components.ha_departures.sensor import DeparturesSensor
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from tests.common import MockConfigEntry

#####################################
#      Mock config entry data       #
#####################################

ENTRY_TEST_DATA = {
    CONF_API_URL: "http://test.mock",
    CONF_STOP_ID: "stop_id",
    CONF_STOP_NAME: "stop_name",
    CONF_STOP_COORD: [1.0, 2.0],
    CONF_HUB_NAME: "hub_name",
}

#####################################
##### Mock apyefa data classes ######
#####################################

MOCK_LOCATION_A = {
    "id": "de:1:1",
    "isGlobalId": True,
    "name": "Station A",
    "disassembledName": "Station A",
    "coord": [49.11111, 11.22222],
    "type": "stop",
    "matchQuality": 100000,
    "isBest": True,
    "parent": {
        "id": "placeID:1:1",
        "name": "Hauptstation",
        "type": "locality",
    },
    "assignedStops": [
        {
            "id": "de:7:7",
            "isGlobalId": True,
            "name": "City Station A",
            "disassembledName": "Station A",
            "type": "stop",
            "coord": [49.123455, 11.54321],
            "parent": {"name": "City", "type": "locality"},
            "productClasses": [2],
            "connectingMode": 100,
            "properties": {"stopId": "88888"},
        }
    ],
    "properties": {"stopId": "456"},
}

MOCK_LOCATION_B = {
    "id": "de:2:2",
    "isGlobalId": True,
    "name": "Station B",
    "disassembledName": "Station B",
    "coord": [51.11111, 7.22222],
    "type": "stop",
    "matchQuality": 100000,
    "isBest": True,
    "parent": {"id": "placeID:5555:1", "name": "Hauptstation", "type": "locality"},
    "assignedStops": [
        {
            "id": "de:3:3",
            "isGlobalId": True,
            "name": "Hauptbahnhof",
            "disassembledName": "Hauptbahnhof",
            "type": "stop",
            "coord": [51.449732, 7.012213],
            "parent": {"name": "City", "type": "locality"},
            "productClasses": [0, 1, 2],
            "connectingMode": 100,
            "properties": {"stopId": "123456789"},
        }
    ],
    "properties": {
        "additionalTariffData": {
            "area": "",
            "zones": "",
            "layer1": "",
            "layer2": "",
        },
        "stopId": "123",
        "downloads": [{"type": "SM", "url": "vrr/hbf_1.htm", "size": 1}],
    },
}

MOCK_LINES = [
    {
        "id": "mock:11111: :R:j26",
        "name": "U-Bahn U1",
        "disassembledName": "U1",
        "number": "U1",
        "description": "Hauptbahnhof - Station A - Station B",
        "product": {"id": 6, "class": 2, "name": "U-Bahn", "iconId": 1},
        "operator": {"code": "MOCK", "id": "MOCK_ID", "name": "MOCK"},
        "destination": {"id": "1", "name": "Station B", "type": "stop"},
        "properties": {
            "isTTB": True,
            "isSTT": True,
            "isROP": True,
            "tripCode": 0,
            "timetablePeriod": "Jahresfahrplan 2026",
            "validity": {"from": "2025-12-14", "to": "2026-12-12"},
            "lineDisplay": "LINE",
            "globalId": "de:g:1_U1:0",
        },
    },
    {
        "id": "mock:22222: :H:j26",
        "name": "Stadtbus 1",
        "disassembledName": "1",
        "number": "1",
        "description": "Station B - Hauptbahnhof - Station A",
        "product": {"id": 8, "class": 5, "name": "Stadtbus", "iconId": 3},
        "operator": {"code": "MOCK", "id": "MOCK_ID", "name": "MOCK"},
        "destination": {"id": "2", "name": "Station A", "type": "stop"},
        "properties": {
            "isTTB": True,
            "isSTT": True,
            "isROP": True,
            "tripCode": 0,
            "timetablePeriod": "Jahresfahrplan 2026",
            "validity": {"from": "2025-12-14", "to": "2026-12-12"},
            "lineDisplay": "LINE",
            "globalId": "de:g:2_B1:0",
        },
    },
]

MOCK_DEPARTURES_LINE_A = [
    {
        "location": {
            **MOCK_LOCATION_A,
        },
        "departureTimePlanned": "2025-12-29T19:30:00Z",
        "departureTimeBaseTimetable": "2025-12-29T19:30:36Z",
        "transportation": {
            **MOCK_LINES[0],
            "origin": {
                "id": "3000275",
                "name": "Nürnberg Nordwestring",
                "type": "stop",
            },
        },
        "infos": [
            {
                "priority": "normal",
                "id": "43543543",
                "version": 1234563,
                "type": "stopInfo",
                "infoLinks": [
                    {
                        "urlText": "Aufzug im U-Bahnhof Plärrer 1 außer Betrieb",
                        "url": "/d87594c8-f92b-3402-c45d-3d08b49955da",
                        "subtitle": "Aufzug im U-Bahnhof Plärrer 1 außer Betrieb, Standort: Bahnsteig  Straßenebene (Straßenbahninsel)",
                        "htmlText": "Aufzug im U-Bahnhof Plärrer 1 außer Betrieb, Standort: Bahnsteig  Straßenebene (Straßenbahninsel)",
                        "wapText": "Aufzug im U-Bahnhof Plärrer 1 außer Betrieb, Standort: Bahnsteig  Straßenebene (Straßenbahninsel)",
                        "smsText": "Aufzug im U-Bahnhof Plärrer 1 außer Betrieb, Standort: Bahnsteig  Straßenebene (Straßenbahninsel)",
                        "additionalLinks": [
                            {
                                "id": "1",
                                "url": "https://www.vgn.de/d87594c8-f92b-3402-c45d-3d08b49955da",
                                "urlText": "VGN Homepage",
                                "subtitle": "VGN Homepage",
                                "properties": {"linkTarget": "_blank"},
                            }
                        ],
                    }
                ],
            }
        ],
    },
]

MOCK_DEPARTURES_LINE_B = [
    {
        "location": {
            **MOCK_LOCATION_B,
        },
        "departureTimePlanned": "2025-12-29T19:30:00Z",
        "departureTimeBaseTimetable": "2025-12-29T19:30:36Z",
        "transportation": {
            **MOCK_LINES[1],
            "origin": {
                "id": "3000275",
                "name": "Nürnberg Nordwestring",
                "type": "stop",
            },
        },
        "infos": [
            {
                "priority": "normal",
                "id": "43543543",
                "version": 1234563,
                "type": "stopInfo",
                "infoLinks": [
                    {
                        "urlText": "Aufzug im U-Bahnhof Plärrer 1 außer Betrieb",
                        "url": "/d87594c8-f92b-3402-c45d-3d08b49955da",
                        "subtitle": "Aufzug im U-Bahnhof Plärrer 1 außer Betrieb, Standort: Bahnsteig  Straßenebene (Straßenbahninsel)",
                        "htmlText": "Aufzug im U-Bahnhof Plärrer 1 außer Betrieb, Standort: Bahnsteig  Straßenebene (Straßenbahninsel)",
                        "wapText": "Aufzug im U-Bahnhof Plärrer 1 außer Betrieb, Standort: Bahnsteig  Straßenebene (Straßenbahninsel)",
                        "smsText": "Aufzug im U-Bahnhof Plärrer 1 außer Betrieb, Standort: Bahnsteig  Straßenebene (Straßenbahninsel)",
                        "additionalLinks": [
                            {
                                "id": "1",
                                "url": "https://www.vgn.de/d87594c8-f92b-3402-c45d-3d08b49955da",
                                "urlText": "VGN Homepage",
                                "subtitle": "VGN Homepage",
                                "properties": {"linkTarget": "_blank"},
                            }
                        ],
                    }
                ],
            }
        ],
    },
]


def add_mock_config_entry(hass: HomeAssistant, lines: list[dict] | None = None):
    """Creates a new mock config entry and add it to hass instance."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=ENTRY_TEST_DATA,
        options={CONF_LINES: lines or []},
    )
    entry.add_to_hass(hass)

    return entry


def mock_efa_client(stops=None, lines=None, departures=None):
    """Create a mock EfaClient."""
    client = AsyncMock()
    client.locations_by_name.return_value = stops or []
    client.lines_by_location.return_value = lines or []
    client.departures_by_location.return_value = departures or []

    efa = AsyncMock()
    efa.__aenter__.return_value = client
    efa.__aexit__.return_value = None

    return efa


@pytest.fixture
def mock_coordinator(hass: HomeAssistant) -> DeparturesDataUpdateCoordinator:
    """Create a mock DataUpdateCoordinator."""

    url = "http://hello.world"
    stop_id: str = "my_stop_1"

    return DeparturesDataUpdateCoordinator(hass, url, stop_id, Mock(spec=ConfigEntry))


@pytest.fixture
def mock_line(mock_locations) -> Line | None:
    """Create a mock Line object."""
    destination_dict = mock_locations[0].to_dict()
    origin_dict = mock_locations[1].to_dict()

    line_dict = {
        "id": "vag:01:02",
        "name": "mock_line",
        "number": "12345",
        "disassembledName": "disassembled name",
        "description": "mock description",
        "product": {"class": 5},
        "operator": {
            "id": "id operator",
            "code": "code operator",
            "name": "mock operator",
        },
        "destination": destination_dict,
        "origin": origin_dict,
        "properties": {},
        "coords": [1.0, 1.0],
    }
    return Line.from_dict(line_dict)


@pytest.fixture
def mock_sensor(hass: HomeAssistant) -> DeparturesSensor:
    """Return a mock sensor(without connection to HA)."""
    coordinator = DeparturesDataUpdateCoordinator(
        hass,
        ENTRY_TEST_DATA[CONF_API_URL],
        ENTRY_TEST_DATA[CONF_STOP_ID],
        Mock(spec=ConfigEntry),
    )

    return DeparturesSensor(
        hass,
        coordinator=coordinator,
        line_dict=MOCK_LINES[0],
        stop_name=ENTRY_TEST_DATA[CONF_STOP_NAME],
        hub_name=ENTRY_TEST_DATA[CONF_HUB_NAME],
        stop_coord=ENTRY_TEST_DATA[CONF_STOP_COORD],
        api_url=ENTRY_TEST_DATA[CONF_API_URL],
    )
