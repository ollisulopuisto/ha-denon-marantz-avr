"""Tests for DenonDevice media player entity."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from custom_components.denon_marantz_avr.media_player import (
    TELNET_EVENTS,
    DenonDevice,
)
from denonavr.const import ALL_TELNET_EVENTS


@pytest.fixture
def mock_receiver():
    """Mock DenonAVR receiver."""
    receiver = MagicMock()
    receiver.zone = "Main"
    receiver.name = "Test Receiver"
    receiver.sound_mode_list = ["Stereo", "Direct"]
    receiver.support_sound_mode = True
    receiver.telnet_connected = True
    receiver.async_telnet_disconnect = AsyncMock()
    receiver.register_callback = MagicMock()
    receiver.unregister_callback = MagicMock()
    return receiver


@pytest.fixture
def mock_config_entry():
    """Mock config entry."""
    entry = MagicMock()
    entry.unique_id = "test_unique_id"
    entry.data = {
        "host": "192.168.1.100",
        "type": "avr-x",
        "manufacturer": "Denon",
        "model": "AVR-X2700H",
    }
    return entry


@pytest.fixture
def denon_device(mock_receiver, mock_config_entry):
    """DenonDevice instance."""
    return DenonDevice(
        receiver=mock_receiver,
        unique_id="test_unique_id-Main",
        config_entry=mock_config_entry,
        update_audyssey=False,
    )


async def test_async_added_to_hass_registers_telnet_events(denon_device, mock_receiver):
    """Test that async_added_to_hass only registers for TELNET_EVENTS."""
    await denon_device.async_added_to_hass()

    registered_events = {
        call.args[0] for call in mock_receiver.register_callback.call_args_list
    }
    assert ALL_TELNET_EVENTS not in registered_events
    assert registered_events == TELNET_EVENTS

    # Verify that the callback registered for each event is _telnet_callback
    for call in mock_receiver.register_callback.call_args_list:
        event, callback = call.args
        assert event in TELNET_EVENTS
        assert callback == denon_device._telnet_callback


async def test_async_will_remove_from_hass_unregisters_telnet_events(
    denon_device, mock_receiver
):
    """Test that async_will_remove_from_hass unregisters TELNET_EVENTS and disconnects."""
    await denon_device.async_will_remove_from_hass()

    mock_receiver.async_telnet_disconnect.assert_awaited_once()

    unregistered_events = {
        call.args[0] for call in mock_receiver.unregister_callback.call_args_list
    }
    assert ALL_TELNET_EVENTS not in unregistered_events
    assert unregistered_events == TELNET_EVENTS

    for call in mock_receiver.unregister_callback.call_args_list:
        event, callback = call.args
        assert event in TELNET_EVENTS
        assert callback == denon_device._telnet_callback
