"""Test for the visualize_results module."""

import json
from pathlib import Path
from unittest.mock import Mock, mock_open, patch

import numpy as np
import pytest

from visualize_results import VisualizeResults


@pytest.fixture
def visualize_results() -> VisualizeResults:
    """Fixture for the visualize_results module."""
    return VisualizeResults()


def test_select_test_file_no_files(visualize_results: VisualizeResults) -> None:
    """Test for the select_test_file method when no files are found."""
    with patch("visualize_results.Path.glob", return_value=[]):
        result = visualize_results.select_test_file()
        assert result is None


def test_select_test_file_with_files(visualize_results: VisualizeResults) -> None:
    """Test for the select_test_file method when files are found."""
    mock_files = [Path(f"test_{i}.json") for i in range(15)]
    with (
        patch("visualize_results.Path.glob", return_value=mock_files),
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
            "bitrate": 100.365,
            "jitter": False,
            "results": [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.1],
        }
    ]
    with patch("pathlib.Path.open", mock_open(read_data=json.dumps(mock_data))):
        result = visualize_results.load_and_process_data(Path("test.json"))
        assert result is not None
        labels, test_data, stats_data, samples, jitter = result
        assert labels == ["t: test1\nw.time:\n100\nbitrate: 100"]
        assert len(test_data) == 1
        assert len(stats_data) == 1
        assert samples == 10  # noqa: PLR2004
        assert jitter is False


def test_load_and_process_data_invalid(visualize_results: VisualizeResults) -> None:
    """Test for the load_and_process_data method when invalid data is found."""
    with patch("builtins.open", mock_open(read_data="{}")):
        result = visualize_results.load_and_process_data(Path("test.json"))
        assert result is None


def test_plot_boxplot(visualize_results: VisualizeResults) -> None:
    """Test for the plot_data method."""
    labels = ["Test 1"]
    test_data = [np.array([0.01, 0.02, 0.03])]
    stats_data = [
        {"avg": 0.02, "min": 0.01, "max": 0.03, "p95": 0.03, "dropped_messages": 0}
    ]
    samples = 3
    jitter = False
    with patch("matplotlib.pyplot.show") as mock_show:
        visualize_results.plot_boxplot(labels, test_data, stats_data, samples, jitter)
        mock_show.assert_called_once()


def test_plot_histogram(visualize_results: VisualizeResults) -> None:
    """Test for the plot_histogram method with detailed assertions."""
    test_data = [np.array([0.01, 0.02, 0.03]), np.array([0.04, 0.05, 0.06])]
    labels = ["T1", "T2"]
    stats_data = [
        {"p95": 0.03, "avg": 0.02, "min": 0.01, "max": 0.03},
        {"p95": 0.06, "avg": 0.05, "min": 0.04, "max": 0.06},
    ]

    ax1 = Mock()
    ax2 = Mock()
    ax1.get_ylim.return_value = (0, 10)
    ax2.get_ylim.return_value = (0, 10)
    fig = Mock()

    with (
        patch(
            "visualize_results.plt.subplots", return_value=(fig, [ax1, ax2])
        ) as subplots,
        patch("visualize_results.plt.subplots_adjust") as subplots_adjust,
        patch("visualize_results.plt.tight_layout"),
        patch("visualize_results.plt.show") as mock_show,
        patch("visualize_results.cm.get_cmap", return_value=lambda v: ["red", "blue"]),  # noqa: ARG005
    ):
        visualize_results.plot_histogram(test_data, labels, stats_data)

    # First axis assertions
    ax1.hist.assert_called_once()
    _, kwargs1 = ax1.hist.call_args
    assert kwargs1["bins"] == 50  # noqa: PLR2004
    assert kwargs1["alpha"] == pytest.approx(0.75)
    assert kwargs1["label"] == "T1"
    assert kwargs1["color"] == "red"
    assert kwargs1["histtype"] == "stepfilled"

    # p95 vertical line and text label
    ax1.axvline.assert_called_once_with(0.03, color="red", linestyle="--", alpha=1.0)
    ax1.text.assert_any_call(
        0.03,
        10,
        "P95: 0.0ms",
        rotation=90,
        va="top",
        ha="right",
        bbox=visualize_results.bbox_props,
    )
    ax1.set_title.assert_called()
    ax1.set_xlabel.assert_called_with("Latency (ms)")
    ax1.grid.assert_called_with(axis="y", linestyle="--", alpha=0.7)

    # Second axis basic checks
    assert ax2.hist.call_count == 1
    _, kwargs2 = ax2.hist.call_args
    assert kwargs2["label"] == "T2"
    assert kwargs2["color"] == "blue"
    # Layout calls
    subplots.assert_called_once()
    assert subplots.call_args.kwargs.get("sharey") is True
    subplots_adjust.assert_called_once_with(wspace=0)
    mock_show.assert_called_once()


