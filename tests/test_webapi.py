"""Tests for webapi module and SoundModeSettings."""

from custom_components.denon_marantz_avr.webapi import (
    SoundModeItem,
    SoundModeSettings,
    _parse_sound_modes,
)


def test_sound_mode_settings_properties_and_caching():
    """Test SoundModeSettings properties and caching behavior."""
    items = [
        SoundModeItem(index=1, name="Stereo", selected=False),
        SoundModeItem(index=2, name="Dolby Surround", selected=False),
        SoundModeItem(index=3, name="DTS Neural:X", selected=True),
        SoundModeItem(index=4, name="Direct", selected=False),
    ]
    settings = SoundModeSettings(genre=1, items=items)

    assert settings.genre == 1
    # Check that names returns correct list in order
    assert settings.names == ["Stereo", "Dolby Surround", "DTS Neural:X", "Direct"]
    # Verify cached_property identity (memoized list instance)
    assert settings.names is settings.names

    # Check current selected mode
    assert settings.current == "DTS Neural:X"
    assert settings.current is settings.current

    # Check index_for lookup
    assert settings.index_for("Stereo") == 1
    assert settings.index_for("DTS Neural:X") == 3
    assert settings.index_for("Nonexistent") is None
    # Check that underlying _indices is cached
    assert settings._indices is settings._indices


def test_sound_mode_settings_no_selection():
    """Test SoundModeSettings when no item is selected."""
    items = [
        SoundModeItem(index=1, name="Stereo", selected=False),
        SoundModeItem(index=2, name="Direct", selected=False),
    ]
    settings = SoundModeSettings(genre=None, items=items)
    assert settings.genre is None
    assert settings.current is None
    assert settings.index_for("Stereo") == 1


def test_parse_sound_modes():
    """Test XML parsing of SoundModeSettings."""
    xml_data = """<SoundModeSettings>
      <Genre>2</Genre>
      <SoundMode>
        <List>
          <Item index="1" selected="2">Stereo</Item>
          <Item index="2" selected="1">Dolby Surround</Item>
        </List>
      </SoundMode>
    </SoundModeSettings>"""
    settings = _parse_sound_modes(xml_data)
    assert settings is not None
    assert settings.genre == 2
    assert settings.names == ["Stereo", "Dolby Surround"]
    assert settings.current == "Dolby Surround"
    assert settings.index_for("Dolby Surround") == 2
    assert settings.index_for("Stereo") == 1


def test_parse_sound_modes_invalid():
    """Test XML parsing with invalid inputs."""
    assert _parse_sound_modes("invalid xml") is None
    assert _parse_sound_modes("<OtherRoot></OtherRoot>") is None
    assert _parse_sound_modes("<SoundModeSettings></SoundModeSettings>") is None
