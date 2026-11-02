"""Tests for DenonControlsCoordinator."""

from unittest.mock import MagicMock

from custom_components.denon_marantz_avr.const import CONTROLS_TELNET_EVENTS
from custom_components.denon_marantz_avr.coordinator import DenonControlsCoordinator
from denonavr.const import ALL_TELNET_EVENTS


def test_async_register_telnet_listener_events():
    """Test that async_register_telnet_listener only registers for control events."""
    receiver = MagicMock()
    coordinator = DenonControlsCoordinator(MagicMock(), receiver, "test_device_id")

    # Spy on async_set_updated_data
    coordinator.async_set_updated_data = MagicMock()

    # Register the telnet listener
    unregister = coordinator.async_register_telnet_listener()

    # Ensure ALL_TELNET_EVENTS was NOT registered
    registered_events = {
        call.args[0] for call in receiver.register_callback.call_args_list
    }
    assert ALL_TELNET_EVENTS not in registered_events
    assert registered_events == CONTROLS_TELNET_EVENTS

    # Verify callbacks passed are callable
    for call in receiver.register_callback.call_args_list:
        event, callback = call.args
        assert callable(callback)
        # Calling the callback should trigger async_set_updated_data
        coordinator.async_set_updated_data.reset_mock()
        callback("Main", event, "PARAM")
        coordinator.async_set_updated_data.assert_called_once_with(None)

    # Call unregister
    unregister()

    # Ensure all registered events were unregistered
    unregistered_events = {
        call.args[0] for call in receiver.unregister_callback.call_args_list
    }
    assert unregistered_events == CONTROLS_TELNET_EVENTS