def test_plot_histogram_layout_and_color_sampling(
    visualize_results: VisualizeResults,
) -> None:
    """Verify layout and color sampling arguments are correct."""
    test_data = [np.array([0.01, 0.02, 0.03])]
    labels = ["Only"]
    stats_data = [{"p95": 0.03, "avg": 0.02, "min": 0.01, "max": 0.03}]

    ax = Mock()
    ax.get_ylim.return_value = (0, 1)
    fig = Mock()

    linspace_mock = Mock(return_value=[0.0])

    with (
        patch("visualize_results.plt.subplots", return_value=(fig, ax)),
        patch("visualize_results.plt.subplots_adjust") as subplots_adjust,
        patch("visualize_results.plt.show"),
        patch("visualize_results.cm.get_cmap", return_value=lambda v: ["green"]),  # noqa: ARG005
        patch("visualize_results.np.linspace", linspace_mock),
    ):
        visualize_results.plot_histogram(test_data, labels, stats_data)

    # subplots_adjust should enforce zero spacing
    subplots_adjust.assert_called_once_with(wspace=0)
    # color sampling spans 0..1 with count == len(test_data)
    linspace_mock.assert_called_once_with(0, 1, len(test_data))


def test_get_test_files(visualize_results: VisualizeResults) -> None:
    """Test for the _get_test_files method."""
    mock_files = [Path(f"test_{i}.json") for i in range(5)]
    with patch("visualize_results.Path.glob", return_value=mock_files):
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


def test_get_total_pages(visualize_results: VisualizeResults) -> None:
    """Test for the _get_total_pages method."""
    files = [Path(f"test_{i}.json") for i in range(16)]
    result = visualize_results._get_total_pages(len(files), 5)
    assert result == 4  # noqa: PLR2004


def test_visualize_test_results_returns_when_no_file_selected(
    visualize_results: VisualizeResults,
) -> None:
    """visualize_test_results should exit early when no file is selected."""
    with (
        patch.object(VisualizeResults, "select_test_file", return_value=None),
        patch.object(VisualizeResults, "load_and_process_data") as load_mock,
    ):
        visualize_results.visualize_test_results()
    load_mock.assert_not_called()


def test_visualize_test_results_runs_boxplot_path(
    visualize_results: VisualizeResults,
) -> None:
    """visualize_test_results should call boxplot when user selects option 1."""
    processed = (["L1"], [np.array([1.0])], [{"p95": 1.0}], 1, False)
    with (
        patch.object(VisualizeResults, "select_test_file", return_value=Path("x.json")),
        patch.object(VisualizeResults, "load_and_process_data", return_value=processed),
        patch("builtins.input", return_value="1"),
        patch.object(VisualizeResults, "plot_boxplot") as box_mock,
        patch.object(VisualizeResults, "plot_histogram") as hist_mock,
    ):
        visualize_results.visualize_test_results()
    box_mock.assert_called_once_with(*processed)
    hist_mock.assert_not_called()


def test_visualize_test_results_runs_histogram_path(
    visualize_results: VisualizeResults,
) -> None:
    """visualize_test_results should call histogram when user selects option 2."""
    labels = ["L1"]
    data = [np.array([1.0])]
    stats = [{"p95": 1.0}]
    processed = (labels, data, stats, 1, False)
    with (
        patch.object(VisualizeResults, "select_test_file", return_value=Path("x.json")),
        patch.object(VisualizeResults, "load_and_process_data", return_value=processed),
        patch("builtins.input", return_value="2"),
        patch.object(VisualizeResults, "plot_boxplot") as box_mock,
        patch.object(VisualizeResults, "plot_histogram") as hist_mock,
    ):
        visualize_results.visualize_test_results()
    box_mock.assert_not_called()
    hist_mock.assert_called_once_with(data, labels, stats)
