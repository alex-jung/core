"""
The hangouts bot component.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/hangouts/
"""
import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers import dispatcher
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_BOT, CONF_INTENTS, CONF_REFRESH_TOKEN, DOMAIN,
    EVENT_HANGOUTS_CONNECTED, EVENT_HANGOUTS_CONVERSATIONS_CHANGED,
    MESSAGE_SCHEMA, SERVICE_SEND_MESSAGE,
    SERVICE_UPDATE, CONF_SENTENCES, CONF_MATCHERS,
    CONF_ERROR_SUPPRESSED_CONVERSATIONS, INTENT_SCHEMA, TARGETS_SCHEMA)

# We need an import from .config_flow, without it .config_flow is never loaded.
from .config_flow import HangoutsFlowHandler  # noqa: F401


REQUIREMENTS = ['hangups==0.4.5']

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Optional(CONF_INTENTS, default={}): vol.Schema({
            cv.string: INTENT_SCHEMA
        }),
        vol.Optional(CONF_ERROR_SUPPRESSED_CONVERSATIONS, default=[]):
            [TARGETS_SCHEMA]
    })
}, extra=vol.ALLOW_EXTRA)


async def async_setup(hass, config):
    """Set up the Hangouts bot component."""
    from homeassistant.components.conversation import create_matcher

    config = config.get(DOMAIN)
    if config is None:
        return True

    hass.data[DOMAIN] = {CONF_INTENTS: config.get(CONF_INTENTS),
                         CONF_ERROR_SUPPRESSED_CONVERSATIONS:
                             config.get(CONF_ERROR_SUPPRESSED_CONVERSATIONS)}

    for data in hass.data[DOMAIN][CONF_INTENTS].values():
        matchers = []
        for sentence in data[CONF_SENTENCES]:
            matchers.append(create_matcher(sentence))

        data[CONF_MATCHERS] = matchers

    hass.async_add_job(hass.config_entries.flow.async_init(
        DOMAIN, context={'source': config_entries.SOURCE_IMPORT}
    ))

    return True


async def async_setup_entry(hass, config):
    """Set up a config entry."""
    from hangups.auth import GoogleAuthError

    try:
        from .hangouts_bot import HangoutsBot

        bot = HangoutsBot(
            hass,
            config.data.get(CONF_REFRESH_TOKEN),
            hass.data[DOMAIN][CONF_INTENTS],
            hass.data[DOMAIN][CONF_ERROR_SUPPRESSED_CONVERSATIONS])
        hass.data[DOMAIN][CONF_BOT] = bot
    except GoogleAuthError as exception:
        _LOGGER.error("Hangouts failed to log in: %s", str(exception))
        return False

    dispatcher.async_dispatcher_connect(
        hass,
        EVENT_HANGOUTS_CONNECTED,
        bot.async_handle_update_users_and_conversations)

    dispatcher.async_dispatcher_connect(
        hass,
        EVENT_HANGOUTS_CONVERSATIONS_CHANGED,
        bot.async_update_conversation_commands)
    dispatcher.async_dispatcher_connect(
        hass,
        EVENT_HANGOUTS_CONVERSATIONS_CHANGED,
        bot.async_handle_update_error_suppressed_conversations)

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP,
                               bot.async_handle_hass_stop)

    await bot.async_connect()

    hass.services.async_register(DOMAIN, SERVICE_SEND_MESSAGE,
                                 bot.async_handle_send_message,
                                 schema=MESSAGE_SCHEMA)
    hass.services.async_register(DOMAIN,
                                 SERVICE_UPDATE,
                                 bot.
                                 async_handle_update_users_and_conversations,
                                 schema=vol.Schema({}))

    return True


async def async_unload_entry(hass, _):
    """Unload a config entry."""
    bot = hass.data[DOMAIN].pop(CONF_BOT)
    await bot.async_disconnect()
    return True
