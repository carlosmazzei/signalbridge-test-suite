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
        labels, test_data, stats_data, samples, jitter, error_counters = result
        assert labels == ["t: test1\nw.time:\n100\nbitrate: 100"]
        assert len(test_data) == 1
        assert len(stats_data) == 1
        assert len(error_counters) == 1
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
    # Check both subplots_adjust calls
    assert subplots_adjust.call_count == 2  # noqa: PLR2004
    subplots_adjust.assert_any_call(wspace=0)
    subplots_adjust.assert_any_call(bottom=0.18)
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

    # subplots_adjust should enforce zero spacing and bottom margin
    assert subplots_adjust.call_count == 2  # noqa: PLR2004
    subplots_adjust.assert_any_call(wspace=0)
    subplots_adjust.assert_any_call(bottom=0.18)
    # color sampling spans 0..1 with count == len(test_data)
    linspace_mock.assert_called_once_with(0, 1, len(test_data))


def test_plot_controller_health(visualize_results: VisualizeResults) -> None:
    """Controller health plotting should render without exceptions."""
    labels = ["t0", "t1"]
    stats_data = [
        {
            "status_error_delta_total": 0,
            "outstanding_final": 1,
            "outstanding_max": 2,
        },
        {
            "status_error_delta_total": 3,
            "outstanding_final": 4,
            "outstanding_max": 5,
        },
    ]
    with patch("matplotlib.pyplot.show") as mock_show:
        visualize_results.plot_controller_health(labels, stats_data)
        mock_show.assert_called_once()


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
    labels = ["L1"]
    data = [np.array([1.0])]
    stats = [{"p95": 1.0}]
    processed = (labels, data, stats, 1, False, [{}])
    with (
        patch.object(VisualizeResults, "select_test_file", return_value=Path("x.json")),
        patch.object(VisualizeResults, "load_and_process_data", return_value=processed),
        patch("builtins.input", return_value="1"),
        patch.object(VisualizeResults, "plot_boxplot") as box_mock,
        patch.object(VisualizeResults, "plot_histogram") as hist_mock,
    ):
        visualize_results.visualize_test_results()
    box_mock.assert_called_once_with(labels, data, stats, 1, jitter=False)
    hist_mock.assert_not_called()


def test_visualize_test_results_runs_histogram_path(
    visualize_results: VisualizeResults,
) -> None:
    """visualize_test_results should call histogram when user selects option 2."""
    labels = ["L1"]
    data = [np.array([1.0])]
    stats = [{"p95": 1.0}]
    processed = (labels, data, stats, 1, False, [{}])
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


def test_handle_choice_n_at_last_page(visualize_results: VisualizeResults) -> None:
    """'n' on the last page stays on the current page."""
    files = [Path(f"test_{i}.json") for i in range(5)]
    # (0+1)*5 < 5 is False, so n should not advance
    result = visualize_results._handle_choice("n", files, 0, files, 5)
    assert result == 0


def test_handle_choice_p_at_first_page(visualize_results: VisualizeResults) -> None:
    """'p' on page 0 stays on page 0."""
    files = [Path(f"test_{i}.json") for i in range(15)]
    result = visualize_results._handle_choice("p", files[:5], 0, files, 5)
    assert result == 0


def test_handle_choice_q_returns_none(visualize_results: VisualizeResults) -> None:
    """'q' returns None to signal exit."""
    files = [Path(f"test_{i}.json") for i in range(5)]
    result = visualize_results._handle_choice("q", files, 0, files, 5)
    assert result is None


def test_handle_choice_out_of_range_digit(visualize_results: VisualizeResults) -> None:
    """A digit that exceeds the page file count returns current_page."""
    files = [Path(f"test_{i}.json") for i in range(3)]
    result = visualize_results._handle_choice("9", files, 0, files, 5)
    assert result == 0


