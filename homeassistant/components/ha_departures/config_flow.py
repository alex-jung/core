"""Adds config flow for Public Transport Departures."""

import logging

from aiohttp import ConnectionTimeoutError
from apyefa import EfaClient, Line, LineRequestType, Location, LocationFilter
from apyefa.exceptions import EfaConnectionError, EfaResponseInvalid
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_API_URL,
    CONF_ENDPOINT,
    CONF_ERROR_CONNECTION_FAILED,
    CONF_ERROR_INVALID_RESPONSE,
    CONF_ERROR_NO_CHANGES_OPTIONS,
    CONF_ERROR_NO_STOP_FOUND,
    CONF_HUB_NAME,
    CONF_LINES,
    CONF_STOP_COORD,
    CONF_STOP_ID,
    CONF_STOP_NAME,
    DOMAIN,
    EFA_ENDPOINTS,
    VERSION,
)
from .helper import compare_list_lines, get_unique_lines

_LOGGER = logging.getLogger(__name__)


class HaDeparturesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for ha_departures."""

    VERSION = 1
    MINOR_VERSION = 4

    def __init__(self) -> None:
        """Initialize."""
        self._all_stops: list[Location] = []
        self._all_lines: list[Line] = []

        self._data: dict[str, str | list[int]] = {
            CONF_API_URL: "",
            CONF_STOP_ID: "",
            CONF_STOP_NAME: "",
            CONF_STOP_COORD: [],
            CONF_HUB_NAME: "",
        }
        self._options: dict[str, list[dict]] = {}

        _LOGGER.debug(" Start CONFIGURATION flow ".center(60, "="))
        _LOGGER.debug(">> ha-departures version: %s", VERSION)
        _LOGGER.debug(
            ">> config flow version %s.%s",
            HaDeparturesConfigFlow.VERSION,
            HaDeparturesConfigFlow.MINOR_VERSION,
        )

    async def async_step_user(self, user_input=None) -> config_entries.ConfigFlowResult:
        """Handle a flow initialized by the user."""
        _errors: dict[str, str] = {}

        _LOGGER.debug(' Start "step_user" '.center(60, "-"))
        _LOGGER.debug(">> user input: %s", user_input)

        if user_input is not None:
            api_url = self._data[CONF_API_URL] = user_input[CONF_ENDPOINT]

            try:
                async with EfaClient(api_url) as client:
                    self._all_stops = await client.locations_by_name(
                        user_input[CONF_STOP_NAME], filters=[LocationFilter.STOPS]
                    )
            except (EfaConnectionError, ConnectionTimeoutError) as err:
                _errors["base"] = CONF_ERROR_CONNECTION_FAILED
                _LOGGER.error('Failed to connect EFA api "%s"', api_url, exc_info=err)
            except EfaResponseInvalid as err:
                _errors["base"] = CONF_ERROR_INVALID_RESPONSE
                _LOGGER.error("Received invalid response from api", exc_info=err)

            if not _errors:
                _LOGGER.debug(
                    '%s stop(s) found for "%s":',
                    len(self._all_stops),
                    user_input[CONF_STOP_NAME],
                )

                for stop in self._all_stops:
                    _LOGGER.debug(
                        "> %s(%s)",
                        stop.name,
                        stop.id,
                    )

                if not self._all_stops:
                    _errors["base"] = CONF_ERROR_NO_STOP_FOUND
                else:
                    return await self.async_step_stop()

        endpoints = [
            SelectOptionDict(label=name, value=url)
            for name, url in EFA_ENDPOINTS.items()
        ]

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ENDPOINT): SelectSelector(
                        SelectSelectorConfig(
                            options=endpoints,
                            multiple=False,
                            sort=False,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required(CONF_STOP_NAME): str,
                }
            ),
            errors=_errors,
        )

    async def async_step_stop(self, user_input=None) -> config_entries.ConfigFlowResult:
        """Handle step to choose a stop from the available list."""
        _errors: dict[str, str] = {}

        _LOGGER.debug(' Start "step_stop" '.center(60, "-"))
        _LOGGER.debug(">> user input: %s", user_input)

        if user_input is not None:
            stop = next(
                (x for x in self._all_stops if x.id == user_input[CONF_STOP_NAME]),
                None,
            )

            assert stop, "No stop found"

            self._data[CONF_STOP_ID] = stop.id
            self._data[CONF_STOP_NAME] = stop.name
            self._data[CONF_STOP_COORD] = stop.coord

            _LOGGER.debug(
                "Selected stop: %s(%s)",
                stop.name,
                stop.id,
            )

            return await self.async_step_lines()

        stop_list: list[SelectOptionDict] = [
            SelectOptionDict(
                label=stop.name,
                value=stop.id,
            )
            for stop in self._all_stops
        ]

        return self.async_show_form(
            step_id="stop",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_STOP_NAME): SelectSelector(
                        SelectSelectorConfig(
                            options=stop_list,
                            multiple=False,
                            sort=True,
                            mode=SelectSelectorMode.DROPDOWN,
                        ),
                    )
                }
            ),
            errors=_errors,
        )

    async def async_step_lines(
        self, user_input=None
    ) -> config_entries.ConfigFlowResult:
        """Handle step to choose needed lines."""
        _errors: dict[str, str] = {}

        _LOGGER.debug(' Start "step_lines" '.center(60, "-"))
        _LOGGER.debug(">> user input: %s", user_input)

        if user_input is not None:
            # filter lines by user input
            lines = list(
                filter(
                    lambda x: str(hash(x)) in user_input[CONF_LINES],
                    self._all_lines,
                )
            )

            for line in lines:
                _LOGGER.debug(
                    "Selected line: %s(%s) -> %s(%s)",
                    line.name,
                    line.id,
                    line.destination.name,
                    line.destination.id,
                )

            self._options = {
                CONF_LINES: [x.to_dict() for x in lines],
            }

            return await self.async_step_hubname()

        # load all lines for chosen stop location
        api_url: str = str(self._data.get(CONF_API_URL, ""))
        stop_id: str = str(self._data.get(CONF_STOP_ID, ""))

        async with EfaClient(api_url) as client:
            self._all_lines = await client.lines_by_location(
                stop_id, req_types=[LineRequestType.DEPARTURE_MONITOR]
            )

        self._all_lines = get_unique_lines(self._all_lines)

        _LOGGER.debug("Step lines: %s unique line(s) found:", len(self._all_lines))

        for line in self._all_lines:
            _LOGGER.debug(
                "> %s(%s) --> %s(%s)",
                line.name,
                line.id,
                line.destination.name,
                line.destination.id,
            )

        line_list: list[SelectOptionDict] = [
            SelectOptionDict(
                label=f"{line.name} - {line.destination.name}",
                value=str(hash(line)),
            )
            for line in self._all_lines
        ]

        return self.async_show_form(
            step_id="lines",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_LINES): SelectSelector(
                        SelectSelectorConfig(
                            options=line_list,
                            multiple=True,
                            sort=True,
                            mode=SelectSelectorMode.DROPDOWN,
                        ),
                    )
                }
            ),
            errors=_errors,
        )

    async def async_step_hubname(
        self, user_input=None
    ) -> config_entries.ConfigFlowResult:
        """Handle step to define a hub name."""

        _LOGGER.debug(' Start "step_hubname" '.center(60, "-"))
        _LOGGER.debug(">> user input: %s", user_input)

        stop_name = str(self._data.get(CONF_STOP_NAME, ""))

        if user_input is not None:
            hub_name = user_input.get(CONF_HUB_NAME, stop_name)

            await self.async_set_unique_id(hub_name)

            self._abort_if_unique_id_configured()

            self._data[CONF_HUB_NAME] = hub_name

            _LOGGER.debug(" Create a new config entry ".center(60, "-"))
            _LOGGER.debug("Title:%s", hub_name)
            _LOGGER.debug("Data:\n %s", self._data)
            _LOGGER.debug("Options:\n %s", self._options)

            return self.async_create_entry(
                title=hub_name,
                data=self._data,
                options=self._options,
            )

        return self.async_show_form(
            step_id="hubname",
            data_schema=vol.Schema(
                {vol.Required(CONF_HUB_NAME, default=stop_name): cv.string}
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return options flow."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Config flow options handler for ha-departures."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""

        _LOGGER.debug(" Start OPTIONS flow ".center(60, "="))
        _LOGGER.debug(">> ha-departures version: %s", VERSION)
        _LOGGER.debug(
            ">> config flow version %s.%s",
            HaDeparturesConfigFlow.VERSION,
            HaDeparturesConfigFlow.MINOR_VERSION,
        )
        _LOGGER.debug(
            ">> config entry: %s(uid=%s)", config_entry.title, config_entry.unique_id
        )

        self._selected_lines: list[Line | None] = [
            Line.from_dict(x) for x in config_entry.options.get(CONF_LINES, [])
        ]
        self._available_lines: list[Line] = []

    async def async_step_init(self, user_input=None) -> config_entries.ConfigFlowResult:
        """Handle a flow initialized by the user."""

        _LOGGER.debug(' Start "step_init" '.center(60, "-"))
        _LOGGER.debug(">> user input: %s", user_input)

        if user_input is not None:
            new_selected_lines: list[Line] = list(
                filter(
                    lambda x: str(hash(x)) in user_input.get(CONF_LINES, []),
                    self._available_lines,
                )
            )

            _LOGGER.debug(" New lines configured ".center(60, "="))
            for line in new_selected_lines:
                _LOGGER.debug(
                    ">> %s(%s) -> %s(%s)",
                    line.name,
                    line.id,
                    line.destination.name,
                    line.destination.id,
                )

            if compare_list_lines(new_selected_lines, self._selected_lines):
                _LOGGER.debug("No changes on entry configuration detected")
                return self.async_abort(reason=CONF_ERROR_NO_CHANGES_OPTIONS)

            return self.async_create_entry(
                data={
                    CONF_LINES: [x.to_dict() for x in new_selected_lines],
                }
            )

        stop_id: str = self.config_entry.data.get(CONF_STOP_ID, "")
        api_url: str = self.config_entry.data.get(CONF_API_URL, "")

        # load all available lines for chosen stop location
        self._available_lines = await get_unique_lines_by_location(api_url, stop_id)

        # prepare list of selectable lines
        line_list: list[SelectOptionDict] = [
            SelectOptionDict(
                label=f"{line.name} - {line.destination.name}",
                value=str(hash(line)),
            )
            for line in self._available_lines
        ]

        for line in line_list:
            _LOGGER.debug("> %s", line)

        default_list = [str(hash(x)) for x in self._selected_lines]

        for line in default_list:
            _LOGGER.debug(
                ">> Selected line: %s",
                next(filter(lambda x: x["value"] == line, line_list), None),
            )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "lines",
                        default=default_list,
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=line_list,
                            multiple=True,
                            sort=True,
                            mode=SelectSelectorMode.DROPDOWN,
                        ),
                    )
                }
            ),
        )


async def get_unique_lines_by_location(url: str, stop_id: str) -> list[Line]:
    """Fetch lines for a given stop location using the provided EfaClient and returns list of unique lines.

    Args:
        efa_client (EfaClient): An instance of EfaClient to interact with the EFA API.
        stop_id (str): The identifier of the stop location.

    Returns:
        list[Line]: A list of Line objects associated with the specified stop location.

    """
    lines = []

    async with EfaClient(url) as efa_client:
        lines = await efa_client.lines_by_location(
            stop_id, req_types=[LineRequestType.DEPARTURE_MONITOR]
        )

    return get_unique_lines(lines)
