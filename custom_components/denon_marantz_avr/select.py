"""Select entities for the Denon/Marantz AVR controls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, get_args

from denonavr.const import (
    AudioRestorers,
    BluetoothOutputModes,
    DialogEnhancerLevels,
    DRCs,
    MDAXs,
)
from homeassistant.components.select import SelectEntity, SelectEntityDescription

from .const import (
    CONF_USE_TELNET,
    DEFAULT_USE_TELNET,
    ECO_MODE_OPTIONS,
    SOUND_CATEGORY_OPTIONS,
    SPEAKER_PRESET_OPTIONS,
)
from .entity import DenonControlsEntity

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import DenonavrConfigEntry
    from .coordinator import DenonControlsCoordinator
    from .webapi import SoundModeSettings


@dataclass(frozen=True, kw_only=True)
class AudysseySelectDescription(SelectEntityDescription):
    """Describe an Audyssey select."""

    value_fn: Callable[[], str | None]
    options_fn: Callable[[], list[str]]
    set_fn: Callable[[str], Awaitable[None]]


@dataclass(frozen=True, kw_only=True)
class AvrSelectDescription(SelectEntityDescription):
    """
    Describe a receiver setting exposed as a select.

    ``options`` and the current value both come from the ``denonavr`` library
    so nothing is hard-coded here, and the entity is only created when the
    receiver actually reports a value for the setting (see ``async_setup_entry``).
    """

    option_list: list[str]
    value_fn: Callable[[], str | None]
    set_fn: Callable[[str], Awaitable[None]]


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: DenonavrConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up receiver select controls."""
    coordinator = entry.runtime_data.controls
    receiver = coordinator.receiver
    audyssey = receiver.audyssey
    # Dialog Enhancer, M-DAX and DRC live on the sound-mode sub-component,
    # not on the top-level receiver facade.
    soundmode = receiver.soundmode

    entities: list[SelectEntity] = [
        AudysseySelect(coordinator, description)
        for description in (
            AudysseySelectDescription(
                key="dynamic_volume",
                translation_key="dynamic_volume",
                value_fn=lambda: audyssey.dynamic_volume,
                options_fn=lambda: audyssey.dynamic_volume_setting_list,
                set_fn=audyssey.async_set_dynamicvol,
            ),
            AudysseySelectDescription(
                key="reference_level_offset",
                translation_key="reference_level_offset",
                value_fn=lambda: audyssey.reference_level_offset,
                options_fn=lambda: audyssey.reference_level_offset_setting_list,
                set_fn=audyssey.async_set_reflevoffset,
            ),
            AudysseySelectDescription(
                key="multi_eq",
                translation_key="multi_eq",
                value_fn=lambda: audyssey.multi_eq,
                options_fn=lambda: audyssey.multi_eq_setting_list,
                set_fn=audyssey.async_set_multieq,
            ),
        )
    ]
    entities.append(EcoModeSelect(coordinator))

    # Receiver settings pushed over Telnet. These arrive asynchronously over
    # several seconds after connect, so gating on the instantaneous value is
    # racy; instead create them when Telnet is enabled (the transport that
    # carries them), restricting the brand-specific ones. Each shows "unknown"
    # until the receiver reports its value.
    avr_descriptions = (
        AvrSelectDescription(
            key="dialog_enhancer",
            translation_key="dialog_enhancer",
            option_list=list(get_args(DialogEnhancerLevels)),
            value_fn=lambda: soundmode.dialog_enhancer,
            set_fn=soundmode.async_dialog_enhancer,
        ),
        AvrSelectDescription(
            key="mdax",
            translation_key="mdax",
            option_list=list(get_args(MDAXs)),
            value_fn=lambda: soundmode.mdax,
            set_fn=soundmode.async_mdax,
        ),
        AvrSelectDescription(
            key="audio_restorer",
            translation_key="audio_restorer",
            option_list=list(get_args(AudioRestorers)),
            value_fn=lambda: receiver.audio_restorer,
            set_fn=receiver.async_audio_restorer,
        ),
        AvrSelectDescription(
            key="drc",
            translation_key="drc",
            option_list=list(get_args(DRCs)),
            value_fn=lambda: soundmode.drc,
            set_fn=soundmode.async_drc,
        ),
        AvrSelectDescription(
            key="bt_output_mode",
            translation_key="bt_output_mode",
            option_list=list(get_args(BluetoothOutputModes)),
            value_fn=lambda: receiver.bt_output_mode,
            set_fn=receiver.async_bt_output_mode,
        ),
        AvrSelectDescription(
            key="speaker_preset",
            translation_key="speaker_preset",
            option_list=list(SPEAKER_PRESET_OPTIONS),
            value_fn=lambda: (
                None
                if receiver.speaker_preset is None
                else str(receiver.speaker_preset)
            ),
            set_fn=lambda option: receiver.async_speaker_preset(int(option)),
        ),
    )
    if entry.options.get(CONF_USE_TELNET, DEFAULT_USE_TELNET):
        manufacturer = (receiver.manufacturer or "").lower()
        is_marantz = "marantz" in manufacturer
        is_denon = "denon" in manufacturer
        include = {"dialog_enhancer", "drc", "bt_output_mode", "speaker_preset"}
        # M-DAX is Marantz-only, Audio Restorer is Denon-only; include both
        # when the manufacturer is unknown so nothing is missed.
        if is_marantz or not is_denon:
            include.add("mdax")
        if is_denon or not is_marantz:
            include.add("audio_restorer")
        entities.extend(
            AvrSelect(coordinator, description)
            for description in avr_descriptions
            if description.key in include
        )

    # Sound-mode category (genre), from the web API, when the receiver
    # reports one.
    if (
        coordinator.web_available
        and coordinator.sound_modes is not None
        and coordinator.sound_modes.genre is not None
    ):
        entities.append(SoundCategorySelect(coordinator))

    # Sound mode as a stand-alone dropdown (in addition to the media player's
    # own control). Prefer the real device-reported list from the web API, and
    # fall back to the denonavr list on receivers without the web API.
    web_modes = (
        coordinator.sound_modes
        if coordinator.web_available and coordinator.sound_modes is not None
        else None
    )
    if (web_modes is not None and web_modes.names) or receiver.sound_mode_list:
        entities.append(SoundModeSelect(coordinator))

    async_add_entities(entities)


