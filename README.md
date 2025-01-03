# UART Test Routines

This project includes UART testing tools for the simulator interface, featuring a latency test and a simple interface to send commands.

## Features

- UART Latency test for ESP32 and CP2102
- Simple interface to send custom commands
- Regression testing capabilities
- Extensible architecture for adding new test modes

## Project Setup

1. **Install Python:**
   Ensure Python 3.7+ is installed on your system. Download from [python.org](https://www.python.org/downloads/).

2. **Clone the Repository:**

   ```sh
   git clone https://github.com/carlosmazzei/uart-latency-test.git
   cd uart-latency-test
   ```

3. **Create and Activate a Virtual Environment:**

   ```sh
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

4. **Install Dependencies:**

   ```sh
   pip install -r requirements.txt
   ```

## Running the Application

Execute the main script:

```sh
python src/main.py
```

You'll see the following menu:

```sh
1. Run latency test
2. Send command
3. Regression test
4. Exit
```

### 1. Run Latency Test

This option initiates the UART latency test. The test message format is:

| Byte 0 | Byte 1 | Byte 2 | Byte 3 | Byte 4 | Byte 5 | Byte 6 | Byte 7 | Byte 8 | Byte 9 |
| ------ | ------ | ------ | ------ | ------ | ------ | ------ | ------ | ------ | ------ |
| 0x00   | 0x34   | 0x03   | 0x01   | 0x02   | 0x03   | ?      | ?      | ?      | ?      |

- Id: 1 (First 11 bits)
- Cmd: 20 (PC_ECHO_CMD) (5 bits)
- Length: 3
- Data: [0x01, 0x02, 0x03]

Test results are saved in `./tests/{timestamp}_output.json`.

### 2. Send Command

Use this option to send custom commands for testing other functions. For example, to request heap status:

| Byte 0 | Byte 1 | Byte 2 | Byte 3 | Byte 4 | Byte 5 | Byte 6 | Byte 7 | Byte 8 | Byte 9 |
| ------ | ------ | ------ | ------ | ------ | ------ | ------ | ------ | ------ | ------ |
| 0x00   | 0x38   | 0x01   | 0x01   | ?      | ?      | ?      | ?      | ?      | ?      |

### 3. Regression Test

Runs a series of predefined tests to ensure system stability and performance.

## Configuration

You can modify test parameters in `src/latency_test.py`:

```python
app_manager.run_latency_test(num_times=10, max_wait=0.5, min_wait=0, samples=255, jitter=False)
```

- `num_times`: Number of test iterations
- `max_wait`: Maximum wait time between samples (seconds)
- `min_wait`: Minimum wait time between samples (seconds)
- `samples`: Number of samples per test (max 255)
- `jitter`: Add random jitter to wait times (boolean)

## Development

### Adding New Test Modes

1. Create a new module in the `src/` directory.
2. Implement the test logic.
3. Add a new method in `ApplicationManager` to run the test.
4. Update the main menu in `application_manager.py` to include the new test option.

### Modifying Existing Tests

- Latency Test: Update `LatencyTest` class in `src/latency_test.py`.
- Regression Tests: Modify `src/regression_tests.py`.

## Troubleshooting

- Ensure the correct COM port is set in `latency_test.py`.
- Verify that the UART device is properly connected and recognized by your system.
- Check the log output for any error messages or unexpected behavior.

## Contributing

1. Fork the repository.
2. Create a new branch for your feature.
3. Commit your changes and push to your fork.
4. Create a pull request with a description of your changes.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
