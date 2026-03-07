"""Tests for stress_config module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from const import TEST_RESULTS_FOLDER
from stress_config import (
    ScenarioConfig,
    ScenarioThresholds,
    StressConfig,
    _scenario_from_dict,
    _scenario_thresholds_from_dict,
    default_stress_config,
    load_stress_config,
)

# ---------------------------------------------------------------------------
# Dataclass default tests
# ---------------------------------------------------------------------------


class TestScenarioThresholdsDefaults:
    def test_max_echo_drop_ratio_default(self) -> None:
        t = ScenarioThresholds()
        assert t.max_echo_drop_ratio == 0.001

    def test_max_error_counter_deltas_default(self) -> None:
        t = ScenarioThresholds()
        assert t.max_error_counter_deltas == {}

    def test_max_p95_latency_ms_default(self) -> None:
        t = ScenarioThresholds()
        assert t.max_p95_latency_ms == 50.0

    def test_max_recovery_time_s_default(self) -> None:
        t = ScenarioThresholds()
        assert t.max_recovery_time_s == 2.0


class TestScenarioConfigDefaults:
    def test_pacing_s_default(self) -> None:
        cfg = ScenarioConfig(name="x", duration_s=1.0, command_profile="echo_only")
        assert cfg.pacing_s == 0.0

    def test_message_length_default(self) -> None:
        cfg = ScenarioConfig(name="x", duration_s=1.0, command_profile="echo_only")
        assert cfg.message_length == 10

    def test_num_messages_default(self) -> None:
        cfg = ScenarioConfig(name="x", duration_s=1.0, command_profile="echo_only")
        assert cfg.num_messages == 500

    def test_baud_rates_default(self) -> None:
        cfg = ScenarioConfig(name="x", duration_s=1.0, command_profile="echo_only")
        assert cfg.baud_rates == []

    def test_noise_bytes_default(self) -> None:
        cfg = ScenarioConfig(name="x", duration_s=1.0, command_profile="echo_only")
        assert cfg.noise_bytes == 64

    def test_thresholds_default(self) -> None:
        cfg = ScenarioConfig(name="x", duration_s=1.0, command_profile="echo_only")
        assert cfg.thresholds == ScenarioThresholds()

    def test_tags_default(self) -> None:
        cfg = ScenarioConfig(name="x", duration_s=1.0, command_profile="echo_only")
        assert cfg.tags == []


class TestStressConfigDefaults:
    def test_output_dir_default(self) -> None:
        cfg = StressConfig(scenarios=[])
        assert cfg.output_dir == TEST_RESULTS_FOLDER


# ---------------------------------------------------------------------------
# default_stress_config() tests
# ---------------------------------------------------------------------------


class TestDefaultStressConfig:
    def test_returns_stress_config(self) -> None:
        cfg = default_stress_config()
        assert isinstance(cfg, StressConfig)

    def test_scenario_count(self) -> None:
        cfg = default_stress_config()
        assert len(cfg.scenarios) == 5

    def test_output_dir(self) -> None:
        cfg = default_stress_config()
        assert cfg.output_dir == TEST_RESULTS_FOLDER

    def test_scenario_names(self) -> None:
        cfg = default_stress_config()
        names = [s.name for s in cfg.scenarios]
        assert names == [
            "echo_burst",
            "mixed_command_burst",
            "status_poll_storm",
            "baud_flip",
            "noise_and_recovery",
        ]

    # -- echo_burst --
    def test_echo_burst_duration(self) -> None:
        s = default_stress_config().scenarios[0]
        assert s.duration_s == 30.0

    def test_echo_burst_profile(self) -> None:
        s = default_stress_config().scenarios[0]
        assert s.command_profile == "echo_only"

    def test_echo_burst_pacing(self) -> None:
        s = default_stress_config().scenarios[0]
        assert s.pacing_s == 0.005

    def test_echo_burst_message_length(self) -> None:
        s = default_stress_config().scenarios[0]
        assert s.message_length == 10

    def test_echo_burst_num_messages(self) -> None:
        s = default_stress_config().scenarios[0]
        assert s.num_messages == 500

    def test_echo_burst_thresholds(self) -> None:
        t = default_stress_config().scenarios[0].thresholds
        assert t.max_echo_drop_ratio == 0.001
        assert t.max_error_counter_deltas == {"buffer_overflow_error": 0}
        assert t.max_p95_latency_ms == 50.0

    def test_echo_burst_tags(self) -> None:
        s = default_stress_config().scenarios[0]
        assert s.tags == ["ci", "quick"]

    # -- mixed_command_burst --
    def test_mixed_burst_duration(self) -> None:
        s = default_stress_config().scenarios[1]
        assert s.duration_s == 45.0

    def test_mixed_burst_profile(self) -> None:
        s = default_stress_config().scenarios[1]
        assert s.command_profile == "mixed"

    def test_mixed_burst_pacing(self) -> None:
        s = default_stress_config().scenarios[1]
        assert s.pacing_s == 0.01

    def test_mixed_burst_num_messages(self) -> None:
        s = default_stress_config().scenarios[1]
        assert s.num_messages == 400

    def test_mixed_burst_thresholds(self) -> None:
        t = default_stress_config().scenarios[1].thresholds
        assert t.max_echo_drop_ratio == 0.005
        assert t.max_p95_latency_ms == 100.0

    def test_mixed_burst_tags(self) -> None:
        s = default_stress_config().scenarios[1]
        assert s.tags == ["ci"]

    # -- status_poll_storm --
    def test_status_poll_duration(self) -> None:
        s = default_stress_config().scenarios[2]
        assert s.duration_s == 20.0

    def test_status_poll_profile(self) -> None:
        s = default_stress_config().scenarios[2]
        assert s.command_profile == "status_poll"

    def test_status_poll_pacing(self) -> None:
        s = default_stress_config().scenarios[2]
        assert s.pacing_s == 0.0

    def test_status_poll_num_messages(self) -> None:
        s = default_stress_config().scenarios[2]
        assert s.num_messages == 200

    def test_status_poll_thresholds(self) -> None:
        t = default_stress_config().scenarios[2].thresholds
        assert t.max_echo_drop_ratio == 1.0
        assert t.max_error_counter_deltas == {"queue_send_error": 0}
        assert t.max_p95_latency_ms == 200.0

    def test_status_poll_tags(self) -> None:
        s = default_stress_config().scenarios[2]
        assert s.tags == ["ci"]

    # -- baud_flip --
    def test_baud_flip_duration(self) -> None:
        s = default_stress_config().scenarios[3]
        assert s.duration_s == 60.0

    def test_baud_flip_profile(self) -> None:
        s = default_stress_config().scenarios[3]
        assert s.command_profile == "baud_flip"

    def test_baud_flip_num_messages(self) -> None:
        s = default_stress_config().scenarios[3]
        assert s.num_messages == 5

    def test_baud_flip_baud_rates(self) -> None:
        s = default_stress_config().scenarios[3]
        assert s.baud_rates == [9600, 57600, 115200, 230400]

    def test_baud_flip_thresholds(self) -> None:
        t = default_stress_config().scenarios[3].thresholds
        assert t.max_echo_drop_ratio == 0.0
        assert t.max_p95_latency_ms == 200.0
        assert t.max_recovery_time_s == 3.0

    def test_baud_flip_tags(self) -> None:
        s = default_stress_config().scenarios[3]
        assert s.tags == ["hil"]

    # -- noise_and_recovery --
    def test_noise_recovery_duration(self) -> None:
        s = default_stress_config().scenarios[4]
        assert s.duration_s == 15.0

    def test_noise_recovery_profile(self) -> None:
        s = default_stress_config().scenarios[4]
        assert s.command_profile == "noise_and_recovery"

    def test_noise_recovery_noise_bytes(self) -> None:
        s = default_stress_config().scenarios[4]
        assert s.noise_bytes == 64

    def test_noise_recovery_num_messages(self) -> None:
        s = default_stress_config().scenarios[4]
        assert s.num_messages == 10

    def test_noise_recovery_thresholds(self) -> None:
        t = default_stress_config().scenarios[4].thresholds
        assert t.max_echo_drop_ratio == 0.0
        assert t.max_p95_latency_ms == 2000.0
        assert t.max_recovery_time_s == 2.0

    def test_noise_recovery_tags(self) -> None:
        s = default_stress_config().scenarios[4]
        assert s.tags == ["ci", "fault_injection"]


# ---------------------------------------------------------------------------
# _scenario_thresholds_from_dict() tests
# ---------------------------------------------------------------------------


class TestScenarioThresholdsFromDict:
    def test_empty_dict_returns_defaults(self) -> None:
        t = _scenario_thresholds_from_dict({})
        assert t.max_echo_drop_ratio == 0.001
        assert t.max_error_counter_deltas == {}
        assert t.max_p95_latency_ms == 50.0
        assert t.max_recovery_time_s == 2.0

    def test_full_dict_overrides_all(self) -> None:
        d = {
            "max_echo_drop_ratio": 0.05,
            "max_error_counter_deltas": {"crc_error": 3},
            "max_p95_latency_ms": 99.0,
            "max_recovery_time_s": 5.0,
        }
        t = _scenario_thresholds_from_dict(d)
        assert t.max_echo_drop_ratio == 0.05
        assert t.max_error_counter_deltas == {"crc_error": 3}
        assert t.max_p95_latency_ms == 99.0
        assert t.max_recovery_time_s == 5.0

    def test_partial_dict_mixes_overrides_and_defaults(self) -> None:
        t = _scenario_thresholds_from_dict({"max_p95_latency_ms": 77.0})
        assert t.max_echo_drop_ratio == 0.001  # default
        assert t.max_p95_latency_ms == 77.0  # overridden
        assert t.max_recovery_time_s == 2.0  # default


# ---------------------------------------------------------------------------
# _scenario_from_dict() tests
# ---------------------------------------------------------------------------


class TestScenarioFromDict:
    def test_minimal_dict_uses_defaults(self) -> None:
        cfg = _scenario_from_dict({"name": "test_scenario"})
        assert cfg.name == "test_scenario"
        assert cfg.duration_s == 30.0
        assert cfg.command_profile == "echo_only"
        assert cfg.pacing_s == 0.0
        assert cfg.message_length == 10
        assert cfg.num_messages == 500
        assert cfg.baud_rates == []
        assert cfg.noise_bytes == 64
        assert cfg.thresholds == ScenarioThresholds()
        assert cfg.tags == []

    def test_full_dict_overrides_all(self) -> None:
        d = {
            "name": "custom",
            "duration_s": 99.9,
            "command_profile": "baud_flip",
            "pacing_s": 0.5,
            "message_length": 8,
            "num_messages": 100,
            "baud_rates": [9600, 115200],
            "noise_bytes": 32,
            "thresholds": {"max_p95_latency_ms": 200.0},
            "tags": ["custom_tag"],
        }
        cfg = _scenario_from_dict(d)
        assert cfg.name == "custom"
        assert cfg.duration_s == 99.9
        assert cfg.command_profile == "baud_flip"
        assert cfg.pacing_s == 0.5
        assert cfg.message_length == 8
        assert cfg.num_messages == 100
        assert cfg.baud_rates == [9600, 115200]
        assert cfg.noise_bytes == 32
        assert cfg.thresholds.max_p95_latency_ms == 200.0
        assert cfg.tags == ["custom_tag"]

    def test_missing_name_raises_key_error(self) -> None:
        with pytest.raises(KeyError):
            _scenario_from_dict({"duration_s": 10})

    def test_type_coercion_from_strings(self) -> None:
        d = {
            "name": "coercion_test",
            "duration_s": "42",
            "pacing_s": "0.1",
            "message_length": "8",
            "num_messages": "200",
            "noise_bytes": "32",
        }
        cfg = _scenario_from_dict(d)
        assert cfg.duration_s == 42.0
        assert isinstance(cfg.duration_s, float)
        assert cfg.pacing_s == 0.1
        assert isinstance(cfg.pacing_s, float)
        assert cfg.message_length == 8
        assert isinstance(cfg.message_length, int)
        assert cfg.num_messages == 200
        assert isinstance(cfg.num_messages, int)
        assert cfg.noise_bytes == 32
        assert isinstance(cfg.noise_bytes, int)

    def test_thresholds_delegation(self) -> None:
        d = {
            "name": "thresh_test",
            "thresholds": {
                "max_echo_drop_ratio": 0.1,
                "max_p95_latency_ms": 300.0,
            },
        }
        cfg = _scenario_from_dict(d)
        assert cfg.thresholds.max_echo_drop_ratio == 0.1
        assert cfg.thresholds.max_p95_latency_ms == 300.0
        assert cfg.thresholds.max_recovery_time_s == 2.0  # default


# ---------------------------------------------------------------------------
# load_stress_config() tests
# ---------------------------------------------------------------------------


class TestLoadStressConfig:
    def test_round_trip(self, tmp_path: Path) -> None:
        data = {
            "output_dir": "my_output",
            "scenarios": [
                {
                    "name": "sc1",
                    "duration_s": 10,
                    "command_profile": "echo_only",
                    "num_messages": 50,
                    "tags": ["test"],
                    "thresholds": {"max_echo_drop_ratio": 0.01},
                }
            ],
        }
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(data))
        cfg = load_stress_config(config_file)
        assert cfg.output_dir == "my_output"
        assert len(cfg.scenarios) == 1
        assert cfg.scenarios[0].name == "sc1"
        assert cfg.scenarios[0].duration_s == 10.0
        assert cfg.scenarios[0].num_messages == 50
        assert cfg.scenarios[0].tags == ["test"]
        assert cfg.scenarios[0].thresholds.max_echo_drop_ratio == 0.01

    def test_empty_scenarios(self, tmp_path: Path) -> None:
        config_file = tmp_path / "empty.json"
        config_file.write_text(json.dumps({"scenarios": []}))
        cfg = load_stress_config(config_file)
        assert cfg.scenarios == []
        assert cfg.output_dir == "results"

    def test_default_output_dir(self, tmp_path: Path) -> None:
        config_file = tmp_path / "no_dir.json"
        config_file.write_text(json.dumps({"scenarios": [{"name": "s"}]}))
        cfg = load_stress_config(config_file)
        assert cfg.output_dir == "results"

    def test_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_stress_config(tmp_path / "missing.json")

    def test_invalid_json(self, tmp_path: Path) -> None:
        config_file = tmp_path / "bad.json"
        config_file.write_text("not json at all")
        with pytest.raises(json.JSONDecodeError):
            load_stress_config(config_file)

    def test_multiple_scenarios(self, tmp_path: Path) -> None:
        data = {
            "scenarios": [
                {"name": "a", "duration_s": 5},
                {"name": "b", "duration_s": 10, "command_profile": "mixed"},
            ]
        }
        config_file = tmp_path / "multi.json"
        config_file.write_text(json.dumps(data))
        cfg = load_stress_config(config_file)
        assert len(cfg.scenarios) == 2
        assert cfg.scenarios[0].name == "a"
        assert cfg.scenarios[1].name == "b"
        assert cfg.scenarios[1].command_profile == "mixed"
