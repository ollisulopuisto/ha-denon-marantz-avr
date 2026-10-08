"""Tests for channel_volume module."""

import logging

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.denon_marantz_avr.channel_volume import (
    ChannelVolumeNumber,
    db_to_protocol,
    protocol_to_db,
)

try:
    from denonavr.const import POWER_ON
except ImportError:
    POWER_ON = "ON"


# ---------------------------------------------------------------------------
# protocol_to_db
# ---------------------------------------------------------------------------


class TestProtocolToDb:
    @pytest.mark.parametrize(
        ("protocol_value", "expected"),
        [
            ("50", 0.0),
            ("53", 3.0),
            ("535", 3.5),
            ("38", -12.0),
            ("62", 12.0),
            ("49", -1.0),
            ("495", -0.5),
            ("505", 0.5),
            ("51", 1.0),
        ],
    )
    def test_known_values(self, protocol_value, expected):
        assert protocol_to_db(protocol_value) == expected

    def test_strips_whitespace(self):
        assert protocol_to_db("  53  ") == 3.0

    def test_custom_offset(self):
        assert protocol_to_db("30", offset=30) == 0.0


# ---------------------------------------------------------------------------
# db_to_protocol
# ---------------------------------------------------------------------------


class TestDbToProtocol:
    @pytest.mark.parametrize(
        ("db_value", "expected"),
        [
            (0.0, "50"),
            (3.0, "53"),
            (3.5, "535"),
            (-12.0, "38"),
            (12.0, "62"),
            (-1.0, "49"),
            (-0.5, "495"),
            (0.5, "505"),
            (1.0, "51"),
        ],
    )
    def test_known_values(self, db_value, expected):
        assert db_to_protocol(db_value) == expected

    def test_custom_offset(self):
        assert db_to_protocol(0.0, offset=100) == "100"


# ---------------------------------------------------------------------------
# Roundtrip
# ---------------------------------------------------------------------------


class TestRoundtrip:
    @pytest.mark.parametrize(
        "db_value",
        [v / 2 for v in range(-24, 25)],  # -12.0 to +12.0 in 0.5 steps
    )
    def test_roundtrip(self, db_value):
        assert protocol_to_db(db_to_protocol(db_value)) == db_value


# ---------------------------------------------------------------------------
# ChannelVolumeManager._cv_callback
# ---------------------------------------------------------------------------


class TestCvCallback:
    def test_pending_counter_blocks_update(self, manager_with_entities):
        manager, entities = manager_with_entities
        manager.pending_counters["FL"] = 1

        manager._cv_callback("Main", "CV", "FL 53")

        entities["FL"].async_write_ha_state.assert_not_called()
        assert manager.pending_counters["FL"] == 0

    def test_counter_decremented_once(self, manager_with_entities):
        manager, entities = manager_with_entities
        manager.pending_counters["FL"] = 2

        manager._cv_callback("Main", "CV", "FL 53")
        assert manager.pending_counters["FL"] == 1
        entities["FL"].async_write_ha_state.assert_not_called()

        manager._cv_callback("Main", "CV", "FL 53")
        assert manager.pending_counters["FL"] == 0
        entities["FL"].async_write_ha_state.assert_not_called()

        # Third event goes through
        manager._cv_callback("Main", "CV", "FL 53")
        entities["FL"].async_write_ha_state.assert_called_once()

    def test_channel_specific_counters(self, manager_with_entities):
        manager, entities = manager_with_entities
        manager.pending_counters["FL"] = 1
        manager.pending_counters["FR"] = 0

        manager._cv_callback("Main", "CV", "FL 53")
        manager._cv_callback("Main", "CV", "FR 53")

        entities["FL"].async_write_ha_state.assert_not_called()
        entities["FR"].async_write_ha_state.assert_called_once()

    def test_wrong_zone_ignored(self, manager_with_entities):
        manager, entities = manager_with_entities

        manager._cv_callback("Zone2", "CV", "FL 53")

        for entity in entities.values():
            entity.async_write_ha_state.assert_not_called()

    def test_all_zones_accepted(self, manager_with_entities):
        manager, entities = manager_with_entities

        manager._cv_callback("ALL_ZONES", "CV", "FL 53")

        entities["FL"].async_write_ha_state.assert_called_once()
        assert manager.channel_volumes["FL"] == 3.0

    def test_end_parameter_ignored(self, manager_with_entities):
        manager, entities = manager_with_entities

        manager._cv_callback("Main", "CV", "END")

        for entity in entities.values():
            entity.async_write_ha_state.assert_not_called()

    def test_empty_parameter_ignored(self, manager_with_entities):
        manager, entities = manager_with_entities

        manager._cv_callback("Main", "CV", "  ")

        for entity in entities.values():
            entity.async_write_ha_state.assert_not_called()

    def test_malformed_parameter_ignored(self, manager_with_entities):
        manager, entities = manager_with_entities

        manager._cv_callback("Main", "CV", "FL")  # Missing value

        for entity in entities.values():
            entity.async_write_ha_state.assert_not_called()

    def test_unknown_channel_ignored(self, manager_with_entities):
        manager, entities = manager_with_entities

        manager._cv_callback("Main", "CV", "XX 50")

        for entity in entities.values():
            entity.async_write_ha_state.assert_not_called()

    def test_half_db_value_parsed(self, manager_with_entities):
        manager, entities = manager_with_entities

        manager._cv_callback("Main", "CV", "FL 535")

        assert manager.channel_volumes["FL"] == 3.5
        entities["FL"].async_write_ha_state.assert_called_once()

    def test_volume_state_updated(self, manager_with_entities):
        manager, _ = manager_with_entities

        manager._cv_callback("Main", "CV", "FR 495")

        assert manager.channel_volumes["FR"] == -0.5

    def test_zone2_manager_accepts_zone2(self, manager_zone2):
        entity = MagicMock()
        entity.async_write_ha_state = MagicMock()
        manager_zone2.entities["FL"] = entity

        manager_zone2._cv_callback("Zone2", "CV", "FL 53")

        entity.async_write_ha_state.assert_called_once()
        assert manager_zone2.channel_volumes["FL"] == 3.0

    def test_zone2_manager_ignores_main(self, manager_zone2):
        entity = MagicMock()
        entity.async_write_ha_state = MagicMock()
        manager_zone2.entities["FL"] = entity

        manager_zone2._cv_callback("Main", "CV", "FL 53")

        entity.async_write_ha_state.assert_not_called()


