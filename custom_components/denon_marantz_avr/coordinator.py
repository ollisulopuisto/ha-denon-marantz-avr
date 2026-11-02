"""
Data coordinator for the native Audyssey/Eco controls.

This coordinator drives the extra receiver controls (Dynamic EQ, Dynamic
Volume, Reference Level Offset, MultiEQ, Eco mode and the Audyssey/recover
buttons) that the media player does not expose. It reuses the same
:class:`denonavr.DenonAVR` instance created for the media player, so no second
connection to the receiver is opened.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING

from denonavr.exceptions import DenonAvrError
from homeassistant.core import callback
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONTROLS_SCAN_INTERVAL,
    CONTROLS_TELNET_EVENTS,
    DEFAULT_POWER_OFF_DELAY,
    DEFAULT_POWER_ON_DELAY,
    DOMAIN,
)
from .webapi import (
    async_get_sound_mode_settings,
    async_select_genre,
    async_select_sound_mode,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from denonavr import DenonAVR
    from homeassistant.core import HomeAssistant

    from .webapi import SoundModeSettings

_LOGGER = logging.getLogger(__name__)


class DenonControlsCoordinator(DataUpdateCoordinator[None]):
    """Coordinate receiver control updates and serialize commands."""

    def __init__(
        self,
        hass: HomeAssistant,
        receiver: DenonAVR,
        device_id: str,
    ) -> None:
        """Initialize the coordinator around an existing receiver."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=CONTROLS_SCAN_INTERVAL,
        )
        self.receiver = receiver
        self.device_id = device_id
        self.command_lock = asyncio.Lock()
        # Real sound-mode list / current category from the port-11080 web API.
        self.sound_modes: SoundModeSettings | None = None
        self.web_available = False
        self._web_probed = False

    async def _async_update_web(self) -> None:
        """Refresh the web-API sound-mode settings (best-effort)."""
        if self._web_probed and not self.web_available:
            return
        settings = await async_get_sound_mode_settings(
            get_async_client(self.hass), self.receiver.host
        )
        if settings is not None:
            self.web_available = True
            self.sound_modes = settings
        elif not self._web_probed:
            self.web_available = False
        self._web_probed = True

    async def async_set_sound_category(self, index: int) -> None:
        """Select a sound-mode category (genre) and refresh."""
        await async_select_genre(get_async_client(self.hass), self.receiver.host, index)
        await self.async_request_refresh()

    async def async_set_sound_mode(self, index: int) -> None:
        """Select a sound mode by its web-API index and refresh."""
        await async_select_sound_mode(
            get_async_client(self.hass), self.receiver.host, index
        )
        await self.async_request_refresh()

    @callback
    def async_register_telnet_listener(self) -> Callable[[], None]:
        """
        Refresh the control entities in real time on Telnet events.

        Many of the receiver's extra settings (Dialog Enhancer, M-DAX, audio
        delay, Bluetooth transmitter, ...) are only pushed over Telnet. The
        30 s poll already reads their current value, but registering for
        Telnet events lets the controls update immediately. Returns a
        callback that unregisters the listener.
        """

        # Performance optimization: Only subscribe to Telnet events that affect
        # controls managed by this coordinator (CONTROLS_TELNET_EVENTS).
        # Subscribing to ALL_TELNET_EVENTS causes high-frequency events (such as
        # streaming progress NSE, volume MV, or channel volume CV) to trigger
        # async_set_updated_data(None), which needlessly updates and writes state
        # for all ~10 coordinator entities on every tick.
        def _telnet_callback(zone: str, event: str, parameter: str) -> None:  # noqa: ARG001
            self.async_set_updated_data(None)

        for event in CONTROLS_TELNET_EVENTS:
            self.receiver.register_callback(event, _telnet_callback)

        def _unregister() -> None:
            for event in CONTROLS_TELNET_EVENTS:
                self.receiver.unregister_callback(event, _telnet_callback)

        return _unregister

    async def async_send(self, command: Callable[[], Awaitable[None]]) -> None:
        """Run a single receiver command, serialized, then refresh entities."""
        async with self.command_lock:
            await command()
        self.async_set_updated_data(None)

    async def _async_update_data(self) -> None:
        """
        Read current receiver and Audyssey settings.

        The plain receiver update must succeed for the controls to be
        available, but the Audyssey read is best-effort: some models or
        sound modes do not expose it, and a failure there should not take
        the whole integration down.
        """
        try:
            async with self.command_lock:
                await self.receiver.async_update()
                with contextlib.suppress(DenonAvrError):
                    await self.receiver.async_update_audyssey()
        except DenonAvrError as err:
            raise UpdateFailed from err
        await self._async_update_web()

    async def async_run_command(self, command: Callable[[], Awaitable[None]]) -> None:
        """Run one command at a time and refresh Audyssey afterward."""
        async with self.command_lock:
            await command()
            with contextlib.suppress(DenonAvrError):
                await self.receiver.async_update_audyssey()
        self.async_set_updated_data(None)

    async def async_set_eco_mode(self, mode: str) -> None:
        """Set Eco mode and refresh the receiver state."""
        async with self.command_lock:
            await self.receiver.async_eco_mode(mode)
            await self.receiver.async_update()
        self.async_set_updated_data(None)

    async def async_recover_audio(self) -> None:
        """
        Power cycle the receiver and restore its selected input.

        This performs a soft power cycle (standby off/on), it does not cut
        electrical power. The previously selected input is restored once the
        receiver is back online.
        """
        async with self.command_lock:
            await self.receiver.async_update()
            previous_input = self.receiver.input_func
            await self.receiver.async_power_off()
            await asyncio.sleep(DEFAULT_POWER_OFF_DELAY)
            await self.receiver.async_power_on()
            await asyncio.sleep(DEFAULT_POWER_ON_DELAY)
            await self.receiver.async_update()
            if previous_input in self.receiver.input_func_list:
                await self.receiver.async_set_input_func(previous_input)
            with contextlib.suppress(DenonAvrError):
                await self.receiver.async_update_audyssey()
        self.async_set_updated_data(None)
