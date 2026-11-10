"""Tests for receiver select entities."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from custom_components.denon_marantz_avr.select import SoundModeSelect
from custom_components.denon_marantz_avr.webapi import SoundModeItem, SoundModeSettings


@pytest.fixture
def mock_coordinator():
    """Create a mock DenonControlsCoordinator."""
    coordinator = MagicMock()
    coordinator.device_id = "test_device_id"
    coordinator.receiver = MagicMock()
    coordinator.receiver.host = "192.168.1.100"
    coordinator.receiver.name = "Test Receiver"
    coordinator.receiver.model_name = "AVR-X2700H"
    coordinator.receiver.manufacturer = "Denon"
    coordinator.receiver.sound_mode_list = ["Stereo", "Direct", "Dolby Surround"]
    coordinator.receiver.sound_mode = "Stereo"
    coordinator.receiver.async_set_sound_mode = AsyncMock()
    coordinator.web_available = False
    coordinator.sound_modes = None
    coordinator.async_set_sound_mode = AsyncMock()

    async def mock_async_send(fn):
        await fn()

    coordinator.async_send = AsyncMock(side_effect=mock_async_send)
    return coordinator


def test_sound_mode_select_fallback_options_cached(mock_coordinator):
    """Test that SoundModeSelect pre-caches receiver fallback sound_mode_list."""
    entity = SoundModeSelect(mock_coordinator)

    # Initial options should match fallback
    assert entity.options == ["Stereo", "Direct", "Dolby Surround"]
    assert entity.options is entity._fallback_options

    # Verify that mutating or calling receiver.sound_mode_list does not change cached options
    mock_coordinator.receiver.sound_mode_list = ["Other"]
    assert entity.options == ["Stereo", "Direct", "Dolby Surround"]
    assert entity.options is entity._fallback_options

    # Current option should read from receiver
    assert entity.current_option == "Stereo"


def test_sound_mode_select_web_modes_options(mock_coordinator):
    """Test that SoundModeSelect returns web API sound modes when available."""
    items = [
        SoundModeItem(index=1, name="Stereo", selected=False),
        SoundModeItem(index=2, name="DTS Neural:X", selected=True),
    ]
    web_settings = SoundModeSettings(genre=1, items=items)
    mock_coordinator.web_available = True
    mock_coordinator.sound_modes = web_settings

    entity = SoundModeSelect(mock_coordinator)

    # Options should return web_settings.names directly without re-allocating
    assert entity.options == ["Stereo", "DTS Neural:X"]
    assert entity.options is web_settings.names
    assert entity.current_option == "DTS Neural:X"


async def test_sound_mode_select_option_web_api(mock_coordinator):
    """Test selecting sound mode using web API index."""
    items = [
        SoundModeItem(index=1, name="Stereo", selected=False),
        SoundModeItem(index=3, name="DTS Neural:X", selected=True),
    ]
    web_settings = SoundModeSettings(genre=1, items=items)
    mock_coordinator.web_available = True
    mock_coordinator.sound_modes = web_settings

    entity = SoundModeSelect(mock_coordinator)
    await entity.async_select_option("Stereo")

    mock_coordinator.async_set_sound_mode.assert_awaited_once_with(1)
    mock_coordinator.receiver.async_set_sound_mode.assert_not_called()


async def test_sound_mode_select_option_fallback(mock_coordinator):
    """Test selecting sound mode using denonavr fallback command."""
    mock_coordinator.web_available = False
    mock_coordinator.sound_modes = None

    entity = SoundModeSelect(mock_coordinator)
    await entity.async_select_option("Direct")

    mock_coordinator.receiver.async_set_sound_mode.assert_awaited_once_with("Direct")