# ---------------------------------------------------------------------------
# ChannelVolumeManager._power_callback
# ---------------------------------------------------------------------------


class TestPowerCallback:
    def test_power_change_triggers_entity_update(
        self, manager_with_entities, mock_receiver
    ):
        manager, entities = manager_with_entities
        mock_receiver.power = "STANDBY"
        manager._last_power_state = POWER_ON

        manager._power_callback("Main", "ZM", "STANDBY")

        for entity in entities.values():
            entity.async_schedule_update_ha_state.assert_called_once_with(
                force_refresh=True
            )

    def test_no_change_no_update(self, manager_with_entities, mock_receiver):
        manager, entities = manager_with_entities
        mock_receiver.power = POWER_ON
        manager._last_power_state = POWER_ON

        manager._power_callback("Main", "ZM", POWER_ON)

        for entity in entities.values():
            entity.async_schedule_update_ha_state.assert_not_called()

    def test_power_state_stored(self, manager, mock_receiver):
        mock_receiver.power = "STANDBY"
        manager._last_power_state = POWER_ON

        manager._power_callback("Main", "ZM", "STANDBY")

        assert manager._last_power_state == "STANDBY"

    def test_wrong_zone_ignored(self, manager_with_entities):
        manager, entities = manager_with_entities
        manager._last_power_state = POWER_ON

        manager._power_callback("Zone2", "Z2", "STANDBY")

        for entity in entities.values():
            entity.async_schedule_update_ha_state.assert_not_called()


# ---------------------------------------------------------------------------
# ChannelVolumeNumber.available
# ---------------------------------------------------------------------------


class TestChannelVolumeNumberAvailable:
    def test_available_all_conditions_met(self, channel_entity, manager):
        manager.receiver_available = True
        manager.receiver.power = POWER_ON
        manager.channel_volumes["FL"] = 0.0

        assert channel_entity.available is True

    def test_unavailable_receiver_down(self, channel_entity, manager):
        manager.receiver_available = False
        manager.receiver.power = POWER_ON
        manager.channel_volumes["FL"] = 0.0

        assert channel_entity.available is False

    def test_unavailable_powered_off(self, channel_entity, manager):
        manager.receiver_available = True
        manager.receiver.power = "STANDBY"
        manager.channel_volumes["FL"] = 0.0

        assert channel_entity.available is False

    def test_unavailable_no_value(self, channel_entity, manager):
        manager.receiver_available = True
        manager.receiver.power = POWER_ON
        manager.channel_volumes["FL"] = None

        assert channel_entity.available is False


# ---------------------------------------------------------------------------
# ChannelVolumeNumber.native_value
# ---------------------------------------------------------------------------


class TestChannelVolumeNumberNativeValue:
    def test_returns_current_value(self, channel_entity, manager):
        manager.channel_volumes["FL"] = 3.5
        assert channel_entity.native_value == 3.5

    def test_returns_none_when_not_set(self, channel_entity, manager):
        manager.channel_volumes["FL"] = None
        assert channel_entity.native_value is None

    def test_returns_zero(self, channel_entity, manager):
        manager.channel_volumes["FL"] = 0.0
        assert channel_entity.native_value == 0.0


# ---------------------------------------------------------------------------
# ChannelVolumeNumber properties
# ---------------------------------------------------------------------------


