"""
HEOS network-streaming media player (optional).

A dedicated media player for the receiver's HEOS Built-in player, attached
to the same Home Assistant device as the AVR media player. It provides the
streaming side the AVR control interface does not: rich now-playing,
transport, favorites / inputs and media browsing.

Ported and trimmed from Home Assistant's official ``heos`` integration
(grouping, queue management and account sign-in are intentionally left out;
see that integration for the full HEOS system experience).
"""

from __future__ import annotations

import logging
from contextlib import suppress
from functools import reduce
from operator import ior
from typing import TYPE_CHECKING, Any

from homeassistant.components import media_source
from homeassistant.components.media_player import (
    ATTR_MEDIA_ENQUEUE,
    BrowseError,
    BrowseMedia,
    MediaClass,
    MediaPlayerEnqueue,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
    RepeatMode,
    async_process_play_media_url,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.util.dt import utcnow
from pyheos import (
    AddCriteriaType,
    ControlType,
    HeosError,
    MediaItem,
    MediaMusicSource,
    PlayState,
    RepeatType,
)
from pyheos import (
    MediaType as HeosMediaType,
)
from pyheos import (
    const as heos_const,
)
from pyheos.util import mediauri as heos_source

from .const import DOMAIN

if TYPE_CHECKING:
    from datetime import datetime

    from .heos import HeosStreaming

_LOGGER = logging.getLogger(__name__)

BROWSE_ROOT = "heos://media"

BASE_SUPPORTED_FEATURES = (
    MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_STEP
    | MediaPlayerEntityFeature.SELECT_SOURCE
    | MediaPlayerEntityFeature.PLAY_MEDIA
    | MediaPlayerEntityFeature.BROWSE_MEDIA
    | MediaPlayerEntityFeature.MEDIA_ENQUEUE
)

PLAY_STATE_TO_STATE = {
    None: MediaPlayerState.IDLE,
    PlayState.UNKNOWN: MediaPlayerState.IDLE,
    PlayState.PLAY: MediaPlayerState.PLAYING,
    PlayState.STOP: MediaPlayerState.IDLE,
    PlayState.PAUSE: MediaPlayerState.PAUSED,
}

CONTROL_TO_SUPPORT = {
    ControlType.PLAY: MediaPlayerEntityFeature.PLAY,
    ControlType.PAUSE: MediaPlayerEntityFeature.PAUSE,
    ControlType.STOP: MediaPlayerEntityFeature.STOP,
    ControlType.PLAY_PREVIOUS: MediaPlayerEntityFeature.PREVIOUS_TRACK,
    ControlType.PLAY_NEXT: MediaPlayerEntityFeature.NEXT_TRACK,
}

HA_HEOS_ENQUEUE_MAP = {
    None: AddCriteriaType.REPLACE_AND_PLAY,
    MediaPlayerEnqueue.ADD: AddCriteriaType.ADD_TO_END,
    MediaPlayerEnqueue.REPLACE: AddCriteriaType.REPLACE_AND_PLAY,
    MediaPlayerEnqueue.NEXT: AddCriteriaType.PLAY_NEXT,
    MediaPlayerEnqueue.PLAY: AddCriteriaType.PLAY_NOW,
}

HEOS_HA_REPEAT_TYPE_MAP = {
    RepeatType.OFF: RepeatMode.OFF,
    RepeatType.ON_ALL: RepeatMode.ALL,
    RepeatType.ON_ONE: RepeatMode.ONE,
}
HA_HEOS_REPEAT_TYPE_MAP = {v: k for k, v in HEOS_HA_REPEAT_TYPE_MAP.items()}

HEOS_MEDIA_TYPE_TO_MEDIA_CLASS = {
    HeosMediaType.ALBUM: MediaClass.ALBUM,
    HeosMediaType.ARTIST: MediaClass.ARTIST,
    HeosMediaType.CONTAINER: MediaClass.DIRECTORY,
    HeosMediaType.GENRE: MediaClass.GENRE,
    HeosMediaType.HEOS_SERVER: MediaClass.DIRECTORY,
    HeosMediaType.HEOS_SERVICE: MediaClass.DIRECTORY,
    HeosMediaType.MUSIC_SERVICE: MediaClass.DIRECTORY,
    HeosMediaType.PLAYLIST: MediaClass.PLAYLIST,
    HeosMediaType.SONG: MediaClass.TRACK,
    HeosMediaType.STATION: MediaClass.TRACK,
}


class HeosStreamingPlayer(MediaPlayerEntity):
    """The receiver's HEOS network-streaming player."""

    _attr_has_entity_name = True
    _attr_translation_key = "streaming"
    _attr_media_content_type = MediaType.MUSIC
    _attr_media_image_remotely_accessible = True
    _attr_supported_features = BASE_SUPPORTED_FEATURES

    def __init__(self, streaming: HeosStreaming, device_id: str) -> None:
        """Initialize the streaming player."""
        self._streaming = streaming
        self._player = streaming.player
        self._media_position_updated_at: datetime | None = None
        self._attr_unique_id = f"{device_id}-heos"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, device_id)})

    async def async_added_to_hass(self) -> None:
        """Subscribe to HEOS player events."""
        self._update_attributes()
        self.async_on_remove(self._player.add_on_player_event(self._on_player_event))
        self.async_on_remove(self._streaming.heos.add_on_connected(self._on_connected))
        self.async_on_remove(
            self._streaming.heos.add_on_disconnected(self._on_disconnected)
        )

    async def _on_player_event(self, event: str) -> None:
        if event == heos_const.EVENT_PLAYER_NOW_PLAYING_PROGRESS:
            self._media_position_updated_at = utcnow()
        self._update_attributes()
        self.async_write_ha_state()

    async def _on_connected(self) -> None:
        self._update_attributes()
        self.async_write_ha_state()

    async def _on_disconnected(self) -> None:
        self.async_write_ha_state()

    def _update_attributes(self) -> None:
        """Recompute source list and supported features."""
        self._attr_source_list = self._streaming.source_list()
        self._attr_repeat = HEOS_HA_REPEAT_TYPE_MAP.get(self._player.repeat)
        controls = self._player.now_playing_media.supported_controls
        current = [CONTROL_TO_SUPPORT[c] for c in controls if c in CONTROL_TO_SUPPORT]
        features = reduce(ior, current, BASE_SUPPORTED_FEATURES)
        if (
            MediaPlayerEntityFeature.NEXT_TRACK in features
            and MediaPlayerEntityFeature.PREVIOUS_TRACK in features
        ):
            features |= (
                MediaPlayerEntityFeature.REPEAT_SET
                | MediaPlayerEntityFeature.SHUFFLE_SET
            )
        self._attr_supported_features = features

    @property
    def available(self) -> bool:
        """Return whether the HEOS connection is up."""
        return self._streaming.connected

    @property
    def state(self) -> MediaPlayerState:
        """Return the play state."""
        return PLAY_STATE_TO_STATE[self._player.state]

    @property
    def volume_level(self) -> float:
        """Return the volume level (0..1)."""
        return self._player.volume / 100

    @property
    def is_volume_muted(self) -> bool:
        """Return whether the player is muted."""
        return self._player.is_muted

    @property
    def shuffle(self) -> bool:
        """Return whether shuffle is enabled."""
        return self._player.shuffle

    @property
    def source(self) -> str | None:
        """Return the current source name (favorite/input) if matched."""
        # Performance optimization: Use O(1) hash map lookup instead of
        # linear O(N) scans over inputs and favorites on every state read.
        now = self._player.now_playing_media
        return self._streaming.resolve_source(
            station=now.station,
            media_id=now.media_id,
            album_id=now.album_id,
        )

    @property
    def media_title(self) -> str | None:
        """Return the current track title."""
        return self._player.now_playing_media.song

    @property
    def media_artist(self) -> str | None:
        """Return the current artist."""
        return self._player.now_playing_media.artist

    @property
    def media_album_name(self) -> str | None:
        """Return the current album."""
        return self._player.now_playing_media.album

    @property
    def media_content_id(self) -> str | None:
        """Return the current media id."""
        return self._player.now_playing_media.media_id

    @property
    def media_image_url(self) -> str | None:
        """Return the current cover-art URL."""
        return self._player.now_playing_media.image_url or None

    @property
    def media_duration(self) -> int | None:
        """Return the media duration in seconds."""
        duration = self._player.now_playing_media.duration
        return int(duration / 1000) if isinstance(duration, int) else None

    @property
    def media_position(self) -> int | None:
        """Return the media position in seconds."""
        if not self._player.now_playing_media.duration:
            return None
        position = self._player.now_playing_media.current_position
        return int(position / 1000) if isinstance(position, int) else None

    @property
    def media_position_updated_at(self) -> datetime | None:
        """Return when the media position was last valid."""
        if not self._player.now_playing_media.duration:
            return None
        return self._media_position_updated_at

    async def async_media_play(self) -> None:
        """Send play."""
        await self._run("play", self._player.play())

    async def async_media_pause(self) -> None:
        """Send pause."""
        await self._run("pause", self._player.pause())

    async def async_media_stop(self) -> None:
        """Send stop."""
        await self._run("stop", self._player.stop())

    async def async_media_next_track(self) -> None:
        """Send next track."""
        await self._run("next", self._player.play_next())

    async def async_media_previous_track(self) -> None:
        """Send previous track."""
        await self._run("previous", self._player.play_previous())

    async def async_mute_volume(self, mute: bool) -> None:  # noqa: FBT001
        """Mute or unmute."""
        await self._run("mute", self._player.set_mute(mute))

    async def async_set_volume_level(self, volume: float) -> None:
        """Set the volume level."""
        await self._run("volume", self._player.set_volume(int(volume * 100)))

    async def async_set_shuffle(self, shuffle: bool) -> None:  # noqa: FBT001
        """Enable/disable shuffle."""
        await self._run(
            "shuffle", self._player.set_play_mode(self._player.repeat, shuffle)
        )

    async def async_set_repeat(self, repeat: RepeatMode) -> None:
        """Set the repeat mode."""
        await self._run(
            "repeat",
            self._player.set_play_mode(
                HA_HEOS_REPEAT_TYPE_MAP[repeat], self._player.shuffle
            ),
        )

    async def async_select_source(self, source: str) -> None:
        """Play a favorite or an input source by name."""
        index = self._streaming.favorite_index(source)
        if index is not None:
            await self._run("select source", self._player.play_preset_station(index))
            return
        # Performance optimization: Use O(1) hash map lookup instead of
        # linear O(N) iteration over streaming inputs.
        if (input_source := self._streaming.input_source(source)) is not None:
            await self._run("select source", self._player.play_media(input_source))
            return
        msg = f"Unknown source: {source}"
        raise HomeAssistantError(msg)

    async def async_play_media(
        self, media_type: MediaType | str, media_id: str, **kwargs: Any
    ) -> None:
        """Play media (favorite, URL, media-source or HEOS browse item)."""
        enqueue = HA_HEOS_ENQUEUE_MAP[kwargs.get(ATTR_MEDIA_ENQUEUE)]
        if heos_source.is_media_uri(media_id):
            media, _data = heos_source.from_media_uri(media_id)
            if not isinstance(media, MediaItem):
                msg = f"Invalid media id: {media_id}"
                raise HomeAssistantError(msg)
            await self._run("play media", self._player.play_media(media, enqueue))
            return
        if media_source.is_media_source_id(media_id):
            play_item = await media_source.async_resolve_media(
                self.hass, media_id, self.entity_id
            )
            url = async_process_play_media_url(self.hass, play_item.url)
            await self._run("play url", self._player.play_url(url))
            return
        if media_type in {MediaType.URL, MediaType.MUSIC}:
            url = async_process_play_media_url(self.hass, media_id)
            await self._run("play url", self._player.play_url(url))
            return
        if media_type == "favorite":
            try:
                index = int(media_id)
            except ValueError:
                index = self._streaming.favorite_index(media_id)
            if index is None:
                msg = f"Invalid favorite: {media_id}"
                raise HomeAssistantError(msg)
            await self._run("play favorite", self._player.play_preset_station(index))
            return
        msg = f"Unsupported media type: {media_type}"
        raise HomeAssistantError(msg)

    async def async_browse_media(
        self,
        media_content_type: MediaType | str | None = None,
        media_content_id: str | None = None,
    ) -> BrowseMedia:
        """Browse HEOS music sources and media-source items."""
        if media_content_id in (None, BROWSE_ROOT):
            return await self._async_browse_root()
        if heos_source.is_media_uri(media_content_id):
            media, _data = heos_source.from_media_uri(media_content_id)
            browse_media = _media_to_browse_media(media)
            with suppress(HeosError):
                result = await self._streaming.heos.browse_media(media)
                browse_media.children = [
                    _media_to_browse_media(item)
                    for item in result.items
                    if item.browsable or item.playable
                ]
            return browse_media
        if media_source.is_media_source_id(media_content_id):
            return await self._async_browse_media_source(media_content_id)
        msg = f"Unsupported media content id: {media_content_id}"
        raise HomeAssistantError(msg)

    async def _async_browse_root(self) -> BrowseMedia:
        heos = self._streaming.heos
        if not heos.music_sources:
            with suppress(HeosError):
                await heos.get_music_sources()
        children: list[BrowseMedia] = [
            _media_to_browse_media(source)
            for source in heos.music_sources.values()
            if source.available or source.source_id == heos_const.MUSIC_SOURCE_TUNEIN
        ]
        root = BrowseMedia(
            title="Music Sources",
            media_class=MediaClass.DIRECTORY,
            children_media_class=MediaClass.DIRECTORY,
            media_content_type="",
            media_content_id=BROWSE_ROOT,
            can_expand=True,
            can_play=False,
            children=children,
        )
        with suppress(BrowseError):
            browse = await self._async_browse_media_source()
            if browse.domain is None and browse.children:
                children.extend(browse.children)
            else:
                children.append(browse)
        return root

    async def _async_browse_media_source(
        self, media_content_id: str | None = None
    ) -> BrowseMedia:
        return await media_source.async_browse_media(
            self.hass,
            media_content_id,
            content_filter=lambda item: item.media_content_type.startswith("audio/"),
        )

    async def _run(self, action: str, coro: Any) -> None:
        """Await a HEOS coroutine, surfacing errors to Home Assistant."""
        try:
            await coro
        except HeosError as err:
            msg = f"Unable to {action}: {err}"
            raise HomeAssistantError(msg) from err


def _media_to_browse_media(media: MediaItem | MediaMusicSource) -> BrowseMedia:
    """Convert a HEOS media item to a Home Assistant browse item."""
    if isinstance(media, MediaMusicSource):
        can_expand = (
            media.source_id == heos_const.MUSIC_SOURCE_TUNEIN or media.available
        )
        can_play = False
    else:
        can_expand = media.browsable
        can_play = media.playable
    return BrowseMedia(
        can_expand=can_expand,
        can_play=can_play,
        media_content_id=heos_source.to_media_uri(media),
        media_content_type="",
        media_class=HEOS_MEDIA_TYPE_TO_MEDIA_CLASS[media.type],
        title=media.name,
        thumbnail=media.image_url,
    )
