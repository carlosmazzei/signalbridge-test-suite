"""Module to visualize the test results."""

import json
import logging
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from const import TEST_RESULTS_FOLDER
from logger_config import setup_logging

setup_logging()

logger = logging.getLogger(__name__)


class VisualizeResults:
    """Class to visualize the log files and plot it."""

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
        print(f"(Page {current_page + 1} of {total_files // page_size + 1})")

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
    ) -> tuple[list[str], list[np.ndarray], list[dict[str, float]], int, bool] | None:
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
            samples = 0
            jitter = False

            for series in data:
                series_data = np.array(series["results"]) * 1000
                waiting_time = format(series["waiting_time"] * 1000, ".0f")
                bitrate = format(series["bitrate"], ".0f")
                jitter = series["jitter"]
                series_name = (
                    f"t: {series['test']}\nw.time:\n{waiting_time}\nbitrate: {bitrate}"
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
                    },
                )

            if not test_data:
                msg = "No valid data to visualize."
                raise ValueError(msg)  # noqa: TRY301

        except (OSError, KeyError, TypeError, ValueError):
            logger.exception("Error processing file %s", file_path)
            return None
        else:
            return labels, test_data, stats_data, samples, jitter

    def plot_data(
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
                figsize=(10, 8),
                gridspec_kw={"height_ratios": [2, 1]},
                sharex=True,
            )

            fig.suptitle(f"Test Results Visualization (jitter = {jitter})", fontsize=12)

            # Boxplot
            ax1.boxplot(test_data, showmeans=True)
            ax1.set_title(f"Latency Percentiles (Samples = {samples})", fontsize=10)
            ax1.set_ylabel("Latency (ms)")
            ax1.set_yscale("log")
            ax1.grid(axis="y", linestyle="--", alpha=0.7)
            plt.setp(ax1.get_xticklabels(), rotation=45, ha="right")

            # Statistics subplot
            x = np.arange(len(labels)) + 1
            width = 0.1

            ax2.bar(
                x - 1.5 * width,
                [s["avg"] for s in stats_data],
                width,
                label="Avg",
                alpha=0.8,
            )
            ax2.bar(
                x - 0.5 * width,
                [s["min"] for s in stats_data],
                width,
                label="Min",
                alpha=0.8,
            )
            ax2.bar(
                x + 0.5 * width,
                [s["max"] for s in stats_data],
                width,
                label="Max",
                alpha=0.8,
            )
            ax2.bar(
                x + 1.5 * width,
                [s["p95"] for s in stats_data],
                width,
                label="P95",
                alpha=0.8,
            )
            ax2.bar(
                x + 2.5 * width,
                [s["dropped_messages"] for s in stats_data],
                width,
                label="Dropped",
                alpha=0.8,
            )

            ax2.set_ylabel("Latency (ms)")
            ax2.set_title("Latency Statistics", fontsize=10)
            ax2.set_xticks(x)
            ax2.set_xticklabels(labels, fontsize=8)
            ax2.set_yscale("log")
            ax2.legend()
            ax2.grid(axis="y", linestyle="--", alpha=0.7)
            plt.setp(ax2.get_xticklabels(), rotation=45, ha="right")

            plt.tight_layout()
            plt.show()

        except Exception:
            logger.exception("Error occurred while plotting.")

    def visualize_test_results(self) -> None:
        """Plot results."""
        file_path = self.select_test_file()
        if file_path is None:
            return

        processed_data = self.load_and_process_data(file_path)
        if processed_data is None:
            return

        labels, test_data, stats_data, samples, jitter = processed_data
        self.plot_data(labels, test_data, stats_data, samples, jitter)

    def execute_visualization(self) -> None:
        """Execute visualization."""
        self.visualize_test_results()