def test_status_error_delta_total_with_data(
    visualize_results: VisualizeResults,
) -> None:
    """_status_error_delta_total sums known error keys from status_delta.statistics."""
    from base_test import STATUS_ERROR_KEYS  # noqa: PLC0415

    series: dict[str, object] = {
        "status_delta": {
            "statistics": {STATUS_ERROR_KEYS[0]: 3, STATUS_ERROR_KEYS[1]: 2},
        }
    }
    result = visualize_results._status_error_delta_total(series)
    assert result == 5  # noqa: PLR2004


def test_status_error_delta_total_no_status_delta(
    visualize_results: VisualizeResults,
) -> None:
    """_status_error_delta_total returns 0 when status_delta key is absent."""
    assert visualize_results._status_error_delta_total({}) == 0


def test_status_error_delta_total_non_dict_status_delta(
    visualize_results: VisualizeResults,
) -> None:
    """_status_error_delta_total returns 0 when status_delta is not a dict."""
    result = visualize_results._status_error_delta_total({"status_delta": "invalid"})
    assert result == 0


def test_status_error_delta_total_non_dict_statistics(
    visualize_results: VisualizeResults,
) -> None:
    """_status_error_delta_total returns 0 when statistics is not a dict."""
    result = visualize_results._status_error_delta_total(
        {"status_delta": {"statistics": 42}}
    )
    assert result == 0


def test_display_page_shows_previous_option(
    visualize_results: VisualizeResults, capsys: pytest.CaptureFixture[str]
) -> None:
    """_display_page shows 'p - Previous page' when current_page > 0."""
    page_files = [Path(f"test_{i}.json") for i in range(5)]
    visualize_results._display_page(page_files, 1, 20, 5)
    captured = capsys.readouterr()
    assert "p - Previous page" in captured.out


def test_visualize_test_results_error_counter_details(
    visualize_results: VisualizeResults,
) -> None:
    """visualize_test_results calls plot_error_counter_details for choice '4'."""
    labels = ["L1"]
    data = [np.array([1.0])]
    stats = [{"p95": 1.0}]
    error_counters = [{"key": 0}]
    processed = (labels, data, stats, 1, False, error_counters)
    with (
        patch.object(VisualizeResults, "select_test_file", return_value=Path("x.json")),
        patch.object(VisualizeResults, "load_and_process_data", return_value=processed),
        patch("builtins.input", return_value="4"),
        patch.object(VisualizeResults, "plot_error_counter_details") as detail_mock,
    ):
        visualize_results.visualize_test_results()
    detail_mock.assert_called_once_with(labels, error_counters)


def test_visualize_test_results_invalid_choice(
    visualize_results: VisualizeResults,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """visualize_test_results prints an error message for an unrecognised choice."""
    labels = ["L1"]
    data = [np.array([1.0])]
    stats = [{"p95": 1.0}]
    processed = (labels, data, stats, 1, False, [{}])
    with (
        patch.object(VisualizeResults, "select_test_file", return_value=Path("x.json")),
        patch.object(VisualizeResults, "load_and_process_data", return_value=processed),
        patch("builtins.input", return_value="9"),
    ):
        visualize_results.visualize_test_results()
    out = capsys.readouterr().out
    assert "Invalid choice" in out


def test_visualize_test_results_runs_controller_health_path(
    visualize_results: VisualizeResults,
) -> None:
    """visualize_test_results should call controller health for option 3."""
    labels = ["L1"]
    data = [np.array([1.0])]
    stats = [{"p95": 1.0}]
    processed = (labels, data, stats, 1, False, [{}])
    with (
        patch.object(VisualizeResults, "select_test_file", return_value=Path("x.json")),
        patch.object(VisualizeResults, "load_and_process_data", return_value=processed),
        patch("builtins.input", return_value="3"),
        patch.object(VisualizeResults, "plot_boxplot") as box_mock,
        patch.object(VisualizeResults, "plot_histogram") as hist_mock,
        patch.object(VisualizeResults, "plot_controller_health") as health_mock,
    ):
        visualize_results.visualize_test_results()
    box_mock.assert_not_called()
    hist_mock.assert_not_called()
    health_mock.assert_called_once_with(labels, stats)
