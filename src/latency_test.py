import os
import time
import datetime
import json
import random
from cobs import cobs
from alive_progress import alive_bar


class LatencyTest:
    """Latency test class. Implement a roundtrip message to measure timing"""

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, ser, logger):
        self.logger = logger
        self.ser = ser
        self.latency_message = [0] * 255
        self.latency_results = []

    # Send 10 byte message to the interface and wait for response. Log the time taken.
    def publish(self, iteration_counter: int):
        """Function to send messages"""

        header = bytes([0x00, 0x34, 0x03, 0x01, 0x02])
        counter = iteration_counter.to_bytes(1, byteorder="big")
        payload = header + counter

        start_time = time.time()
        self.latency_message[int.from_bytes(counter, byteorder="big")] = start_time

        message = cobs.encode(payload)
        message += b"\x00"
        self.ser.write(message)
        print(f"Published (encoded) `{message}`, counter {counter}")

    # Main test
    def main_test(
        self, num_times=10, max_wait=0.5, min_wait=0, samples=255, jitter=False
    ):
        """Execute the main test given the desired parameters"""

        # Get the current date and time
        current_datetime = datetime.datetime.now()
        # Format the date and time as a string
        formatted_datetime = current_datetime.strftime("%Y%m%d_%H%M%S")
        # Output filename
        filename = "output.json"
        output_filename = f"{formatted_datetime}_{filename}"
        # Format the output directory path
        script_directory = os.path.dirname(os.path.abspath(__file__))
        project_root_relative_path = ".."  # Move up one level to the project root
        tests_folder_relative_path = "tests"
        file_path = os.path.join(
            script_directory,
            project_root_relative_path,
            tests_folder_relative_path,
            output_filename,
        )
        # Open the file in append mode
        with open(file_path, "w", encoding="utf-8") as output_file:

            # Prepare the data to store in JSON format
            output_data = []
            latency_results_copy = [[] for _ in range(num_times)]
            bar_title = f"Test / Jitter: {jitter}"

            # Loop for each byte
            with alive_bar(samples * num_times, title=bar_title) as pbar:
                for j in range(num_times):
                    self.latency_results.clear()

                    # Calculate the waiting time
                    waiting_time = min_wait + (max_wait - min_wait) * (
                        j / (num_times - 1)
                    )
                    print(f"Test {j}, waiting time: {waiting_time} s")
                    random_max = (max_wait - min_wait) * 0.2

                    for i in range(0, samples):
                        self.publish(i)
                        if jitter is True:
                            # Sleep for a random amount of time
                            time.sleep(waiting_time + random.uniform(0, random_max))
                        else:
                            time.sleep(waiting_time)
                        pbar()

                    # Calculate the average latency
                    latency_avg = sum(self.latency_results) / len(self.latency_results)
                    print(f"Average latency: {latency_avg * 1e3} ms")
                    # Calculate minimum latency
                    latency_min = min(self.latency_results)
                    print(f"Minimum latency: {latency_min * 1e3} ms")
                    # Calculate maximum latency
                    latency_max = max(self.latency_results)
                    print(f"Maximum latency: {latency_max * 1e3} ms")
                    latency_results_copy[j] = self.latency_results.copy()

                    # Write the data to the output file
                    output_data.append(
                        {
                            "test": j,
                            "sample": samples,
                            "waiting_time": waiting_time,
                            "results": latency_results_copy[j],
                            "latency_avg": latency_avg,
                            "latency_min": latency_min,
                            "latency_max": latency_max,
                        }
                    )

                    # Sleep for 10 seconds
                    print("Waiting for 5 seconds to collect results...")
                    time.sleep(5)

            # Close output file
            json.dump(output_data, output_file, indent=4)
            output_file.flush()
            output_file.close()

    def handle_message(self, command, decoded_data):
        """Handle the return message. Calculate roundtrip time and store"""

        if command == 20:
            try:
                counter = decoded_data[5]
                latency = time.time() - self.latency_message[counter]
                self.latency_results.append(latency)
                print(f"Message {counter} latency: {latency * 1e3} ms")

            except IndexError:
                print("Invalid message (Index Error)")
                return

    def execute_test(self):
        """Main test function"""

        if self.ser is None:
            print("No serial port found. Quitting test.")
            return

        try:
            print(
                "Waiting to start test for 5 seconds (press CTRL+C to interrupt test)..."
            )
            time.sleep(5)

            # Run the test
            self.main_test(num_times=10, max_wait=0.7, min_wait=0, samples=255)

            # Run again with jitter
            self.main_test(
                num_times=10, max_wait=0.7, min_wait=0, samples=255, jitter=True
            )

            print("Test ended")
        except KeyboardInterrupt:
            pass
