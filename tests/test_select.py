"""Tests for select entities in denon_marantz_avr."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from custom_components.denon_marantz_avr.coordinator import DenonControlsCoordinator
from custom_components.denon_marantz_avr.select import (
    AudysseySelect,
    AudysseySelectDescription,
)


@pytest.fixture
def mock_coordinator():
    """Mock DenonControlsCoordinator."""
    coordinator = MagicMock(spec=DenonControlsCoordinator)
    coordinator.receiver = MagicMock()
    coordinator.receiver.audyssey = MagicMock()
    coordinator.receiver.soundmode = MagicMock()
    coordinator.device_id = "test_device_id"
    coordinator.web_available = False
    coordinator.sound_modes = None
    return coordinator


def test_audyssey_select_options_cached_at_init(mock_coordinator):
    """Test that AudysseySelect caches options at initialization and avoids repeated calls."""
    options_fn_mock = MagicMock(return_value=["Off", "Light", "Medium", "Heavy"])

    description = AudysseySelectDescription(
        key="dynamic_volume",
        translation_key="dynamic_volume",
        value_fn=lambda: "Off",
        options_fn=options_fn_mock,
        set_fn=AsyncMock(),
    )

    entity = AudysseySelect(mock_coordinator, description)

    # options_fn should have been called exactly once during __init__
    assert options_fn_mock.call_count == 1
    assert entity.options == ["Off", "Light", "Medium", "Heavy"]
    assert entity._attr_options == ["Off", "Light", "Medium", "Heavy"]

    # Accessing entity.options multiple times should NOT call options_fn again
    for _ in range(5):
        _ = entity.options

    assert options_fn_mock.call_count == 1


def test_audyssey_select_options_none_fallback(mock_coordinator):
    """Test that AudysseySelect handles None returned by options_fn."""
    options_fn_mock = MagicMock(return_value=None)

    description = AudysseySelectDescription(
        key="dynamic_volume",
        translation_key="dynamic_volume",
        value_fn=lambda: "Off",
        options_fn=options_fn_mock,
        set_fn=AsyncMock(),
    )

    entity = AudysseySelect(mock_coordinator, description)

    assert options_fn_mock.call_count == 1
    assert entity.options == []
    assert entity._attr_options == []


def test_audyssey_select_properties(mock_coordinator):
    """Test availability and current_option of AudysseySelect."""
    mock_coordinator.last_update_success = True
    mock_coordinator.receiver.audyssey.dynamic_eq = True
    description = AudysseySelectDescription(
        key="reference_level_offset",
        translation_key="reference_level_offset",
        value_fn=lambda: "0dB",
        options_fn=lambda: ["0dB", "+5dB", "+10dB", "+15dB"],
        set_fn=AsyncMock(),
    )

    entity = AudysseySelect(mock_coordinator, description)
    assert entity.current_option == "0dB"
    assert entity.available is True

    mock_coordinator.receiver.audyssey.dynamic_eq = False
    assert entity.available is False