class AudysseySelect(DenonControlsEntity, SelectEntity):
    """Represent an Audyssey setting."""

    def __init__(
        self,
        coordinator: DenonControlsCoordinator,
        description: AudysseySelectDescription,
    ) -> None:
        """Initialize an Audyssey select."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_translation_key = description.translation_key

    @property
    def available(self) -> bool:
        """Return whether this setting can currently be changed."""
        if self.entity_description.key == "reference_level_offset":
            return (
                super().available
                and self.coordinator.receiver.audyssey.dynamic_eq is True
            )
        return super().available

    @property
    def current_option(self) -> str | None:
        """Return the current setting."""
        return self.entity_description.value_fn()

    @property
    def options(self) -> list[str]:
        """Return available settings."""
        return self.entity_description.options_fn() or []

    async def async_select_option(self, option: str) -> None:
        """Change the setting."""
        if self.entity_description.key == "reference_level_offset":
            await self.coordinator.async_request_refresh()
        await self.coordinator.async_run_command(
            lambda: self.entity_description.set_fn(option)
        )


class EcoModeSelect(DenonControlsEntity, SelectEntity):
    """Display and control the receiver's Eco mode."""

    _attr_translation_key = "eco_mode"
    _attr_options = ECO_MODE_OPTIONS

    def __init__(self, coordinator: DenonControlsCoordinator) -> None:
        """Initialize the Eco mode select."""
        super().__init__(coordinator, "eco_mode")

    @property
    def current_option(self) -> str | None:
        """Return the current Eco mode."""
        return self.coordinator.receiver.eco_mode

    async def async_select_option(self, option: str) -> None:
        """Change the Eco mode."""
        await self.coordinator.async_set_eco_mode(option)


class AvrSelect(DenonControlsEntity, SelectEntity):
    """Represent a receiver setting backed by the denonavr library."""

    def __init__(
        self,
        coordinator: DenonControlsCoordinator,
        description: AvrSelectDescription,
    ) -> None:
        """Initialize the select."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_translation_key = description.translation_key
        self._attr_options = list(description.option_list)

    @property
    def current_option(self) -> str | None:
        """Return the current setting."""
        return self.entity_description.value_fn()

    async def async_select_option(self, option: str) -> None:
        """Change the setting."""
        await self.coordinator.async_send(
            lambda: self.entity_description.set_fn(option)
        )


class SoundCategorySelect(DenonControlsEntity, SelectEntity):
    """
    Select the sound-mode category (genre) via the web API.

    The receiver groups its surround modes into categories; picking one
    changes which modes the media player then offers.
    """

    _attr_translation_key = "sound_category"
    _attr_options = SOUND_CATEGORY_OPTIONS

    def __init__(self, coordinator: DenonControlsCoordinator) -> None:
        """Initialize the sound category select."""
        super().__init__(coordinator, "sound_category")

    @property
    def current_option(self) -> str | None:
        """Return the current category name."""
        settings = self.coordinator.sound_modes
        if settings is None or settings.genre is None:
            return None
        index = settings.genre - 1
        if 0 <= index < len(SOUND_CATEGORY_OPTIONS):
            return SOUND_CATEGORY_OPTIONS[index]
        return None

    async def async_select_option(self, option: str) -> None:
        """Change the sound category."""
        index = SOUND_CATEGORY_OPTIONS.index(option) + 1
        await self.coordinator.async_set_sound_category(index)


class SoundModeSelect(DenonControlsEntity, SelectEntity):
    """
    Select the active sound mode as a stand-alone dropdown.

    Mirrors the media player's sound-mode control. It prefers the real,
    device-reported list from the web API (only the modes actually available
    for the current input) and falls back to the ``denonavr`` list on
    receivers without that API.
    """

    _attr_translation_key = "sound_mode"

    def __init__(self, coordinator: DenonControlsCoordinator) -> None:
        """Initialize the sound mode select."""
        super().__init__(coordinator, "sound_mode")

    @property
    def _web_modes(self) -> SoundModeSettings | None:
        """Return the web-API sound modes when they are usable."""
        settings = self.coordinator.sound_modes
        if self.coordinator.web_available and settings is not None and settings.names:
            return settings
        return None

    @property
    def options(self) -> list[str]:
        """Return the selectable sound modes."""
        web = self._web_modes
        if web is not None:
            return list(web.names)
        return list(self.coordinator.receiver.sound_mode_list or [])

    @property
    def current_option(self) -> str | None:
        """Return the current sound mode."""
        web = self._web_modes
        if web is not None:
            return web.current
        return self.coordinator.receiver.sound_mode

    async def async_select_option(self, option: str) -> None:
        """Change the sound mode."""
        web = self._web_modes
        if web is not None:
            index = web.index_for(option)
            if index is not None:
                await self.coordinator.async_set_sound_mode(index)
                return
        await self.coordinator.async_send(
            lambda: self.coordinator.receiver.async_set_sound_mode(option)
        )
