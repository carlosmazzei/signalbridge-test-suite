"""Test for the visualize_results module."""

import json
from pathlib import Path
from unittest.mock import Mock, mock_open, patch

import numpy as np
import pytest

from visualize_results import VisualizeResults


@pytest.fixture(autouse=True)
def prevent_infinite_loops(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Prevent infinite loops in select_test_file during mutation testing.
    Mutmut might mutate the loop's exit condition, causing the test to hang until timeout.
    This fixture bounds the number of loop iterations.
    """
    original_handle_choice = VisualizeResults._handle_choice
    call_count = 0

    def mock_handle_choice(
        self: VisualizeResults,
        choice: str,
        page_files: list[Path],
        current_page: int,
        files: list[Path],
        page_size: int,
    ) -> Path | int | None:
        nonlocal call_count
        call_count += 1
        if call_count > 100:  # Arbitrary limit, plenty for any normal test
            msg = "Infinite loop detected during test"
            raise RuntimeError(msg)
        return original_handle_choice(
            self, choice, page_files, current_page, files, page_size
        )

    monkeypatch.setattr(VisualizeResults, "_handle_choice", mock_handle_choice)


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
        assert samples == 10
        assert jitter is False


def test_load_and_process_data_invalid(visualize_results: VisualizeResults) -> None:
    """Test for the load_and_process_data method when invalid data is found."""
    with patch("builtins.open", mock_open(read_data="{}")):
        result = visualize_results.load_and_process_data(Path("test.json"))
        assert result is None


def test_visualize_stress_run(visualize_results: VisualizeResults) -> None:
    """Test that _visualize_stress_run parses stress data and calls matplotlib."""
    mock_data = {
        "run_id": "1234",
        "overall_verdict": "PASS",
        "scenarios": [
            {
                "name": "echo_burst",
                "drop_ratio": 0.0,
                "p95_ms": 10.5,
                "status_delta": {"statistics": {"cobs_decode_error": 5}},
                "verdict": "PASS",
                "failure_reasons": [],
            },
            {
                "name": "bad_scenario",
                "drop_ratio": 1.0,
                "p95_ms": 100.0,
                "status_delta": {"cobs_decode_error": 10},
                "verdict": "FAIL",
                "failure_reasons": ["Too many dropped"],
            },
        ],
    }
    with (
        patch("visualize_results.plt.subplots") as mock_subplots,
        patch("visualize_results.plt.tight_layout"),
        patch("visualize_results.plt.subplots_adjust"),
        patch("visualize_results.plt.show"),
    ):
        mock_fig = Mock()
        mock_ax1 = Mock()
        mock_ax2 = Mock()
        mock_ax3 = Mock()

        def make_bar_mock():
            m = Mock()
            m.get_x.return_value = 0.0
            m.get_width.return_value = 0.8
            m.get_height.return_value = 10.0
            return m

        mock_ax1.bar.return_value = [make_bar_mock(), make_bar_mock()]
        mock_ax2.bar.return_value = [make_bar_mock(), make_bar_mock()]
        mock_ax3.bar.return_value = [make_bar_mock(), make_bar_mock()]
        mock_subplots.return_value = (mock_fig, (mock_ax1, mock_ax2, mock_ax3))

        # Test valid data
        visualize_results._visualize_stress_run(mock_data)

        # Verify subplots were called
        mock_subplots.assert_called_once_with(3, 1, figsize=(10, 12))
        mock_ax1.bar.assert_called_once()
        mock_ax2.bar.assert_called_once()
        mock_ax3.bar.assert_called_once()

    # Test empty scenarios
    with patch("visualize_results.logger.info") as mock_log:
        visualize_results._visualize_stress_run({"scenarios": []})
        mock_log.assert_called_with("No scenarios found in stress result.")


def test_plot_boxplot(visualize_results: VisualizeResults) -> None:
    """Test for the plot_boxplot method."""
    labels = ["Test 1"]
    test_data = [np.array([0.01, 0.02, 0.03])]
    stats_data = [
        {"avg": 0.02, "min": 0.01, "max": 0.03, "p95": 0.03, "dropped_messages": 0}
    ]
    samples = 3
    jitter = False

    # Mock matplotlib to verify calls
    with (
        patch("matplotlib.pyplot.subplots") as mock_subplots,
        patch("matplotlib.pyplot.show") as mock_show,
    ):
        # Setup mock figure and axes
        mock_fig = Mock()
        mock_ax1 = Mock()
        mock_ax2 = Mock()
        mock_subplots.return_value = (mock_fig, (mock_ax1, mock_ax2))

        # Setup boxplot return value to avoid iteration errors if it's used
        mock_boxplot = {"medians": [Mock()]}
        mock_ax1.boxplot.return_value = mock_boxplot
        # Setup line get_xydata for stats text positioning
        mock_boxplot["medians"][0].get_xydata.return_value = [[0, 0], [1, 1]]
        mock_ax1.get_ylim.return_value = (0, 1)

        # Fix: get_xticklabels must return an iterable
        mock_ax1.get_xticklabels.return_value = [Mock() for _ in labels]

        # FIX: Configure bar mocks to return float values for math operations
        mock_bar = Mock()
        mock_bar.get_x.return_value = 0.0
        mock_bar.get_width.return_value = 0.5
        mock_bar.get_height.return_value = 1.0
        mock_ax2.bar.return_value = [mock_bar]

        # Fix: get_xticklabels must return an iterable
        mock_ax1.get_xticklabels.return_value = [Mock() for _ in labels]
        mock_ax2.get_xticklabels.return_value = [Mock() for _ in labels]

        visualize_results.plot_boxplot(labels, test_data, stats_data, samples, jitter)

        # Verify plotting calls
        mock_ax1.boxplot.assert_called_once()
        args, kwargs = mock_ax1.boxplot.call_args
        assert kwargs["showmeans"] is True
        assert kwargs["patch_artist"] is True

        mock_ax1.set_title.assert_called_with(
            f"Latency Percentiles (Samples = {samples})", fontsize=10
        )
        mock_ax1.set_ylabel.assert_called_with("Latency (ms) - Log Scale")
        mock_ax1.set_yscale.assert_called_with("log")

        # Verify bar charts were created with exact kwargs
        assert mock_ax2.bar.call_count == 3
        bar_calls = mock_ax2.bar.call_args_list
        assert bar_calls[0].kwargs["label"] == "Dropped"
        assert bar_calls[0].kwargs["alpha"] == 0.85
        assert bar_calls[1].kwargs["label"] == "Status Δ Errors"
        assert bar_calls[1].kwargs["alpha"] == 0.85
        assert bar_calls[2].kwargs["label"] == "Backlog End"
        assert bar_calls[2].kwargs["alpha"] == 0.85

        mock_show.assert_called_once()


def test_plot_histogram(visualize_results: VisualizeResults) -> None:
    """Test for the plot_histogram method."""
    test_data = [np.array([0.01, 0.02, 0.03])]
    labels = ["T1"]
    stats_data = [
        {"p95": 0.03, "avg": 0.02, "min": 0.01, "max": 0.03},
    ]

    with (
        patch("matplotlib.pyplot.subplots") as mock_subplots,
        patch("matplotlib.pyplot.show") as mock_show,
        patch("visualize_results.cm.get_cmap", return_value=lambda _: ["red"]),
    ):
        mock_fig = Mock()
        mock_ax = Mock()
        # When len(test_data) == 1, subplots returns single ax, code wraps it in list
        mock_subplots.return_value = (mock_fig, mock_ax)
        mock_ax.get_ylim.return_value = (0, 10)

        visualize_results.plot_histogram(test_data, labels, stats_data)

        # Verify histogram plotting
        mock_ax.hist.assert_called_once()
        hist_args, hist_kwargs = mock_ax.hist.call_args
        np.testing.assert_array_equal(hist_args[0], test_data[0])
        assert hist_kwargs["bins"] == 50
        assert hist_kwargs["alpha"] == 0.75
        assert hist_kwargs["label"] == "T1"
        assert hist_kwargs["color"] == "red"
        assert hist_kwargs["histtype"] == "stepfilled"

        # Verify p95 line plot
        mock_ax.axvline.assert_called_once_with(
            stats_data[0]["p95"], color="red", linestyle="--", alpha=1.0
        )

        # Verify text and labels
        mock_ax.set_title.assert_called_with("T1", fontsize=10)
        mock_ax.set_xlabel.assert_called_with("Latency (ms)")

        mock_show.assert_called_once()


def test_plot_controller_health(visualize_results: VisualizeResults) -> None:
    """Test plot_controller_health method."""
    labels = ["t0", "t1"]
    stats_data = [
        {
            "status_error_delta_total": 0.0,
            "outstanding_final": 1.0,
            "outstanding_max": 2.0,
        },
        {
            "status_error_delta_total": 3.0,
            "outstanding_final": 4.0,
            "outstanding_max": 5.0,
        },
    ]
    with (
        patch("matplotlib.pyplot.subplots") as mock_subplots,
        patch("matplotlib.pyplot.show") as mock_show,
        patch("matplotlib.pyplot.setp"),
    ):
        mock_fig = Mock()
        mock_ax1 = Mock()
        mock_ax2 = Mock()
        mock_subplots.return_value = (mock_fig, (mock_ax1, mock_ax2))

        # Fix: get_xticklabels must return an iterable
        mock_ax2.get_xticklabels.return_value = [Mock() for _ in labels]

        visualize_results.plot_controller_health(labels, stats_data)

        # Verify bar chart (Error Delta)
        mock_ax1.bar.assert_called_once()
        bar_args, bar_kwargs = mock_ax1.bar.call_args
        np.testing.assert_array_equal(bar_args[0], np.arange(2))
        assert bar_args[1] == [0.0, 3.0]
        assert bar_kwargs["color"] == "tab:red"
        assert bar_kwargs["alpha"] == 0.85

        mock_ax1.set_ylabel.assert_called_with("Status Error Δ")
        mock_ax1.set_title.assert_called_with("Error Delta per Series", fontsize=10)

        # Verify line plots (Backlog)
        assert mock_ax2.plot.call_count == 2
        plot_calls = mock_ax2.plot.call_args_list

        # Backlog End
        pe_args = plot_calls[0].args
        pe_kwargs = plot_calls[0].kwargs
        np.testing.assert_array_equal(pe_args[0], np.arange(2))
        assert pe_args[1] == [1.0, 4.0]
        assert pe_kwargs["marker"] == "o"
        assert pe_kwargs["linestyle"] == "-"
        assert pe_kwargs["linewidth"] == 1.5
        assert pe_kwargs["label"] == "Backlog End"

        # Backlog Max
        pm_args = plot_calls[1].args
        pm_kwargs = plot_calls[1].kwargs
        np.testing.assert_array_equal(pm_args[0], np.arange(2))
        assert pm_args[1] == [2.0, 5.0]
        assert pm_kwargs["marker"] == "^"
        assert pm_kwargs["linestyle"] == "--"
        assert pm_kwargs["linewidth"] == 1.5
        assert pm_kwargs["label"] == "Backlog Max"

        mock_ax2.set_ylabel.assert_called_with("Outstanding Messages")
        mock_ax2.set_title.assert_called_with("Backlog per Series", fontsize=10)

        mock_show.assert_called_once()


def test_plot_error_counter_details(visualize_results: VisualizeResults) -> None:
    """Test plot_error_counter_details method."""
    from base_test import STATISTICS_DISPLAY_NAMES, STATUS_ERROR_KEYS

    labels = ["t0", "t1"]
    # Logic requires non-zero errors to plot. Use a key from the actual set.
    error_key = next(iter(STATUS_ERROR_KEYS))
    error_key_display = STATISTICS_DISPLAY_NAMES.get(error_key, error_key)
    # Give one series an error, and the other explicitly no errors to catch `get` mutants
    error_counters = [{error_key: 5}, {error_key: 0}]

    with (
        patch("matplotlib.pyplot.figure") as mock_figure,
        patch("matplotlib.pyplot.show") as mock_show,
        # Mock cm.get_cmap because it's used in this method
        patch("visualize_results.cm.get_cmap", return_value=lambda _: ["red", "blue"]),
        patch("matplotlib.pyplot.colorbar") as mock_colorbar,
    ):
        mock_fig = Mock()
        mock_figure.return_value = mock_fig

        # Configure add_gridspec return value to be subscriptable
        mock_gs = Mock()
        mock_gs.__getitem__ = Mock(return_value=Mock())
        mock_fig.add_gridspec.return_value = mock_gs

        # Setup subplots
        mock_ax1 = Mock()
        mock_ax2 = Mock()
        mock_ax3 = Mock()
        mock_fig.add_subplot.side_effect = [mock_ax1, mock_ax2, mock_ax3]

        visualize_results.plot_error_counter_details(labels, error_counters)

        # --- Verify Figure ---
        mock_figure.assert_called_with(figsize=(14, 10))
        mock_fig.suptitle.assert_called_with(
            "Detailed Error Counter Analysis - Before/After Test Series",
            fontsize=14,
            fontweight="bold",
        )
        mock_fig.add_gridspec.assert_called_with(
            3, 1, height_ratios=[2, 1.5, 0.8], hspace=0.3
        )

        # --- Verify Subplot 1 (Stacked Bar) ---
        assert mock_ax1.bar.call_count == 1
        args, kwargs = mock_ax1.bar.call_args
        np.testing.assert_array_equal(args[0], np.arange(2))  # x
        assert args[1] == [5, 0]  # values
        # Check specific cosmetic args to kill mutants
        assert kwargs["bottom"] is not None  # checking existence first
        # verify bottom is updated in-place after the call
        np.testing.assert_array_equal(kwargs["bottom"], np.array([5.0, 0.0]))
        assert kwargs["label"] == error_key_display
        assert kwargs["color"] == "red"
        assert kwargs["alpha"] == 0.85

        mock_ax1.set_ylabel.assert_called_with("Error Count (Δ)", fontsize=11)
        mock_ax1.set_title.assert_called_with(
            "Error Counter Changes per Test Series (Stacked)", fontsize=12
        )
        mock_ax1.set_xticks.assert_called()
        mock_ax1.set_xticklabels.assert_called_with(
            labels, fontsize=8, rotation=45, ha="right"
        )
        mock_ax1.grid.assert_called_with(axis="y", linestyle="--", alpha=0.4)
        mock_ax1.legend.assert_called_with(
            bbox_to_anchor=(1.02, 1),
            loc="upper left",
            fontsize=8,
            framealpha=0.9,
        )

        # --- Verify Subplot 2 (Heatmap) ---
        mock_ax2.imshow.assert_called_once()
        args, kwargs = mock_ax2.imshow.call_args
        np.testing.assert_array_equal(args[0], np.array([[5, 0]]))
        assert kwargs["aspect"] == "auto"
        assert kwargs["cmap"] == "YlOrRd"
        assert kwargs["interpolation"] == "nearest"

        mock_ax2.set_xlabel.assert_called_with("Test Series", fontsize=11)
        mock_ax2.set_ylabel.assert_called_with("Error Type", fontsize=11)
        mock_ax2.set_title.assert_called_with("Error Distribution Heatmap", fontsize=12)

        # Verify text annotation loops in heatmap
        mock_ax2.text.assert_called()
        args, kwargs = mock_ax2.text.call_args
        # Should be called with (0, 0, "5", ...)
        assert args[0] == 0
        assert args[1] == 0
        assert args[2] == "5"
        assert kwargs["ha"] == "center"
        assert kwargs["va"] == "center"
        assert kwargs["fontsize"] == 8
        assert kwargs["fontweight"] == "bold"
        # Color logic check: 5 > 2.5 (max/2) -> white
        assert kwargs["color"] == "white"

        # --- Verify Subplot 3 (Summary Text) ---
        mock_ax3.axis.assert_called_with("off")
        mock_ax3.text.assert_called()
        args, kwargs = mock_ax3.text.call_args
        summary_text = args[2]

        expected_summary_parts = [
            "📊 Summary Statistics:",
            "Total errors across all series: 5",
            "Series with errors: 1/2",
            "Maximum errors in single series: 5",
            f"Most common error: {error_key_display} (5 occurrences)",
            "Unique error types detected: 1/20",  # 20 is len of STATUS_ERROR_KEYS
        ]
        for part in expected_summary_parts:
            assert part in summary_text, f"Missing '{part}' in summary text"

        assert kwargs["ha"] == "center"
        assert kwargs["va"] == "center"
        assert kwargs["fontsize"] == 10
        assert kwargs["family"] == "monospace"
        assert kwargs["bbox"]["edgecolor"] == "darkblue"
        assert kwargs["bbox"]["facecolor"] == "lightcyan"
        assert kwargs["bbox"]["alpha"] == 0.9

        # --- Verify Explanation Text ---
        # fig.text is called twice (one for title? No, fig.suptitle was used.
        # Ah, fig.text is used for "Variable Explanations" at the bottom)
        mock_fig.text.assert_called()
        args, kwargs = mock_fig.text.call_args
        assert args[0] == 0.5
        assert args[1] == 0.01
        assert "Variable Explanations" in args[2]
        assert kwargs["ha"] == "center"
        assert kwargs["fontsize"] == 9
        assert kwargs["bbox"]["edgecolor"] == "green"
        assert kwargs["bbox"]["facecolor"] == "lightgreen"
        assert kwargs["bbox"]["alpha"] == 0.7

        mock_show.assert_called_once()
        mock_colorbar.assert_called()


def test_visualize_test_results_runs_boxplot_path(
    visualize_results: VisualizeResults,
) -> None:
    """visualize_test_results should call real plot_boxplot."""
    labels = ["L1"]
    data = [np.array([1.0])]
    stats = [{"p95": 1.0, "avg": 1.0, "min": 1.0, "max": 1.0, "dropped_messages": 0}]
    processed = (labels, data, stats, 1, False, [{}])

    with (
        patch.object(VisualizeResults, "select_test_file", return_value=Path("x.json")),
        patch.object(VisualizeResults, "load_and_process_data", return_value=processed),
        patch("builtins.input", return_value="1") as mock_input,
        patch("builtins.print") as mock_print,
        # We Mock matplotlib to prevent actual window opening,
        # but we DO NOT mock plot_boxplot
        patch("matplotlib.pyplot.subplots") as mock_subplots,
        patch("matplotlib.pyplot.setp"),
        patch("matplotlib.pyplot.show") as mock_show,
    ):
        # Setup mocks for plot_boxplot internals
        mock_fig = Mock()
        mock_ax1 = Mock()
        mock_ax2 = Mock()
        mock_subplots.return_value = (mock_fig, (mock_ax1, mock_ax2))
        mock_boxplot = {"medians": [Mock()]}
        mock_ax1.boxplot.return_value = mock_boxplot
        mock_boxplot["medians"][0].get_xydata.return_value = [[0, 0], [1, 1]]
        mock_ax1.get_ylim.return_value = (0, 1)
        mock_ax1.get_xticklabels.return_value = [Mock() for _ in labels]
        mock_ax2.get_xticklabels.return_value = [Mock() for _ in labels]

        # Configure bar mocks to return float values for math operations
        mock_bar = Mock()
        mock_bar.get_x.return_value = 0.0
        mock_bar.get_width.return_value = 0.5
        mock_bar.get_height.return_value = 1.0
        mock_ax2.bar.return_value = [mock_bar]

        visualize_results.visualize_test_results()

        # Verify result
        mock_ax1.boxplot.assert_called_once()
        mock_show.assert_called_once()

        # Verify inputs and prints to kill mutants
        mock_input.assert_called_with("Enter choice (1, 2, 3 or 4): ")
        mock_print.assert_any_call("Select visualization type:")
        mock_print.assert_any_call("1. Boxplot")


def test_visualize_test_results_runs_histogram_path(
    visualize_results: VisualizeResults,
) -> None:
    """visualize_test_results should call real plot_histogram."""
    labels = ["L1"]
    data = [np.array([1.0])]
    stats = [{"p95": 1.0, "avg": 1.0, "min": 1.0, "max": 1.0}]
    processed = (labels, data, stats, 1, False, [{}])

    with (
        patch.object(VisualizeResults, "select_test_file", return_value=Path("x.json")),
        patch.object(VisualizeResults, "load_and_process_data", return_value=processed),
        patch("builtins.input", return_value="2") as mock_input,
        patch("builtins.print") as mock_print,
        patch("matplotlib.pyplot.subplots") as mock_subplots,
        patch("matplotlib.pyplot.show") as mock_show,
        patch("visualize_results.cm.get_cmap", return_value=lambda _: ["red"]),
    ):
        mock_fig = Mock()
        mock_ax = Mock()
        mock_subplots.return_value = (mock_fig, mock_ax)
        mock_ax.get_ylim.return_value = (0, 10)

        visualize_results.visualize_test_results()

        mock_ax.hist.assert_called_once()
        mock_ax.axvline.assert_called()  # Check p95 line
        mock_show.assert_called_once()

        mock_input.assert_called_with("Enter choice (1, 2, 3 or 4): ")
        mock_print.assert_any_call("2. Histogram")


def test_visualize_test_results_runs_controller_health_path(
    visualize_results: VisualizeResults,
) -> None:
    """visualize_test_results should call real plot_controller_health."""
    labels = ["L1"]
    stats = [
        {"status_error_delta_total": 0, "outstanding_final": 0, "outstanding_max": 0}
    ]
    data = [np.array([1.0])]
    processed = (labels, data, stats, 1, False, [{}])

    with (
        patch.object(VisualizeResults, "select_test_file", return_value=Path("x.json")),
        patch.object(VisualizeResults, "load_and_process_data", return_value=processed),
        patch("builtins.input", return_value="3"),
        patch("matplotlib.pyplot.subplots") as mock_subplots,
        patch("matplotlib.pyplot.show") as mock_show,
        patch("matplotlib.pyplot.setp"),
    ):
        mock_fig = Mock()
        mock_ax1 = Mock()
        mock_ax2 = Mock()
        mock_subplots.return_value = (mock_fig, (mock_ax1, mock_ax2))
        mock_ax2.get_xticklabels.return_value = [Mock() for _ in labels]

        visualize_results.visualize_test_results()

        mock_ax1.bar.assert_called_once()
        mock_show.assert_called_once()


def test_visualize_test_results_runs_error_details_path(
    visualize_results: VisualizeResults,
) -> None:
    """visualize_test_results should call real plot_error_counter_details."""
    from base_test import STATUS_ERROR_KEYS

    labels = ["L1"]
    # Must provide NON-ZERO errors to trigger plotting
    error_key = next(iter(STATUS_ERROR_KEYS))
    error_counters = [{error_key: 5}]
    data = [np.array([1.0])]
    stats = [{"p95": 1.0}]
    processed = (labels, data, stats, 1, False, error_counters)

    with (
        patch.object(VisualizeResults, "select_test_file", return_value=Path("x.json")),
        patch.object(VisualizeResults, "load_and_process_data", return_value=processed),
        patch("builtins.input", return_value="4"),
        patch("matplotlib.pyplot.figure") as mock_figure,
        patch("matplotlib.pyplot.show") as mock_show,
        patch("visualize_results.cm.get_cmap", return_value=lambda _: ["red"]),
        patch("matplotlib.pyplot.colorbar"),
    ):
        mock_fig = Mock()
        mock_figure.return_value = mock_fig

        # FIX: Configure add_gridspec return value to be subscriptable
        mock_gs = Mock()
        mock_gs.__getitem__ = Mock(return_value=Mock())
        mock_fig.add_gridspec.return_value = mock_gs

        mock_fig.add_subplot.return_value = Mock()

        visualize_results.visualize_test_results()

        mock_fig.add_subplot.assert_called()
        mock_show.assert_called_once()


# Keep existing helper tests
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
    assert "p - Previous page" not in captured.out


def test_display_page_no_next_on_last_page(
    visualize_results: VisualizeResults, capsys: pytest.CaptureFixture[str]
) -> None:
    """'n - Next page' must NOT appear when already on the last page."""
    page_files = [Path(f"test_{i}.json") for i in range(5)]
    visualize_results._display_page(page_files, 1, 10, 5)
    captured = capsys.readouterr()
    assert "n - Next page" not in captured.out


def test_display_page_shows_correct_page_number(
    visualize_results: VisualizeResults, capsys: pytest.CaptureFixture[str]
) -> None:
    """_display_page shows the correct '(Page X of Y)' text."""
    page_files = [Path(f"test_{i}.json") for i in range(5)]
    visualize_results._display_page(page_files, 0, 10, 5)
    captured = capsys.readouterr()
    assert "(Page 1 of 2)" in captured.out
    assert "p - Previous page" not in captured.out


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


def test_handle_choice_n_on_penultimate_page(
    visualize_results: VisualizeResults,
) -> None:
    """'n' on the second-to-last page advances one page (not two)."""
    files = [Path(f"test_{i}.json") for i in range(15)]
    result = visualize_results._handle_choice("n", files[5:10], 1, files, 5)
    assert result == 2


def test_handle_choice_digit_at_exact_length_boundary(
    visualize_results: VisualizeResults,
) -> None:
    """A digit equal to len(page_files)+1 is out of range and returns current_page."""
    files = [Path(f"test_{i}.json") for i in range(3)]
    result = visualize_results._handle_choice("4", files, 0, files, 5)
    assert result == 0


def test_get_total_pages(visualize_results: VisualizeResults) -> None:
    """Test for the _get_total_pages method."""
    files = [Path(f"test_{i}.json") for i in range(16)]
    result = visualize_results._get_total_pages(len(files), 5)
    assert result == 4


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


def test_visualize_test_results_passes_file_path_to_load(
    visualize_results: VisualizeResults,
) -> None:
    """visualize_test_results passes the selected file path to load_and_process_data."""
    selected = Path("mytest.json")
    with (
        patch.object(VisualizeResults, "select_test_file", return_value=selected),
        patch.object(
            VisualizeResults, "load_and_process_data", return_value=None
        ) as load_mock,
    ):
        visualize_results.visualize_test_results()
    load_mock.assert_called_once_with(selected)


def test_select_test_file_navigates_next_then_selects(
    visualize_results: VisualizeResults,
) -> None:
    """select_test_file correctly advances the page and selects a file."""
    mock_files = [Path(f"test_{i}.json") for i in range(15)]
    sorted_files = sorted(mock_files)
    with (
        patch("visualize_results.Path.glob", return_value=mock_files),
        patch("builtins.input", side_effect=["n", "1"]),
    ):
        result = visualize_results.select_test_file()
    assert result == sorted_files[10]


def test_handle_choice_n_at_last_page(visualize_results: VisualizeResults) -> None:
    """'n' on the last page stays on the current page."""
    files = [Path(f"test_{i}.json") for i in range(5)]
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
    from base_test import STATUS_ERROR_KEYS

    series: dict[str, object] = {
        "status_delta": {
            "statistics": {STATUS_ERROR_KEYS[0]: 3, STATUS_ERROR_KEYS[1]: 2},
        }
    }
    result = visualize_results._status_error_delta_total(series)
    assert result == 5


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
