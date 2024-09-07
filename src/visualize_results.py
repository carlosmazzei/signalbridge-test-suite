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

        for series in data:
            series_data = np.array(series["results"]) * 1000
            waiting_time = format(series["waiting_time"] * 1000, ".0f")
            series_name = f"t: {series['test']}\nw.time:\n{waiting_time}"
            labels.append(series_name)
            test_data.append(series_data)

        _, ax = plt.subplots(figsize=(12, 6))
        ax.boxplot(test_data, label=labels, showmeans=True)
        ax.set_title("Latency percentiles")
        ax.set_xlabel("Test cases / waiting time in ms")
        ax.set_ylabel("Latency (ms)")
        plt.yscale("log")
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()
        plt.show()

    def execute_visualization(self) -> None:
        """Execute visualization."""
        self.visualize_test_results()