class TestChannelVolumeNumberProperties:
    def test_min_value(self, channel_entity):
        assert channel_entity.native_min_value == -12.0

    def test_max_value(self, channel_entity):
        assert channel_entity.native_max_value == 12.0

    def test_step(self, channel_entity):
        assert channel_entity.native_step == 0.5

    def test_unit(self, channel_entity):
        assert channel_entity.native_unit_of_measurement == "dB"

    def test_icon_speaker(self, channel_entity):
        assert channel_entity._attr_icon == "mdi:speaker"

    def test_icon_subwoofer(self, manager):
        sw_entity = ChannelVolumeNumber(
            manager=manager,
            channel="SW",
            zone="Main",
            device_info={},
            unique_id_base="test-serial",
            device_name="Test Device",
        )
        # Documents current (possibly surprising) icon choice for subwoofer
        assert sw_entity._attr_icon == "mdi:smoke-detector"

    def test_name_main_zone(self, channel_entity):
        assert channel_entity._attr_name == "Test Device Front Left Volume"

    def test_name_zone2(self, manager_zone2):
        entity = ChannelVolumeNumber(
            manager=manager_zone2,
            channel="FL",
            zone="Zone2",
            device_info={},
            unique_id_base="test-serial",
            device_name="Test Device",
        )
        assert entity._attr_name == "Test Device Zone2 Front Left Volume"

    def test_unique_id_main_zone(self, channel_entity):
        assert channel_entity._attr_unique_id == "test-serial_front_left_volume"

    def test_unique_id_zone2(self, manager_zone2):
        entity = ChannelVolumeNumber(
            manager=manager_zone2,
            channel="FL",
            zone="Zone2",
            device_info={},
            unique_id_base="test-serial",
            device_name="Test Device",
        )
        assert entity._attr_unique_id == "test-serial_zone2_front_left_volume"


# ---------------------------------------------------------------------------
# async_send_cv_command
# ---------------------------------------------------------------------------


class TestSendCvCommand:
    async def test_counter_incremented_on_success(self, manager):
        mock_writer = MagicMock()
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()
        mock_writer.close = MagicMock()
        mock_writer.wait_closed = AsyncMock()

        with patch(
            "asyncio.open_connection",
            new=AsyncMock(return_value=(MagicMock(), mock_writer)),
        ):
            await manager.async_send_cv_command("FL", 3.0)

        assert manager.pending_counters["FL"] == 1

    async def test_main_zone_command_format(self, manager):
        mock_writer = MagicMock()
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()
        mock_writer.close = MagicMock()
        mock_writer.wait_closed = AsyncMock()

        with patch(
            "asyncio.open_connection",
            new=AsyncMock(return_value=(MagicMock(), mock_writer)),
        ):
            await manager.async_send_cv_command("FL", 3.0)

        mock_writer.write.assert_called_once_with(b"CVFL 53\r")

    async def test_zone2_command_format(self, manager_zone2):
        mock_writer = MagicMock()
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()
        mock_writer.close = MagicMock()
        mock_writer.wait_closed = AsyncMock()

        with patch(
            "asyncio.open_connection",
            new=AsyncMock(return_value=(MagicMock(), mock_writer)),
        ):
            await manager_zone2.async_send_cv_command("FL", 3.0)

        mock_writer.write.assert_called_once_with(b"Z2CVFL 53\r")

    async def test_half_db_command_format(self, manager):
        mock_writer = MagicMock()
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()
        mock_writer.close = MagicMock()
        mock_writer.wait_closed = AsyncMock()

        with patch(
            "asyncio.open_connection",
            new=AsyncMock(return_value=(MagicMock(), mock_writer)),
        ):
            await manager.async_send_cv_command("FL", 3.5)

        mock_writer.write.assert_called_once_with(b"CVFL 535\r")

    async def test_counter_decremented_on_os_error(self, manager):
        with patch(
            "asyncio.open_connection",
            new=AsyncMock(side_effect=OSError("connection refused")),
        ):
            await manager.async_send_cv_command("FL", 3.0)

        assert manager.pending_counters["FL"] == 0

    async def test_counter_decremented_on_timeout(self, manager):
        async def timing_out(*_args, **_kwargs):
            raise TimeoutError

        with patch(
            "asyncio.wait_for",
            side_effect=TimeoutError,
        ):
            await manager.async_send_cv_command("FL", 3.0)

        assert manager.pending_counters["FL"] == 0


class TestExtraChannelCodes:
    @pytest.mark.parametrize(
        "code", ["SBL", "SBR", "SB", "FHL", "FHR", "FWL", "FWR", "SW2"]
    )
    def test_extra_speaker_codes_not_warned(self, manager_with_entities, caplog, code):
        manager, entities = manager_with_entities

        with caplog.at_level(logging.WARNING):
            manager._cv_callback("Main", "CV", f"{code} 50")

        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
        for entity in entities.values():
            entity.async_write_ha_state.assert_not_called()
