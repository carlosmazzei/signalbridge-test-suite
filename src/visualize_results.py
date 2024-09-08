import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from logger import Logger


class VisualizeResults:
    """Class to visualize the log files and plot it."""

    def __init__(self, logger: Logger):
        """Initialize the class with a logger instance."""
        self.logger = logger

    def select_test_file(self) -> Path | None:
        """Select a test file from the tests folder."""
        tests_folder: Path = Path(__file__).parent.parent / "tests"
        files: list[Path] = sorted(tests_folder.glob("*.json"))
        if not files:
            self.logger.display_log("No test files found in the tests folder.")
            return None

        page_size: int = 10
        current_page: int = 0

        while True:
            start_idx: int = current_page * page_size
            end_idx: int = start_idx + page_size
            page_files: list = files[start_idx:end_idx]

            print("\nTest files:")
            for idx, file in enumerate(page_files, start=1):
                print(f"{idx}. {file.name}")

            print("\nOptions:")
            print("n - Next page")
            print("p - Previous page")
            print("q - Return to main menu")

            choice = input("Enter your choice (number, n, p, or q): ").lower()

            if choice == "n" and end_idx < len(files):
                current_page += 1
            elif choice == "p" and current_page > 0:
                current_page -= 1
            elif choice == "q":
                return None
            elif choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(page_files):
                    return page_files[idx]
                print("Invalid file number. Please try again.")
            else:
                print("Invalid input. Please try again.")

    def visualize_test_results(self) -> None:
        """Plot results."""
        file_path = self.select_test_file()
        if file_path is None:
            return

        with Path(file_path).open() as f:
            data = json.load(f)

        labels = []
        test_data = []
        stats_data = []

        for series in data:
            series_data = np.array(series["results"]) * 1000
            waiting_time = format(series["waiting_time"] * 1000, ".0f")
            series_name = f"t: {series['test']}\nw.time:\n{waiting_time}"
            labels.append(series_name)
            test_data.append(series_data)

            stats_data.append(
                {
                    "avg": series["latency_avg"] * 1000,
                    "min": series["latency_min"] * 1000,
                    "max": series["latency_max"] * 1000,
                    "p95": series["latency_p95"] * 1000,
                },
            )

        _, (ax1, ax2) = plt.subplots(
            2,
            1,
            figsize=(12, 10),
            gridspec_kw={"height_ratios": [2, 1]},
        )

        # Boxplot
        ax1.boxplot(test_data, labels=labels, showmeans=True)
        ax1.set_title(f"Latency Percentiles (Samples = {series["samples"]})")
        ax1.set_xlabel("Test cases / waiting time in ms")
        ax1.set_ylabel("Latency (ms)")
        ax1.set_yscale("log")
        ax1.grid(axis="y", linestyle="--", alpha=0.7)
        plt.setp(ax1.get_xticklabels(), rotation=45, ha="right")

        # Statistics subplot
        x = np.arange(len(labels))
        width = 0.2

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

        ax2.set_ylabel("Latency (ms)")
        ax2.set_title("Latency Statistics")
        ax2.set_xticks(x)
        ax2.set_xticklabels(labels)
        ax2.legend()
        ax2.grid(axis="y", linestyle="--", alpha=0.7)
        plt.setp(ax2.get_xticklabels(), rotation=45, ha="right")

        plt.tight_layout()
        plt.show()

    def execute_visualization(self) -> None:
        """Execute visualization."""
        self.visualize_test_results()
