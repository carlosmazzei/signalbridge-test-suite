# Copyright (C) 2026 SignalBridge contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Result file format envelope helpers."""

from __future__ import annotations

import datetime
from typing import Any

RESULT_FORMAT_VERSION = 1
FORMAT_STRESS_RUN = "stress_run"
FORMAT_LATENCY_SERIES = "latency_series"


def make_result_envelope(
    format_type: str,
    payload: Any,
    *,
    format_version: int = RESULT_FORMAT_VERSION,
) -> dict[str, Any]:
    """Wrap payload with explicit format metadata for robust classification."""
    return {
        "format_type": format_type,
        "format_version": format_version,
        "payload": payload,
    }


def make_result_filename(test_type: str, run_id: str) -> str:
    """Return ``YYYYMMDD-HHMMSS-<run_id>-<type>.json``."""
    timestamp = datetime.datetime.now(tz=datetime.UTC).strftime("%Y%m%d-%H%M%S")
    return f"{timestamp}-{run_id}-{test_type}.json"


def parse_result_envelope(data: Any) -> tuple[str, Any] | None:
    """Return ``(format_type, payload)`` for valid envelopes, else ``None``."""
    if not isinstance(data, dict):
        return None

    format_type = data.get("format_type")
    payload = data.get("payload")
    if not isinstance(format_type, str) or "payload" not in data:
        return None

    return format_type, payload
