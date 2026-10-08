"""Constants for Denon/Marantz AVR."""

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "denon_marantz_avr"

PLATFORMS = [
    Platform.MEDIA_PLAYER,
    Platform.NUMBER,
    Platform.BUTTON,
    Platform.SELECT,
    Platform.SWITCH,
]


CONF_SHOW_ALL_SOURCES = "show_all_sources"
CONF_ZONE2 = "zone2"
CONF_ZONE3 = "zone3"
CONF_MANUFACTURER = "manufacturer"
CONF_SERIAL_NUMBER = "serial_number"
CONF_UPDATE_AUDYSSEY = "update_audyssey"
CONF_USE_TELNET = "use_telnet"

DEFAULT_SHOW_SOURCES = False
DEFAULT_TIMEOUT = 5
DEFAULT_ZONE2 = False
DEFAULT_ZONE3 = False
DEFAULT_UPDATE_AUDYSSEY = False
DEFAULT_USE_TELNET = False

# Channel volume constants
CHANNEL_MAP = {
    "FL": "Front Left",
    "FR": "Front Right",
    "C": "Center",
    "SL": "Surround Left",
    "SR": "Surround Right",
    "SW": "Subwoofer",
}

# Channels the AVR-4520 reports in CV events but has no entity for
UNMAPPED_CHANNEL_CODES = frozenset(
    {"SBL", "SBR", "SB", "FHL", "FHR", "FWL", "FWR", "SW2"}
)

# Protocol value to dB conversion
# Protocol: 38-62 (integer), Display: -12.0 to +12.0 dB (float)
MIN_CHANNEL_VOLUME_DB = -12.0
MAX_CHANNEL_VOLUME_DB = 12.0
CHANNEL_VOLUME_STEP_DB = 0.5
MIN_CHANNEL_VOLUME_PROTOCOL = 38
MAX_CHANNEL_VOLUME_PROTOCOL = 62

# Telnet connection settings for CV commands
CV_TELNET_PORT = 23
CV_TELNET_TIMEOUT = 5.0

# Zone prefixes for multi-zone command prefixes
ZONE_PREFIXES = {
    "Main": "",
    "Zone2": "Z2",
    "Zone3": "Z3",
}

# Audyssey / Eco controls (from the denonavr-controls layer, now native)
CONTROLS_SCAN_INTERVAL = timedelta(seconds=30)
DEFAULT_POWER_OFF_DELAY = 5
DEFAULT_POWER_ON_DELAY = 12
ECO_MODE_OPTIONS = ["Off", "Auto", "On"]

# Speaker preset slots (the receiver exposes presets 1 and 2)
SPEAKER_PRESET_OPTIONS = ["1", "2"]

# Sound-mode categories ("genre") on the web API. The receiver reports the
# current category as a 1-based number; these are its labels in that order.
SOUND_CATEGORY_OPTIONS = ["Movie", "Music", "Game", "Pure"]

# Audio delay (ms) and sleep timer (minutes) ranges, per the denonavr protocol
MIN_DELAY_TIME_MS = 0
MAX_DELAY_TIME_MS = 999
MIN_SLEEP_MINUTES = 0
MAX_SLEEP_MINUTES = 120
