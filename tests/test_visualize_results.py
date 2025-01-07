"""Test for the visualize_results module."""

import json
from pathlib import Path
from unittest.mock import mock_open, patch

import numpy as np
import pytest

from src.visualize_results import VisualizeResults


@pytest.fixture
def visualize_results() -> VisualizeResults:
    """Fixture for the visualize_results module."""
    return VisualizeResults()


def test_select_test_file_no_files(visualize_results: VisualizeResults) -> None:
    """Test for the select_test_file method when no files are found."""
    with patch("src.visualize_results.Path.glob", return_value=[]):
        result = visualize_results.select_test_file()
        assert result is None


def test_select_test_file_with_files(visualize_results: VisualizeResults) -> None:
    """Test for the select_test_file method when files are found."""
    mock_files = [Path(f"test_{i}.json") for i in range(15)]
    with (
        patch("src.visualize_results.Path.glob", return_value=mock_files),
        patch("builtins.input", side_effect=["1", "q"]),
    ):
        result = visualize_results.select_test_file()
        assert result == mock_files[0]


def test_load_and_process_data_valid(visualize_results: VisualizeResults) -> None:
    """Test for the load_and_process_data method when valid data is found."""
    mock_data = [
        {
            "test": "test1",
            "waiting_time": 0.1,
            "samples": 10,
            "latency_avg": 0.05,
            "latency_min": 0.01,
            "latency_max": 0.1,
            "latency_p95": 0.09,
            "dropped_messages": 0,
            "results": [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.1],
        }
    ]
    with patch("pathlib.Path.open", mock_open(read_data=json.dumps(mock_data))):
        result = visualize_results.load_and_process_data(Path("test.json"))
        assert result is not None
        labels, test_data, stats_data, samples, jitter = result
        assert labels == ["t: test1\nw.time:\n100"]
        assert len(test_data) == 1
        assert len(stats_data) == 1
        assert samples == 10  # noqa: PLR2004
        assert jitter is False


def test_load_and_process_data_invalid(visualize_results: VisualizeResults) -> None:
    """Test for the load_and_process_data method when invalid data is found."""
    with patch("builtins.open", mock_open(read_data="{}")):
        result = visualize_results.load_and_process_data(Path("test.json"))
        assert result is None


def test_plot_data(visualize_results: VisualizeResults) -> None:
    """Test for the plot_data method."""
    labels = ["Test 1"]
    test_data = [np.array([0.01, 0.02, 0.03])]
    stats_data = [
        {"avg": 0.02, "min": 0.01, "max": 0.03, "p95": 0.03, "dropped_messages": 0}
    ]
    samples = 3
    jitter = False
    with patch("matplotlib.pyplot.show") as mock_show:
        visualize_results.plot_data(labels, test_data, stats_data, samples, jitter)
        mock_show.assert_called_once()


def test_get_test_files(visualize_results: VisualizeResults) -> None:
    """Test for the _get_test_files method."""
    mock_files = [Path(f"test_{i}.json") for i in range(5)]
    with patch("src.visualize_results.Path.glob", return_value=mock_files):
        files = visualize_results._get_test_files()
        assert files == mock_files


def test_get_page_files(visualize_results: VisualizeResults) -> None:
    """Test for the _get_page_files method."""
    files = [Path(f"test_{i}.json") for i in range(15)]
    page_files = visualize_results._get_page_files(files, 1, 5)
    assert page_files == files[5:10]


def test_display_page(
    visualize_results: VisualizeResults, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test for the _display_page method."""
    page_files = [Path(f"test_{i}.json") for i in range(5)]
    visualize_results._display_page(page_files, 0, 10, 5)
    captured = capsys.readouterr()
    assert "1. test_0.json" in captured.out
    assert "n - Next page" in captured.out
    assert "q - Return to main menu" in captured.out


def test_handle_choice_next_page(visualize_results: VisualizeResults) -> None:
    """Test for the _handle_choice method for next page."""
    files = [Path(f"test_{i}.json") for i in range(15)]
    result = visualize_results._handle_choice("n", files[:5], 0, files, 5)
    assert result == 1


def test_handle_choice_previous_page(visualize_results: VisualizeResults) -> None:
    """Test for the _handle_choice method for previous page."""
    files = [Path(f"test_{i}.json") for i in range(15)]
    result = visualize_results._handle_choice("p", files[5:10], 1, files, 5)
    assert result == 0


def test_handle_choice_select_file(visualize_results: VisualizeResults) -> None:
    """Test for the _handle_choice method for selecting a file."""
    files = [Path(f"test_{i}.json") for i in range(5)]
    result = visualize_results._handle_choice("1", files, 0, files, 5)
    assert result == files[0]


def test_handle_choice_invalid_input(visualize_results: VisualizeResults) -> None:
    """Test for the _handle_choice method with invalid input."""
    files = [Path(f"test_{i}.json") for i in range(5)]
    result = visualize_results._handle_choice("x", files, 0, files, 5)
    assert result == 0
