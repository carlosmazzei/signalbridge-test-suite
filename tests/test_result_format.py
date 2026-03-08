"""Tests for result_format module."""

from __future__ import annotations

import re
from unittest.mock import patch

from result_format import (
    FORMAT_LATENCY_SERIES,
    FORMAT_STRESS_RUN,
    RESULT_FORMAT_VERSION,
    make_result_envelope,
    make_result_filename,
    parse_result_envelope,
)

# ---------------------------------------------------------------------------
# make_result_envelope
# ---------------------------------------------------------------------------


class TestMakeResultEnvelope:
    def test_wraps_payload_with_format_type(self) -> None:
        result = make_result_envelope(FORMAT_LATENCY_SERIES, [{"test": 1}])
        assert result["format_type"] == FORMAT_LATENCY_SERIES
        assert result["payload"] == [{"test": 1}]

    def test_default_version(self) -> None:
        result = make_result_envelope(FORMAT_STRESS_RUN, {})
        assert result["format_version"] == RESULT_FORMAT_VERSION

    def test_custom_version(self) -> None:
        result = make_result_envelope("custom", {}, format_version=99)
        assert result["format_version"] == 99


# ---------------------------------------------------------------------------
# parse_result_envelope
# ---------------------------------------------------------------------------


class TestParseResultEnvelope:
    def test_valid_envelope(self) -> None:
        data = {"format_type": "test", "payload": {"key": "val"}}
        result = parse_result_envelope(data)
        assert result == ("test", {"key": "val"})

    def test_returns_none_for_non_dict(self) -> None:
        assert parse_result_envelope([1, 2, 3]) is None

    def test_returns_none_for_missing_format_type(self) -> None:
        assert parse_result_envelope({"payload": {}}) is None

    def test_returns_none_for_missing_payload(self) -> None:
        assert parse_result_envelope({"format_type": "x"}) is None

    def test_returns_none_for_non_string_format_type(self) -> None:
        assert parse_result_envelope({"format_type": 123, "payload": {}}) is None


# ---------------------------------------------------------------------------
# make_result_filename
# ---------------------------------------------------------------------------


class TestMakeResultFilename:
    def test_format_matches_standard(self) -> None:
        """Filename follows YYYYMMDD-HHMMSS-<run_id>-<test_type>.json."""
        name = make_result_filename("latency", "abcd1234")
        assert re.fullmatch(r"\d{8}-\d{6}-abcd1234-latency\.json", name)

    def test_stress_type(self) -> None:
        name = make_result_filename("stress", "deadbeef")
        assert name.endswith("-deadbeef-stress.json")

    def test_baud_sweep_type(self) -> None:
        name = make_result_filename("baud_sweep", "12345678")
        assert name.endswith("-12345678-baud_sweep.json")

    def test_timestamp_is_utc(self) -> None:
        """Verify the timestamp portion comes from a controlled clock."""
        import datetime

        fixed = datetime.datetime(2025, 3, 15, 10, 30, 45, tzinfo=datetime.UTC)
        with patch("result_format.datetime.datetime") as mock_dt:
            mock_dt.now.return_value = fixed
            mock_dt.UTC = datetime.UTC
            name = make_result_filename("latency", "aabbccdd")
        assert name.startswith("20250315-103045-")
