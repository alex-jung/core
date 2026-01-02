"""Sensor platform for Public Transport Departures."""

from datetime import datetime
import logging

from apyefa import Departure, Line, Location, TransportType

from homeassistant import config_entries, core
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import ATTR_LATITUDE, ATTR_LONGITUDE
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DeparturesDataUpdateCoordinator
from .const import (
    ATTR_DIRECTION,
    ATTR_ESTIMATED_DEPARTURE_TIME,
    ATTR_LINE_ID,
    ATTR_LINE_NAME,
    ATTR_PLANNED_DEPARTURE_TIME,
    ATTR_PROVIDER_URL,
    ATTR_TIMES,
    ATTR_TRANSPORT_TYPE,
    CONF_API_URL,
    CONF_HUB_NAME,
    CONF_LINES,
    CONF_STOP_COORD,
    CONF_STOP_NAME,
)
from .helper import (
    UnstableDepartureTime,
    create_unique_id,
    filter_by_line_id,
    filter_identical_departures,
    replace_year_in_id,
)

_LOGGER = logging.getLogger(__name__)


PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: core.HomeAssistant,
    entry: config_entries.ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Departures entries."""
    coordinator = entry.runtime_data.coordinator

    api_url: str = entry.data.get(CONF_API_URL, "")
    stop_name: str = entry.data.get(CONF_STOP_NAME, "")
    stop_coord: list[float] = entry.data.get(CONF_STOP_COORD, [])
    hub_name: str = entry.data.get(CONF_HUB_NAME, "")

    lines: list[dict] = entry.options.get(CONF_LINES, [])

    async_add_entities(
        [
            DeparturesSensor(
                hass, coordinator, line, stop_name, hub_name, stop_coord, api_url
            )
            for line in lines
        ],
        update_before_add=True,
    )


class DeparturesSensor(
    CoordinatorEntity[DeparturesDataUpdateCoordinator], SensorEntity
):
    """ha_departures Sensor class."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: core.HomeAssistant,
        coordinator: DeparturesDataUpdateCoordinator,
        line_dict: dict,
        stop_name: str,
        hub_name: str,
        stop_coord: list[float],
        api_url: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        line = Line.from_dict(line_dict)

        self._hass: core.HomeAssistant = hass
        self._transport = line.product
        self._line: str = line.name
        self._line_id: str = line.id
        self._destination: Location = line.destination
        self._value: datetime | None = None
        self._times: list[UnstableDepartureTime] = []

        self._attr_name = f"{stop_name}-{self._line}-{self._destination.name}"
        self._attr_unique_id = create_unique_id(line, hub_name)

        self._attr_extra_state_attributes = {
            ATTR_LINE_NAME: self._line,
            ATTR_LINE_ID: replace_year_in_id(self._line_id, False),
            ATTR_TRANSPORT_TYPE: self._transport.name,
            ATTR_DIRECTION: line.destination.name,
            ATTR_PROVIDER_URL: api_url,
            ATTR_LATITUDE: (stop_coord[0] if stop_coord else None),
            ATTR_LONGITUDE: (stop_coord[1] if stop_coord else None),
            ATTR_TIMES: [],
        }

        _LOGGER.debug('ha-departures sensor "%s" created', self.unique_id)

    @property
    def native_value(self) -> datetime | None:
        """Return value of this sensor."""
        return self._value

    @property
    def icon(self) -> str:
        """Icon of the entity, based on transport type."""
        match self._transport:
            case (
                TransportType.CITY_BUS
                | TransportType.REGIONAL_BUS
                | TransportType.EXPRESS_BUS
            ):
                return "mdi:bus"
            case TransportType.TRAM:
                return "mdi:tram"
            case TransportType.SUBWAY:
                return "mdi:subway"
            case TransportType.AST:
                return "mdi:taxi"
            case TransportType.SUBURBAN | TransportType.TRAIN | TransportType.CITY_RAIL:
                return "mdi:train"
            case _:
                return "mdi:train-bus"

    @core.callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""

        debug_title = f" Update '{self._line}' -> '{self._destination.name}' "

        _LOGGER.debug(debug_title.center(70, "="))
        _LOGGER.debug(">> Unique ID: %s", self.unique_id)

        departures: list[Departure] = []

        _LOGGER.debug(
            ">> Before line id filtering: %s departures", len(self.coordinator.data)
        )
        departures = filter_by_line_id(self.coordinator.data, self._line_id)

        _LOGGER.debug(
            ">> Before identical departures filtering: %s departures",
            len(departures),
        )
        departures = filter_identical_departures(departures)

        if not departures:
            _LOGGER.debug(">> No departures found")
            self.clear_times()

            return

        _LOGGER.debug(">> After all filters: %s departures", len(departures))

        self._update_times(departures)

        self._value = self._calculate_datetime(departures[0])

        self.async_write_ha_state()

    def clear_times(self):
        """Clear all times."""
        for time in self._times:
            time.clear()

        self._value = None

        self._attr_extra_state_attributes.update(
            {
                ATTR_TIMES: [],
            }
        )

    def _update_times(self, departures: list[Departure]):
        for index, departure in enumerate(departures):
            planned_time = departure.planned_time
            estimated_time = departure.estimated_time

            _LOGGER.debug(
                ">> [%s]: %s -> %s",
                index,
                planned_time,
                estimated_time,
            )

            if index < len(self._times):
                self._times[index].update(departure)
            else:
                self._times.append(UnstableDepartureTime(departure))

        min_length = min(len(departures), len(self._times))

        # Trim the list to the minimum length
        self._times = self._times[:min_length]

        for t in self._times:
            _LOGGER.debug(
                ">> Time entry: planned=%s, estimated=%s",
                t.planned_time,
                t.estimated_time,
            )

        self._attr_extra_state_attributes.update(
            {
                ATTR_TIMES: [
                    {
                        ATTR_PLANNED_DEPARTURE_TIME: time.planned_time,
                        ATTR_ESTIMATED_DEPARTURE_TIME: time.estimated_time,
                    }
                    for time in self._times
                ],
            }
        )

    def _calculate_datetime(self, departure: Departure) -> datetime | None:
        """Calculate the effective departure datetime.

        Determines the departure time to use by prioritizing the estimated time
        over the planned time if available.

        Args:
            departure: A Departure object containing time information.

        Returns:
            (datetime | None): The estimated departure time if available,
                             otherwise the planned departure time.
                             Returns None if departure is None or not a Departure instance.

        """
        if not departure or not isinstance(departure, Departure):
            return None

        return (
            departure.estimated_time
            if departure.estimated_time
            else departure.planned_time
        )
