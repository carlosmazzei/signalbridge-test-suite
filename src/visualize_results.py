"""Module to visualize the test results."""

import json
import logging
from math import ceil
from pathlib import Path
from typing import ClassVar

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import cm

from base_test import STATISTICS_DISPLAY_NAMES, STATUS_ERROR_KEYS
from const import TEST_RESULTS_FOLDER
from logger_config import setup_logging

setup_logging()

logger = logging.getLogger(__name__)


class VisualizeResults:
    """Class to visualize the log files and plot it."""

    bbox_props: ClassVar[dict[str, str | float]] = {
        "boxstyle": "round,pad=0.3",
        "edgecolor": "black",
        "facecolor": "white",
        "alpha": 0.8,
    }

    def select_test_file(self) -> Path | None:
        """Select a test file from the tests folder."""
        files = self._get_test_files()
        if not files:
            logger.info("No test files found in the tests folder.")
            return None

        page_size: int = 10
        current_page: int = 0

        while True:
            page_files = self._get_page_files(files, current_page, page_size)
            self._display_page(page_files, current_page, len(files), page_size)

            choice = input("\nEnter your choice (number, n, p, or q): ").lower()
            result = self._handle_choice(
                choice, page_files, current_page, files, page_size
            )

            if isinstance(result, Path):
                return result
            if result is None:
                return None
            current_page = result

    def _get_test_files(self) -> list[Path]:
        """Get sorted list of test files from the tests folder."""
        tests_folder: Path = Path(__file__).parent.parent / TEST_RESULTS_FOLDER
        return sorted(tests_folder.glob("*.json"))

    def _get_page_files(
        self, files: list[Path], current_page: int, page_size: int
    ) -> list[Path]:
        """Get files for the current page."""
        start_idx: int = current_page * page_size
        end_idx: int = start_idx + page_size
        return files[start_idx:end_idx]

    def _get_total_pages(self, total_files: int, page_size: int) -> int:
        """Calculate total number of pages."""
        return ceil(total_files / page_size)

    def _display_page(
        self,
        page_files: list[Path],
        current_page: int,
        total_files: int,
        page_size: int,
    ) -> None:
        """Display the current page of files and options."""
        print("\nTest files:")
        for idx, file in enumerate(page_files, start=1):
            print(f"{idx}. {file.name}")

        print("\nOptions:")
        if (current_page + 1) * page_size < total_files:
            print("n - Next page")
        if current_page > 0:
            print("p - Previous page")
        print("q - Return to main menu")
        print(
            f"(Page {current_page + 1} of "
            f"{self._get_total_pages(total_files, page_size)})"
        )

    def _handle_choice(
        self,
        choice: str,
        page_files: list[Path],
        current_page: int,
        files: list[Path],
        page_size: int,
    ) -> Path | int | None:
        """Handle user input choice and return appropriate result."""
        if choice == "n" and (current_page + 1) * page_size < len(files):
            return current_page + 1
        if choice == "p" and current_page > 0:
            return current_page - 1
        if choice == "q":
            return None
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(page_files):
                return page_files[idx]
            logger.info("Invalid file number. Please try again.")
        else:
            logger.info("Invalid input. Please try again.")
        return current_page

    def load_and_process_data(
        self,
        file_path: Path,
    ) -> (
        tuple[
            list[str],
            list[np.ndarray],
            list[dict[str, float]],
            int,
            bool,
            list[dict[str, int]],
        ]
        | None
    ):
        """Load and process data from the JSON file."""
        try:
            with file_path.open() as f:
                data = json.load(f)

            if not isinstance(data, list):
                msg = "The JSON data should be a list of test series."
                raise ValueError(msg)  # noqa: TRY004, TRY301

            labels = []
            test_data = []
            stats_data = []
            error_counters = []
            samples = 0
            jitter = False

            for series in data:
                series_data = np.array(series["results"]) * 1000
                waiting_time = format(series["waiting_time"] * 1000, ".0f")
                bitrate = format(series["bitrate"], ".0f")
                jitter = series.get("jitter", False)
                if "baudrate" in series:
                    series_name = (
                        f"t: {series['test']}\nbaud:\n{series['baudrate']}"
                        f"\nbitrate: {bitrate}"
                    )
                else:
                    series_name = (
                        f"t: {series['test']}\nw.time:\n{waiting_time}"
                        f"\nbitrate: {bitrate}"
                    )
                samples += series["samples"]
                labels.append(series_name)
                test_data.append(series_data)

                stats_data.append(
                    {
                        "avg": series["latency_avg"] * 1000,
                        "min": series["latency_min"] * 1000,
                        "max": series["latency_max"] * 1000,
                        "p95": series["latency_p95"] * 1000,
                        "bitrate": series["bitrate"],
                        "dropped_messages": series["dropped_messages"],
                        "outstanding_final": series.get("outstanding_final", 0),
                        "outstanding_max": series.get("outstanding_max", 0),
                        "status_error_delta_total": self._status_error_delta_total(
                            series
                        ),
                    },
                )

                # Extract individual error counters
                status_delta = series.get("status_delta", {})
                statistics = status_delta.get("statistics", {})
                error_counters.append(
                    {key: int(statistics.get(key, 0)) for key in STATUS_ERROR_KEYS}
                )

            if not test_data:
                msg = "No valid data to visualize."
                raise ValueError(msg)  # noqa: TRY301

        except (OSError, KeyError, TypeError, ValueError):  # fmt: skip
            logger.exception("Error processing file %s", file_path)
            return None
        else:
            return labels, test_data, stats_data, samples, jitter, error_counters

    def _status_error_delta_total(self, series: dict[str, object]) -> int:
        """Aggregate status delta error counters for one series."""
        status_delta = series.get("status_delta")
        if not isinstance(status_delta, dict):
            return 0
        statistics = status_delta.get("statistics")
        if not isinstance(statistics, dict):
            return 0
        return int(
            sum(int(statistics.get(key, 0)) for key in STATUS_ERROR_KEYS),
        )

    def plot_boxplot(
        self,
        labels: list[str],
        test_data: list[np.ndarray],
        stats_data: list[dict[str, float]],
        samples: int,
        jitter: bool,  # noqa: FBT001
    ) -> None:
        """Plot the processed data."""
        try:
            fig, (ax1, ax2) = plt.subplots(
                2,
                1,
                figsize=(10, 10),
                gridspec_kw={"height_ratios": [2, 1]},
                sharex=True,
            )

            fig.suptitle(f"Test Results Visualization (jitter = {jitter})", fontsize=12)

            # Add explanatory text for the entire figure
            explanation_text = (
                "Variable Explanations:\n"
                "• t: Test name identifier  "
                "• w.time: Waiting time between messages (ms)  "
                "• baud: UART baud rate  "
                "• bitrate: Effective data throughput (bits/s)\n"
                "• Avg/Min/Max: Average, minimum, and maximum "
                "roundtrip latency (ms)  "
                "• P95: 95th percentile latency - 95% of messages "
                "responded faster\n"
                "• ErrΔ / Status Δ Errors: Delta in controller error "
                "counters (COBS, checksum, queue errors)\n"
                "• Backlog End: Outstanding messages not yet "
                "acknowledged at end of test  "
                "• Dropped: Messages sent but no response received "
                "within timeout\n"
                "• Jitter: Random delays added to simulate network "
                "variability"
            )

            fig.text(
                0.5,
                0.01,
                explanation_text,
                ha="center",
                va="bottom",
                fontsize=8,
                bbox={
                    "boxstyle": "round,pad=0.5",
                    "edgecolor": "blue",
                    "facecolor": "lightblue",
                    "alpha": 0.7,
                },
                wrap=True,
            )

            # Boxplot
            boxplot = ax1.boxplot(test_data, showmeans=True, patch_artist=True)
            ax1.set_title(f"Latency Percentiles (Samples = {samples})", fontsize=10)
            ax1.set_ylabel("Latency (ms) - Log Scale")
            ax1.set_yscale("log")
            ax1.grid(axis="y", linestyle="--", alpha=0.7)
            ax1.yaxis.grid(linestyle="--", alpha=0.2, which="both")
            plt.setp(ax1.get_xticklabels(), rotation=45, ha="right")

            # Add statistics box for each boxplot
            for _, (line, stat) in enumerate(
                zip(boxplot["medians"], stats_data, strict=True)
            ):
                x = line.get_xydata()[1][0]
                stats_text = (
                    f"Avg: {stat['avg']:.1f}\n"
                    f"Min: {stat['min']:.1f}\n"
                    f"Max: {stat['max']:.1f}\n"
                    f"P95: {stat['p95']:.1f}\n"
                    f"ErrΔ: {stat.get('status_error_delta_total', 0):.0f}\n"
                    f"Backlog: {stat.get('outstanding_final', 0):.0f}"
                )

                # Posicionar texto à direita do boxplot
                ax1.text(
                    x - 0.6,  # x position
                    ax1.get_ylim()[0] + 8,  # y position at the bottom
                    stats_text,
                    ha="left",
                    va="top",
                    fontsize=8,
                    bbox=self.bbox_props,
                )

            # Dropped messages subplot
            x = np.arange(len(labels)) + 1
            width = 0.25

            dropped_bars = ax2.bar(
                x - width,
                [s.get("dropped_messages", 0) for s in stats_data],
                width=width,
                label="Dropped",
                alpha=0.85,
            )
            status_error_bars = ax2.bar(
                x,
                [s.get("status_error_delta_total", 0) for s in stats_data],
                width=width,
                label="Status Δ Errors",
                alpha=0.85,
            )
            backlog_bars = ax2.bar(
                x + width,
                [s.get("outstanding_final", 0) for s in stats_data],
                width=width,
                label="Backlog End",
                alpha=0.85,
            )

            # Add data labels on bars
            for bar in [*dropped_bars, *status_error_bars, *backlog_bars]:
                height = bar.get_height()
                ax2.text(
                    bar.get_x() + bar.get_width() / 2.0,
                    height,
                    f"{height:.2f}",
                    ha="center",
                    fontsize=8,
                    bbox=self.bbox_props,
                )

            ax2.set_ylabel("Dropped Messages")
            ax2.set_title("Dropped Messages Statistics", fontsize=10)
            ax2.set_xticks(x)
            ax2.set_xticklabels(labels, fontsize=8)
            ax2.legend()
            ax2.grid(axis="y", linestyle="--", alpha=0.7)
            plt.setp(ax2.get_xticklabels(), rotation=45, ha="right")

            # Adjust layout to make room for x-tick labels and explanation text
            plt.tight_layout()
            plt.subplots_adjust(bottom=0.28)

            plt.show()

        except Exception:
            logger.exception("Error occurred while plotting.")

    def plot_histogram(
        self,
        test_data: list[np.ndarray],
        labels: list[str],
        stats_data: list[dict[str, float]],
    ) -> None:
        """Plot all histograms in the same plot."""
        try:
            fig, axes = plt.subplots(1, len(test_data), figsize=(15, 5), sharey=True)
            plt.subplots_adjust(wspace=0)
            fig.suptitle("Histogram of Test Results", fontsize=12)

            # Add explanatory text
            explanation_text = (
                "Variable Explanations:\n"
                "• t: Test name identifier  "
                "• w.time: Waiting time between messages (ms)  "
                "• baud: UART baud rate  "
                "• bitrate: Effective data throughput (bits/s)\n"
                "• Latency: Roundtrip time from message send to "
                "response receipt (ms)  "
                "• P95: 95th percentile - the latency threshold below "
                "which 95% of messages fall"
            )

            fig.text(
                0.5,
                0.01,
                explanation_text,
                ha="center",
                va="bottom",
                fontsize=9,
                bbox={
                    "boxstyle": "round,pad=0.5",
                    "edgecolor": "blue",
                    "facecolor": "lightblue",
                    "alpha": 0.7,
                },
                wrap=True,
            )

            if len(test_data) == 1:
                axes = [axes]

            colors = cm.get_cmap("viridis")(np.linspace(0, 1, len(test_data)))

            for ax, data, label, color, stat in zip(
                axes, test_data, labels, colors, stats_data, strict=True
            ):
                ax.hist(
                    data,
                    bins=50,
                    alpha=0.75,
                    label=label,
                    color=color,
                    histtype="stepfilled",
                )
                # Add p95 line
                p95 = stat["p95"]
                ax.axvline(p95, color=color, linestyle="--", alpha=1.0)

                # Add p95 text label
                ax.text(
                    p95,
                    ax.get_ylim()[1],
                    f"P95: {p95:.1f}ms",
                    rotation=90,
                    va="top",
                    ha="right",
                    bbox=self.bbox_props,
                )
                ax.set_title(label, fontsize=10)
                ax.set_xlabel("Latency (ms)")
                ax.grid(axis="y", linestyle="--", alpha=0.7)

            ax.set_xlabel("Latency (ms)")
            ax.grid(axis="y", linestyle="--", alpha=0.7)
            ax.legend()
            plt.tight_layout()

            # Adjust layout to make room for explanation text
            plt.subplots_adjust(bottom=0.18)

            plt.show()

        except Exception:
            logger.exception("Error occurred while plotting histograms.")

    def plot_controller_health(
        self,
        labels: list[str],
        stats_data: list[dict[str, float]],
    ) -> None:
        """Plot controller health trends across series."""
        try:
            x = np.arange(len(labels))
            status_errors = [s.get("status_error_delta_total", 0) for s in stats_data]
            backlog_end = [s.get("outstanding_final", 0) for s in stats_data]
            backlog_max = [s.get("outstanding_max", 0) for s in stats_data]

            fig, axes = plt.subplots(2, 1, figsize=(11, 8), sharex=True)
            fig.suptitle("Controller Health Trends", fontsize=12)

            # Add explanatory text
            explanation_text = (
                "Variable Explanations:\n"
                "• t: Test name identifier  "
                "• w.time: Waiting time between messages (ms)  "
                "• baud: UART baud rate  "
                "• bitrate: Effective data throughput (bits/s)\n"
                "• Status Error Δ: Change in controller error counters "
                "(queue errors, COBS decode errors, checksum errors, "
                "buffer overflows, etc.)\n"
                "• Backlog End: Number of outstanding unacknowledged "
                "messages at end of test series  "
                "• Backlog Max: Peak number of outstanding messages "
                "during test series\n"
                "• Healthy controller: Low error delta, backlog returns "
                "to zero"
            )

            fig.text(
                0.5,
                0.01,
                explanation_text,
                ha="center",
                va="bottom",
                fontsize=9,
                bbox={
                    "boxstyle": "round,pad=0.5",
                    "edgecolor": "blue",
                    "facecolor": "lightblue",
                    "alpha": 0.7,
                },
                wrap=True,
            )

            axes[0].bar(x, status_errors, color="tab:red", alpha=0.85)
            axes[0].set_ylabel("Status Error Δ")
            axes[0].set_title("Error Delta per Series", fontsize=10)
            axes[0].grid(axis="y", linestyle="--", alpha=0.7)

            axes[1].plot(
                x,
                backlog_end,
                marker="o",
                linestyle="-",
                linewidth=1.5,
                label="Backlog End",
            )
            axes[1].plot(
                x,
                backlog_max,
                marker="^",
                linestyle="--",
                linewidth=1.5,
                label="Backlog Max",
            )
            axes[1].set_ylabel("Outstanding Messages")
            axes[1].set_title("Backlog per Series", fontsize=10)
            axes[1].set_xticks(x)
            axes[1].set_xticklabels(labels, fontsize=8)
            axes[1].grid(axis="y", linestyle="--", alpha=0.7)
            axes[1].legend()
            plt.setp(axes[1].get_xticklabels(), rotation=45, ha="right")

            plt.tight_layout()

            # Adjust layout to make room for explanation text
            plt.subplots_adjust(bottom=0.20)

            plt.show()

        except Exception:
            logger.exception("Error occurred while plotting controller health.")

    def plot_error_counter_details(  # noqa: PLR0915
        self,
        labels: list[str],
        error_counters: list[dict[str, int]],
    ) -> None:
        """Plot detailed error counter changes before and after each test."""
        try:
            # Prepare data for visualization
            num_series = len(labels)
            error_types = list(STATUS_ERROR_KEYS)
            num_errors = len(error_types)

            # Create matrix for heatmap
            error_matrix = np.zeros((num_errors, num_series))
            for i, error_type in enumerate(error_types):
                for j, counters in enumerate(error_counters):
                    error_matrix[i, j] = counters.get(error_type, 0)

            # Filter out error types with no occurrences
            has_errors = error_matrix.sum(axis=1) > 0
            filtered_error_types = [
                error_types[i] for i in range(num_errors) if has_errors[i]
            ]
            filtered_error_matrix = error_matrix[has_errors]
            filtered_friendly_names = [
                STATISTICS_DISPLAY_NAMES.get(et, et) for et in filtered_error_types
            ]

            if len(filtered_error_types) == 0:
                print("\n✅ No errors detected across all test series!")
                print("Controller health is excellent - all error counters are zero.\n")
                return

            # Create figure with subplots
            fig = plt.figure(figsize=(14, 10))
            gs = fig.add_gridspec(3, 1, height_ratios=[2, 1.5, 0.8], hspace=0.3)

            fig.suptitle(
                "Detailed Error Counter Analysis - Before/After Test Series",
                fontsize=14,
                fontweight="bold",
            )

            # Subplot 1: Stacked bar chart
            ax1 = fig.add_subplot(gs[0])
            x = np.arange(num_series)
            bottom = np.zeros(num_series)

            # Use colormap for different error types
            colors = cm.get_cmap("tab20")(np.linspace(0, 1, len(filtered_error_types)))

            for i, (error_type, friendly_name) in enumerate(
                zip(filtered_error_types, filtered_friendly_names, strict=False)
            ):
                values = [counters.get(error_type, 0) for counters in error_counters]
                ax1.bar(
                    x,
                    values,
                    bottom=bottom,
                    label=friendly_name,
                    color=colors[i],
                    alpha=0.85,
                )
                bottom += values

            ax1.set_ylabel("Error Count (Δ)", fontsize=11)
            ax1.set_title(
                "Error Counter Changes per Test Series (Stacked)", fontsize=12
            )
            ax1.set_xticks(x)
            ax1.set_xticklabels(labels, fontsize=8, rotation=45, ha="right")
            ax1.grid(axis="y", linestyle="--", alpha=0.4)
            ax1.legend(
                bbox_to_anchor=(1.02, 1),
                loc="upper left",
                fontsize=8,
                framealpha=0.9,
            )

            # Subplot 2: Heatmap
            ax2 = fig.add_subplot(gs[1])
            im = ax2.imshow(
                filtered_error_matrix,
                aspect="auto",
                cmap="YlOrRd",
                interpolation="nearest",
            )

            ax2.set_xticks(np.arange(num_series))
            ax2.set_yticks(np.arange(len(filtered_error_types)))
            ax2.set_xticklabels(labels, fontsize=8, rotation=45, ha="right")
            ax2.set_yticklabels(filtered_friendly_names, fontsize=9)
            ax2.set_xlabel("Test Series", fontsize=11)
            ax2.set_ylabel("Error Type", fontsize=11)
            ax2.set_title("Error Distribution Heatmap", fontsize=12)

            # Add colorbar
            cbar = plt.colorbar(im, ax=ax2)
            cbar.set_label("Error Count", rotation=270, labelpad=15)

            # Add text annotations on heatmap
            for i in range(len(filtered_error_types)):
                for j in range(num_series):
                    value = int(filtered_error_matrix[i, j])
                    if value > 0:
                        threshold = filtered_error_matrix.max() / 2
                        text_color = "white" if value > threshold else "black"
                        ax2.text(
                            j,
                            i,
                            str(value),
                            ha="center",
                            va="center",
                            color=text_color,
                            fontsize=8,
                            fontweight="bold",
                        )

            # Subplot 3: Summary statistics
            ax3 = fig.add_subplot(gs[2])
            ax3.axis("off")

            # Calculate summary statistics
            total_errors = sum(sum(c.values()) for c in error_counters)
            max_errors_series = max(sum(c.values()) for c in error_counters)
            series_with_errors = sum(1 for c in error_counters if sum(c.values()) > 0)

            # Most common error type
            error_totals = {
                error_type: sum(c.get(error_type, 0) for c in error_counters)
                for error_type in filtered_error_types
            }
            most_common_error = max(error_totals, key=lambda x: error_totals[x])
            most_common_count = error_totals[most_common_error]

            most_common_name = STATISTICS_DISPLAY_NAMES.get(
                most_common_error, most_common_error
            )
            summary_text = (
                "📊 Summary Statistics:\n"
                f"  • Total errors across all series: {total_errors:,}\n"
                f"  • Series with errors: {series_with_errors}/{num_series}\n"
                f"  • Maximum errors in single series: {max_errors_series:,}\n"
                f"  • Most common error: {most_common_name} "
                f"({most_common_count:,} occurrences)\n"
                f"  • Unique error types detected: "
                f"{len(filtered_error_types)}/{len(error_types)}"
            )

            ax3.text(
                0.5,
                0.5,
                summary_text,
                ha="center",
                va="center",
                fontsize=10,
                bbox={
                    "boxstyle": "round,pad=0.8",
                    "edgecolor": "darkblue",
                    "facecolor": "lightcyan",
                    "alpha": 0.9,
                },
                family="monospace",
            )

            # Add explanatory note
            explanation_text = (
                "Variable Explanations:\n"
                "• t: Test name identifier  "
                "• w.time: Waiting time between messages (ms)  "
                "• baud: UART baud rate  "
                "• bitrate: Effective data throughput (bits/s)\n"
                "• Error Count (Δ): Change in error counters "
                "during test series  "
                "• Queue errors: Message queue congestion  "
                "• COBS/Checksum errors: Communication integrity "
                "issues\n"
                "• Buffer overflow: Data rate exceeds processing "
                "capacity  "
                "• Output/Input errors: Hardware initialization or "
                "configuration issues"
            )

            fig.text(
                0.5,
                0.01,
                explanation_text,
                ha="center",
                va="bottom",
                fontsize=9,
                bbox={
                    "boxstyle": "round,pad=0.6",
                    "edgecolor": "green",
                    "facecolor": "lightgreen",
                    "alpha": 0.7,
                },
            )

            plt.subplots_adjust(bottom=0.15, right=0.88)
            plt.show()

        except Exception:
            logger.exception("Error occurred while plotting error counter details.")

    def visualize_test_results(self) -> None:
        """Plot results."""
        file_path = self.select_test_file()
        if file_path is None:
            return

        processed_data = self.load_and_process_data(file_path)
        if processed_data is None:
            return

        labels, test_data, stats_data, samples, jitter, error_counters = processed_data
        print("Select visualization type:")
        print("1. Boxplot")
        print("2. Histogram")
        print("3. Controller health")
        print("4. Error counter details")
        choice = input("Enter choice (1, 2, 3 or 4): ")

        if choice == "1":
            self.plot_boxplot(labels, test_data, stats_data, samples, jitter=jitter)
        elif choice == "2":
            self.plot_histogram(test_data, labels, stats_data)
        elif choice == "3":
            self.plot_controller_health(labels, stats_data)
        elif choice == "4":
            self.plot_error_counter_details(labels, error_counters)
        else:
            print("Invalid choice. Please select 1, 2, 3 or 4.")

    def execute_visualization(self) -> None:
        """Execute visualization."""
        self.visualize_test_results()
