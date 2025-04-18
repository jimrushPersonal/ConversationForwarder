"""The Forwarder Conversation integration."""

# This code is from nodered_conversation and then modified for my needs
# https://github.com/roblandry/nodered_conversation
from __future__ import annotations

from functools import partial
import logging
import aiohttp
import json
import base64
from typing import Literal

import voluptuous as vol

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import MATCH_ALL

from homeassistant.core import (
    HomeAssistant,
)
from homeassistant.helpers import config_validation as cv, intent
from homeassistant.util import ulid

from .const import (
    CONF_URL,
    CONF_USER,
    CONF_PASS,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Conversation Forwarderfrom a config entry."""

    #hass.data.setdefault(DOMAIN, {})[entry.entry_id] = entry.data[CONF_URL]

    _LOGGER.info(f"entry.data: {entry.data}")
    
    user = ""
    password = ""
    if CONF_USER in entry.data:
        user = entry.data[CONF_USER]
    if CONF_PASS in entry.data:
        password = entry.data[CONF_PASS]
    
    conversation.async_set_agent(hass, entry, CFAgent(hass, entry, entry.data[CONF_URL], user, password ))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data[DOMAIN].pop(entry.entry_id)
    
    conversation.async_unset_agent(hass, entry)
    return True


class CFAgent(conversation.AbstractConversationAgent):
    """Conversation Forwarder agent."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, configUrl, configUser, configPass) -> None:
        """Initialize the agent."""
        self.hass = hass
        self.entry = entry
        self.url=configUrl
        self.user=configPass
        self.password=configPass
        _LOGGER.debug("configUrl %s", configUrl)
        _LOGGER.debug("configUser %s", configUser)
        _LOGGER.debug("configPass %s", configPass)

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Return a list of supported languages."""
        return MATCH_ALL
    
    async def call_post_request(self, url: str, auth: str, data: dict):
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(verify_ssl=False)) as session:
            # session.headers.update({"Authorization": f"Basic {auth}"})
            async with session.post(url, json=data) as response:
                text = await response.text()
                #_LOGGER.warning(f"Post Result: {response}")
                _LOGGER.info(f"Post Result text: {text}")
                return text

    async def async_process(
        self, user_input: conversation.ConversationInput
    ) -> conversation.ConversationResult:
        """Process a sentence."""
        content = {'text': user_input.text, 'conversation_id': user_input.conversation_id, 'device_id': user_input.device_id, 'language': user_input.language, 'agent_id': user_input.agent_id, 'extra_system_prompt': user_input.extra_system_prompt}
        
        _LOGGER.debug("Content sent to endpoint %s", content)
        auth = base64.b64encode(f"{self.user}:{self.password}".encode()).decode()
        
        try:
            _LOGGER.info(f"url: {self.url}")
            result_req = await self.call_post_request(self.url, auth, content)
            result = json.loads(result_req)
        except aiohttp.ClientError:
            _LOGGER.warning("Unable to connect to endpoint "+self.url)
            result = {
                "finish_reason": "error",
                "message": "Sorry, unable to connect to endpoint. Check settings and try again." 
            }
        except json.decoder.JSONDecodeError as e:
            _LOGGER.warning(f"Something happened: {e}")
            _LOGGER.warning(f"Result: {result_req}")
            result = {
                "finish_reason": "error",
                "message": "Sorry, I didn't get a response from endpoint. Check your logs for possible issues."
            }

        _LOGGER.debug(f"Result %s", result)

        # https://github.com/home-assistant/core/blob/220aaf93c6b0d201bb4baa59d96ff9d9c8a66279/homeassistant/helpers/intent.py#L1380
        intent_response = intent.IntentResponse(language=user_input.language)

        shouldContinue = False
        if result["finish_reason"]  != "error":
            intent_response.async_set_speech(result["message"])
            shouldContinue = result["continue_conversation"]
        else:
            intent_response.async_set_speech(result["message"])

        _LOGGER.debug(f"shouldContinue {shouldContinue}")
        # https://github.com/home-assistant/core/blob/eb3cb0e0c7835ca10cdbb225d85f5e22d512e290/homeassistant/components/conversation/models.py#L60
        return conversation.ConversationResult(
            response=intent_response, conversation_id=user_input.conversation_id, continue_conversation=shouldContinue,
            #response=intent_response, conversation_id=user_input.conversation_id, 
        )

