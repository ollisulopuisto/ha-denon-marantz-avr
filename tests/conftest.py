"""Shared fixtures for ha-denon-marantz-avr tests."""

import sys
import types
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Stub third-party packages that can't be installed in this environment:
#
#   homeassistant — requires Python 3.13.2+; only 3.11.x is available
#   denonavr      — needs netifaces C extension which requires gcc
#
# These stubs must be in sys.modules BEFORE any custom_components import.
# ---------------------------------------------------------------------------


# homeassistant.components.number
class _NumberEntity:
    """Minimal NumberEntity base class for testing."""

    _attr_should_poll = False
    _attr_name = None
    _attr_unique_id = None
    _attr_device_info = None
    _attr_icon = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)


_ha_number_mod = types.ModuleType("homeassistant.components.number")
_ha_number_mod.NumberEntity = _NumberEntity

sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
sys.modules.setdefault(
    "homeassistant.components", types.ModuleType("homeassistant.components")
)
sys.modules["homeassistant.components.number"] = _ha_number_mod
sys.modules.setdefault("homeassistant.core", types.ModuleType("homeassistant.core"))


# homeassistant.const (Platform enum used by const.py)
class _Platform:
    """Minimal stand-in for homeassistant.const.Platform."""

    MEDIA_PLAYER = "media_player"
    NUMBER = "number"
    BUTTON = "button"
    SELECT = "select"
    SWITCH = "switch"


_ha_const_mod = types.ModuleType("homeassistant.const")
_ha_const_mod.Platform = _Platform
sys.modules["homeassistant.const"] = _ha_const_mod

# homeassistant.helpers.update_coordinator & core
_ha_coord = types.ModuleType("homeassistant.helpers.update_coordinator")


class _DataUpdateCoordinator:
    def __init__(self, hass, logger, *, name, update_interval=None):
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval

    def __class_getitem__(cls, item):
        return cls

    def async_set_updated_data(self, data):
        pass


class _UpdateFailed(Exception):  # noqa: N818
    pass


_ha_coord.DataUpdateCoordinator = _DataUpdateCoordinator
_ha_coord.UpdateFailed = _UpdateFailed

_ha_core = types.ModuleType("homeassistant.core")
_ha_core.callback = lambda f: f

_ha_httpx = types.ModuleType("homeassistant.helpers.httpx_client")
_ha_httpx.get_async_client = MagicMock()

sys.modules.setdefault(
    "homeassistant.helpers", types.ModuleType("homeassistant.helpers")
)
sys.modules["homeassistant.helpers.update_coordinator"] = _ha_coord
sys.modules["homeassistant.core"] = _ha_core
sys.modules["homeassistant.helpers.httpx_client"] = _ha_httpx

# denonavr
_denonavr_const = types.ModuleType("denonavr.const")
_denonavr_const.POWER_ON = "ON"
_denonavr_const.ALL_TELNET_EVENTS = "ALL"

_denonavr_exc = types.ModuleType("denonavr.exceptions")


class _DenonAvrError(Exception):
    pass


_denonavr_exc.DenonAvrError = _DenonAvrError

sys.modules.setdefault("denonavr", types.ModuleType("denonavr"))
sys.modules["denonavr.const"] = _denonavr_const
sys.modules["denonavr.exceptions"] = _denonavr_exc

# ---------------------------------------------------------------------------
# Stub the custom_components.denon_marantz_avr *package* to bypass __init__.py,
# which uses Python 3.12 `type` statement syntax incompatible with 3.11.
# Python will still find and load individual submodules (const, channel_volume)
# from the real source directory via __path__.
# ---------------------------------------------------------------------------
import pathlib as _pathlib

_repo_root = _pathlib.Path(__file__).parent.parent
_pkg_path = [str(_repo_root / "custom_components" / "denon_marantz_avr")]

_cc_mod = types.ModuleType("custom_components")
_cc_mod.__path__ = [str(_repo_root / "custom_components")]  # type: ignore[attr-defined]
sys.modules.setdefault("custom_components", _cc_mod)

_pkg_mod = types.ModuleType("custom_components.denon_marantz_avr")
_pkg_mod.__path__ = _pkg_path  # type: ignore[attr-defined]
_pkg_mod.__package__ = "custom_components.denon_marantz_avr"
sys.modules["custom_components.denon_marantz_avr"] = _pkg_mod

# ---------------------------------------------------------------------------

from custom_components.denon_marantz_avr.channel_volume import (
    ChannelVolumeManager,
    ChannelVolumeNumber,
)
from custom_components.denon_marantz_avr.const import CHANNEL_MAP
from denonavr.const import POWER_ON


@pytest.fixture
def mock_receiver():
    """Return a mock DenonAVR receiver."""
    receiver = MagicMock()
    receiver.host = "192.168.1.100"
    receiver.power = POWER_ON
    receiver.telnet_connected = True
    receiver.telnet_healthy = True
    return receiver


@pytest.fixture
def manager(mock_receiver):
    """Return a ChannelVolumeManager for the Main zone."""
    return ChannelVolumeManager(
        receiver=mock_receiver,
        zone="Main",
        hass=MagicMock(),
        unique_id_base="test-serial",
    )


@pytest.fixture
def manager_zone2(mock_receiver):
    """Return a ChannelVolumeManager for Zone2."""
    return ChannelVolumeManager(
        receiver=mock_receiver,
        zone="Zone2",
        hass=MagicMock(),
        unique_id_base="test-serial",
    )


@pytest.fixture
def manager_with_entities(manager):
    """Return a manager with mock entities attached."""
    entities = {}
    for channel in CHANNEL_MAP:
        entity = MagicMock()
        entity.async_write_ha_state = MagicMock()
        entity.async_schedule_update_ha_state = MagicMock()
        entities[channel] = entity
    manager.entities = entities
    return manager, entities


@pytest.fixture
def channel_entity(manager):
    """Return a ChannelVolumeNumber entity for the FL channel."""
    return ChannelVolumeNumber(
        manager=manager,
        channel="FL",
        zone="Main",
        device_info={},
        unique_id_base="test-serial",
        device_name="Test Device",
    )
