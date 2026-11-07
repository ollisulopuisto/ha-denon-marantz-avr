"""Tests for DenonDevice media player entity."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from custom_components.denon_marantz_avr.media_player import (
    TELNET_EVENTS,
    DenonDevice,
)
from denonavr.const import ALL_TELNET_EVENTS
from homeassistant.components.media_player import MediaPlayerState, MediaType


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


def test_input_func_sets_cached_and_properties(mock_receiver, mock_config_entry):
    """Test that netaudio and playing function sets are cached and used."""
    mock_receiver.netaudio_func_list = ["Online Music", "Media Server"]
    mock_receiver.playing_func_list = ["Online Music", "Media Server", "Bluetooth"]
    mock_receiver.image_url = "http://example.com/cover.jpg"
    mock_receiver.title = "Song Title"
    mock_receiver.frequency = "101.5 MHz"

    device = DenonDevice(
        receiver=mock_receiver,
        unique_id="test_unique_id-Main",
        config_entry=mock_config_entry,
        update_audyssey=False,
    )

    # Initial sets should be populated from receiver lists
    assert device._netaudio_func_set == {"Online Music", "Media Server"}
    assert device._playing_func_set == {"Online Music", "Media Server", "Bluetooth"}

    # Test supported_features with netaudio input
    mock_receiver.input_func = "Online Music"
    features_netaudio = device.supported_features
    mock_receiver.input_func = "CD"
    features_cd = device.supported_features
    assert features_netaudio != features_cd

    # Test media_image_url with playing input
    mock_receiver.input_func = "Bluetooth"
    assert device.media_image_url == "http://example.com/cover.jpg"
    mock_receiver.input_func = "CD"
    assert device.media_image_url is None

    # Test media_title with playing input vs non-playing input
    mock_receiver.input_func = "Bluetooth"
    assert device.media_title == "Song Title"
    mock_receiver.input_func = "CD"
    assert device.media_title == "CD"

    # None input_func handled safely
    mock_receiver.input_func = None
    assert device.media_image_url is None
    assert device.media_title is None


async def test_update_refreshes_input_func_sets(mock_receiver, mock_config_entry):
    """Test that async_update refreshes the cached sets."""
    mock_receiver.telnet_connected = False
    mock_receiver.telnet_healthy = False
    mock_receiver.async_update = AsyncMock()
    mock_receiver.netaudio_func_list = ["Online Music"]
    mock_receiver.playing_func_list = ["Online Music"]

    device = DenonDevice(
        receiver=mock_receiver,
        unique_id="test_unique_id-Main",
        config_entry=mock_config_entry,
        update_audyssey=False,
    )
    device.hass = MagicMock()
    device._web_api_available = False
    assert device._netaudio_func_set == {"Online Music"}

    # Update receiver sources
    mock_receiver.netaudio_func_list = ["Online Music", "Media Server"]
    mock_receiver.playing_func_list = ["Online Music", "Media Server"]
    mock_receiver.input_func_list = ["Online Music", "Media Server"]

    await device.async_update()
    assert device._netaudio_func_set == {"Online Music", "Media Server"}
    assert device._playing_func_set == {"Online Music", "Media Server"}
    assert device.source_list == ["Online Music", "Media Server"]


def test_source_list_cached_and_media_content_type(mock_receiver, mock_config_entry):
    """Test source_list caching and media_content_type behavior."""
    mock_receiver.input_func_list = ["CD", "DVD", "TV"]
    mock_receiver.state = "playing"

    device = DenonDevice(
        receiver=mock_receiver,
        unique_id="test_unique_id-Main",
        config_entry=mock_config_entry,
        update_audyssey=False,
    )

    # Initial source list should be cached
    assert device.source_list == ["CD", "DVD", "TV"]
    assert device.source_list is device._source_list

    # media_content_type checks
    assert device.media_content_type == MediaType.MUSIC

    mock_receiver.state = MediaPlayerState.PAUSED
    assert device.media_content_type == MediaType.MUSIC

    mock_receiver.state = "paused"
    assert device.media_content_type == MediaType.MUSIC

    mock_receiver.state = "on"
    assert device.media_content_type == MediaType.CHANNEL

    mock_receiver.state = "off"
    assert device.media_content_type == MediaType.CHANNEL


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
