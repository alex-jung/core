"""DataUpdateCoordinator for ha_departures integration."""

from datetime import timedelta
import logging

from apyefa import Departure, EfaClient
from apyefa.exceptions import EfaConnectionError, EfaResponseInvalid

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DOMAIN

SCAN_INTERVAL = timedelta(seconds=60)
_LOGGER: logging.Logger = logging.getLogger(__name__)


class DeparturesDataUpdateCoordinator(DataUpdateCoordinator[list[Departure]]):
    """Class to manage fetching data from the API."""

    def __init__(
        self,
        hass: HomeAssistant,
        url: str,
        stop_id: str,
        config_entry,
    ) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=config_entry,
            update_interval=SCAN_INTERVAL,
        )

        self._url: str = url
        self._stop_id: str = stop_id
        self._data = list[Departure]

    @property
    def stop_id(self):
        """Return config entry stop ID."""
        return self._stop_id

    @property
    def api_url(self):
        """Return Provider API URL."""
        return self._url

    async def _async_update_data(self):
        """Fetch data from endpoint."""

        now_time = dt_util.now().strftime("%H:%M")

        async with EfaClient(self._url) as client:
            try:
                self._data = await client.departures_by_location(
                    self._stop_id, arg_date=now_time, realtime=True
                )
            except EfaConnectionError as err:
                _LOGGER.error("Connection to EFA client failed")
                raise UpdateFailed(err) from err
            except EfaResponseInvalid as err:
                _LOGGER.error("EFA response invalid")
                raise UpdateFailed(err) from err

        return self._data
