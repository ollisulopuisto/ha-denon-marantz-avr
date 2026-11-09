"""Tests for HEOS streaming source and favorite resolution."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from custom_components.denon_marantz_avr.heos import HeosStreaming
from custom_components.denon_marantz_avr.heos_media_player import HeosStreamingPlayer
from homeassistant.exceptions import HomeAssistantError


class MockMediaItem:
    """Mock MediaItem for testing inputs and favorites."""

    def __init__(self, name: str, media_id: str | None = None) -> None:
        self.name = name
        self.media_id = media_id


@pytest.fixture
def mock_heos_streaming():
    """Create HeosStreaming with populated favorites and input sources."""
    with patch("custom_components.denon_marantz_avr.heos.Heos"):
        streaming = HeosStreaming("192.168.1.100")
        streaming.inputs = [
            MockMediaItem(name="AUX", media_id="input/aux"),
            MockMediaItem(name="TV Audio", media_id="input/tv"),
            MockMediaItem(name="Optical", media_id="input/optical"),
        ]
        streaming.favorites = {
            1: MockMediaItem(name="Radio Paradise", media_id="fav/1"),
            2: MockMediaItem(name="BBC Radio 6", media_id="fav/2"),
            3: MockMediaItem(name="Jazz Groove", media_id="fav/3"),
        }
        streaming._rebuild_source_lookups()
        return streaming


def test_source_list(mock_heos_streaming):
    """Test source_list returns all favorites followed by inputs."""
    assert mock_heos_streaming.source_list() == [
        "Radio Paradise",
        "BBC Radio 6",
        "Jazz Groove",
        "AUX",
        "TV Audio",
        "Optical",
    ]


def test_favorite_index(mock_heos_streaming):
    """Test favorite_index returns 1-based index or None."""
    assert mock_heos_streaming.favorite_index("Radio Paradise") == 1
    assert mock_heos_streaming.favorite_index("BBC Radio 6") == 2
    assert mock_heos_streaming.favorite_index("Jazz Groove") == 3
    assert mock_heos_streaming.favorite_index("Nonexistent") is None
    assert mock_heos_streaming.favorite_index("AUX") is None


def test_input_source(mock_heos_streaming):
    """Test input_source returns the MediaItem for an input name in O(1) time."""
    aux = mock_heos_streaming.input_source("AUX")
    assert aux is not None
    assert aux.name == "AUX"
    assert aux.media_id == "input/aux"

    tv = mock_heos_streaming.input_source("TV Audio")
    assert tv is not None
    assert tv.name == "TV Audio"
    assert tv.media_id == "input/tv"

    assert mock_heos_streaming.input_source("Radio Paradise") is None
    assert mock_heos_streaming.input_source("Nonexistent") is None


def test_resolve_source_inputs(mock_heos_streaming):
    """Test resolve_source matches inputs by station or media_id."""
    # Match input by station name
    assert (
        mock_heos_streaming.resolve_source(
            station="AUX", media_id="other", album_id=None
        )
        == "AUX"
    )
    # Match input by media_id
    assert (
        mock_heos_streaming.resolve_source(
            station="Unknown Station", media_id="input/tv", album_id=None
        )
        == "TV Audio"
    )


def test_resolve_source_favorites(mock_heos_streaming):
    """Test resolve_source matches favorites by station name or album_id."""
    # Match favorite by station name
    assert (
        mock_heos_streaming.resolve_source(
            station="Radio Paradise", media_id=None, album_id=None
        )
        == "Radio Paradise"
    )
    # Match favorite by album_id (HEOS sets album_id for favorites)
    assert (
        mock_heos_streaming.resolve_source(
            station="Unknown Song", media_id=None, album_id="fav/2"
        )
        == "BBC Radio 6"
    )


def test_resolve_source_precedence(mock_heos_streaming):
    """Test input matches take precedence over favorite matches."""
    # Add a favorite with the same name as an input
    mock_heos_streaming.favorites[4] = MockMediaItem(name="AUX", media_id="fav/aux")
    mock_heos_streaming._rebuild_source_lookups()

    assert (
        mock_heos_streaming.resolve_source(station="AUX", media_id=None, album_id=None)
        == "AUX"
    )


def test_resolve_source_no_match(mock_heos_streaming):
    """Test resolve_source returns None when nothing matches."""
    assert (
        mock_heos_streaming.resolve_source(
            station="Spotify",
            media_id="spotify:track:123",
            album_id="spotify:album:456",
        )
        is None
    )
    assert (
        mock_heos_streaming.resolve_source(station=None, media_id=None, album_id=None)
        is None
    )


def test_heos_media_player_source_property(mock_heos_streaming):
    """Test HeosStreamingPlayer.source property uses the optimized resolution."""
    player_mock = MagicMock()
    now_playing = MagicMock()
    now_playing.station = "Radio Paradise"
    now_playing.media_id = "stream/123"
    now_playing.album_id = None
    player_mock.now_playing_media = now_playing
    mock_heos_streaming.player = player_mock

    player_entity = HeosStreamingPlayer(mock_heos_streaming, "test_device_id")
    assert player_entity.source == "Radio Paradise"

    # Test unknown station
    now_playing.station = "Unknown Track"
    now_playing.media_id = "unknown_media"
    now_playing.album_id = "fav/3"
    assert player_entity.source == "Jazz Groove"

    # Test completely unmatched
    now_playing.album_id = None
    assert player_entity.source is None


async def test_heos_media_player_async_select_source(mock_heos_streaming):
    """Test HeosStreamingPlayer.async_select_source selects favorite or input."""
    player_mock = MagicMock()
    player_mock.play_preset_station = MagicMock()
    player_mock.play_media = MagicMock()
    mock_heos_streaming.player = player_mock

    player_entity = HeosStreamingPlayer(mock_heos_streaming, "test_device_id")
    player_entity._run = AsyncMock()

    # Selecting a favorite should call play_preset_station
    await player_entity.async_select_source("Radio Paradise")
    assert player_entity._run.call_count == 1
    call_action, _coro = player_entity._run.call_args[0]
    assert call_action == "select source"

    # Selecting an input source should call play_media with the input MediaItem
    player_entity._run.reset_mock()
    await player_entity.async_select_source("TV Audio")
    assert player_entity._run.call_count == 1
    player_mock.play_media.assert_called_once_with(mock_heos_streaming.inputs[1])

    # Selecting an unknown source should raise HomeAssistantError
    with pytest.raises(HomeAssistantError, match="Unknown source: Unknown Input"):
        await player_entity.async_select_source("Unknown Input")
