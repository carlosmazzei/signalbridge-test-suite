<!-- markdownlint-disable MD033 MD041 -->
<div align="center">
<img src="https://github.com/carlosmazzei/signalbridge-controller/blob/main/assets/logo-pimatrix-dark.png#gh-dark-mode-only" alt="Signalbridge" width="150">
<img src="https://github.com/carlosmazzei/signalbridge-controller/blob/main/assets/logo-pimatrix-light.png#gh-light-mode-only" alt="Signalbridge" width="150">
</div>
<!-- markdownlint-enable MD033 MD041 -->

# SignalBridge - Test Suite

[![Tests](https://github.com/carlosmazzei/signalbridge-test-suite/actions/workflows/lint.yml/badge.svg)](https://github.com/carlosmazzei/signalbridge-test-suite/actions/workflows/lint.yml)
[![Coverage](https://codecov.io/gh/carlosmazzei/signalbridge-test-suite/branch/main/graph/badge.svg)](https://codecov.io/gh/carlosmazzei/signalbridge-test-suite)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

A comprehensive Python testing suite for the SignalBridge controller, featuring UART latency measurement, command interface, regression testing, system monitoring, and statistical visualization. Designed for testing embedded systems communication with high precision and detailed performance analysis.

> [!TIP]
> This test suite is designed for the Raspberry Pi Pico-based SignalBridge controller firmware.

**Related repositories:**

- [SignalBridge breakout board](https://github.com/carlosmazzei/signalbridge-board) - Hardware design
- [SignalBridge test suite](https://github.com/carlosmazzei/signalbridge-test-suite) - This repository
- [SignalBridge firmware](https://github.com/carlosmazzei/signalbridge-controller) - Embedded C firmware

## 🚀 Quick Start

### Option 1: Automated Setup (Recommended)

```bash
# Clone and setup in one command
git clone https://github.com/carlosmazzei/signalbridge-test-suite.git
cd signalbridge-test-suite
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python src/main.py
```

### Option 2: Manual Setup

1. **Install Python 3.14+:**
   Download from [python.org](https://www.python.org/downloads/)

2. **Clone and Setup:**

   ```bash
   git clone https://github.com/carlosmazzei/signalbridge-test-suite.git
   cd signalbridge-test-suite
   ```

3. **Create Virtual Environment:**

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

4. **Install Dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

## ✨ Features

### Core Testing Capabilities

- **UART Latency Testing**: High-precision roundtrip latency measurement with statistical analysis
- **Command Interface**: Interactive command sending with real-time response monitoring
- **Regression Testing**: Automated test suite for system validation
- **System Monitoring**: Real-time statistics and task performance monitoring
- **Result Visualization**: Advanced plotting with matplotlib for test analysis
- **Extensible Architecture**: Modular design for adding new test modes

### Technical Features

- **COBS Protocol Support**: Consistent Overhead Byte Stuffing for reliable communication
- **Hardware Flow Control**: RTS/CTS support for robust serial communication
- **Checksum Validation**: XOR checksum verification for data integrity
- **Multi-threaded Design**: Separate threads for reading, processing, and user interaction
- **Buffer Management**: Intelligent buffer handling with overflow protection
- **Statistical Analysis**: Comprehensive latency statistics including P95 percentiles

## 📋 System Requirements

### Hardware Requirements

- **Target Device**: SignalBridge controller (Raspberry Pi Pico-based)
- **Serial Connection**: USB or UART interface
- **Host System**: Windows, macOS, or Linux

### Software Requirements

- **Python**: 3.14 or higher
- **Serial Port**: Access to `/dev/cu.usbmodem1234561` (configurable)
- **Display**: For visualization features (matplotlib)

## ⚙️ Configuration

### Serial Communication Settings

Default configuration (defined in `src/const.py`):

```python
PORT_NAME = "/dev/cu.usbmodem1234561"  # Serial port path
BAUDRATE = 115200                       # Communication speed
TIMEOUT = 0.1                          # Read timeout in seconds
TEST_RESULTS_FOLDER = "test_results"    # Output directory
```

### Latency Test Parameters

Configurable parameters with defaults:

| Parameter        | Default | Range   | Description                    |
| ---------------- | ------- | ------- | ------------------------------ |
| `num_times`      | 5       | 1-∞     | Number of test iterations      |
| `max_wait`       | 0.1s    | 0-∞     | Maximum wait between samples   |
| `min_wait`       | 0s      | 0-∞     | Minimum wait between samples   |
| `samples`        | 255     | 1-65536 | Samples per test iteration     |
| `message_length` | 10      | 6-10    | Message payload length (bytes) |
| `jitter`         | false   | bool    | Add random timing variations   |

### Buffer Management

Serial interface buffer settings:

```python
MAX_BUFFER_SIZE = 1024      # Maximum buffer size
BUFFER_HIGH_WATER = 768     # 75% - flow control threshold
BUFFER_LOW_WATER = 256      # 25% - flow control resume
```

## 🎯 Usage Guide

### Main Application Menu

Execute the application:

```bash
python src/main.py
```

Available options:

```bash
1. Run latency test
2. Send command
3. Regression test
4. Visualize test results
5. Status mode
6. Exit
```

### 1. Latency Test

High-precision roundtrip latency measurement with configurable parameters.

**Test Message Format:**

| Byte 0 | Byte 1 | Byte 2 | Byte 3       | Byte 4      | Byte 5-9    |
| ------ | ------ | ------ | ------------ | ----------- | ----------- |
| 0x00   | 0x34   | Length | Counter High | Counter Low | Random Data |

**Protocol Details:**

- **Header**: `0x00 0x34` (fixed)
- **Command**: 20 (PC_ECHO_CMD) embedded in byte 1
- **ID**: First 11 bits for message identification
- **Length**: Variable payload length (6-10 bytes total)
- **Counter**: 16-bit packet identifier for correlation
- **Payload**: Random data for integrity verification

**Interactive Configuration:**

The test prompts for six parameters:

1. Number of test iterations (default: 5)
2. Minimum wait time in ms (default: 0)  
3. Maximum wait time in ms (default: 100)
4. Number of samples per test (default: 255)
5. Wait time between tests in seconds (default: 3)
6. Enable jitter (default: false)
7. Message length in bytes (default: 10, range: 6-10)

**Output:**
Results saved to `./test_results/{timestamp}_output.json` with:

- Individual latency measurements
- Statistical analysis (avg, min, max, P95)
- Dropped message count
- Bitrate calculations
- Test configuration parameters

### 2. Command Interface

Interactive command sending with real-time monitoring.

**Supported Commands:**

| Command                   | Value | Description     | Example        |
| ------------------------- | ----- | --------------- | -------------- |
| ECHO_COMMAND              | 20    | Echo test       | `003403010203` |
| KEY_COMMAND               | 4     | Keypad events   | `001001xx`     |
| ANALOG_COMMAND            | 3     | ADC readings    | `000C01xx`     |
| STATISTICS_STATUS_COMMAND | 23    | System stats    | `003701xx`     |
| TASK_STATUS_COMMAND       | 24    | Task monitoring | `003801xx`     |

**Example Commands:**

**Heap Status Request:**

```bash
003801xx  # Request task status
```

**Echo Test:**

```bash
003403010203  # Send echo with data [0x01, 0x02, 0x03]
```

**Usage:**

- Enter hex data without spaces or prefixes
- Real-time response display with checksum validation
- Type 'x' to exit command mode
- Analog commands filtered from output to reduce noise

### 3. Status Mode

Real-time system monitoring with comprehensive statistics.

**Available Statistics:**

- **Error Counters**: Queue errors, buffer overflows, checksum failures
- **Communication Stats**: Bytes sent/received, command counts
- **Task Performance**: CPU usage, execution times, stack usage
- **System Health**: Watchdog status, memory usage

**Statistics Categories:**

**Error Monitoring:**

| Statistic           | Description                       |
| ------------------- | --------------------------------- |
| Queue Send Error    | Inter-task communication failures |
| Queue Receive Error | Message reception failures        |
| Checksum Error      | Data integrity failures           |
| Buffer Overflow     | Communication buffer overruns     |
| Unknown Command     | Unsupported command reception     |

**Task Monitoring:**

| Task           | Core   | Description          |
| -------------- | ------ | -------------------- |
| Idle Task      | Core 1 | System idle time     |
| CDC Task       | Core 0 | USB communication    |
| CDC Write Task | Core 0 | USB transmission     |
| UART Task      | Core 0 | Serial communication |
| Decode Task    | Core 1 | Message parsing      |
| Process Task   | Core 1 | Command processing   |
| ADC Task       | Core 1 | Analog input         |
| Key Task       | Core 1 | Keypad scanning      |
| Encoder Task   | Core 1 | Rotary encoder       |

**Interactive Options:**

1. Request statistics status update
2. Request task status update  
3. Display current status
4. Exit status mode

### 4. Regression Testing

Automated validation of core system functions.

**Test Scenarios:**

- **Echo Command Validation**: Send echo command and verify exact response
- **Response Time Verification**: Ensure responses within acceptable timeframe
- **Data Integrity Checks**: Validate checksum and message format
- **Protocol Compliance**: Verify COBS encoding/decoding

**Expected vs. Actual Comparison:**

```python
# Test case example
Expected: [0x00, 0x34, 0x02, 0x01, 0x02]
Received: [0x00, 0x34, 0x02, 0x01, 0x02]
Result: [OK] Echo command
```

### 5. Result Visualization  

Advanced plotting and analysis of test results.

**Visualization Types:**

**Boxplot Analysis:**

- Latency percentiles with statistical overlay
- Dropped message statistics
- Comparative analysis across test runs
- Log-scale visualization for wide latency ranges

**Histogram Analysis:**  

- Latency distribution visualization
- P95 percentile markers
- Multi-test comparison
- Color-coded test series

**Features:**

- **File Selection**: Paginated interface for test file selection
- **Interactive Navigation**: Next/previous page navigation
- **Statistical Overlay**: Mean, median, percentiles displayed
- **Export Quality**: High-resolution plots suitable for reports

**File Format Support:**

- JSON test result files from `test_results/` directory
- Automatic file discovery and sorting
- Batch processing of multiple test series
- Error handling for corrupted files

## 🔧 API Reference

### Core Classes

#### `ApplicationManager`

Central application controller managing test modes and user interaction.

```python
class ApplicationManager:
    def __init__(self, port: str, baudrate: int, timeout: float)
    def initialize() -> bool
    def run() -> None
    def cleanup() -> None
```

**Key Methods:**

- `run_latency_test()`: Execute latency measurement
- `run_command_mode()`: Start interactive command interface
- `run_status_mode()`: Launch system monitoring
- `run_visualization()`: Display test result analysis

#### `SerialInterface`

Low-level serial communication with COBS protocol support.

```python
class SerialInterface:
    def __init__(self, port: str, baudrate: int, timeout: float)
    def write(data: bytes) -> None
    def set_message_handler(handler: Callable) -> None
```

**Features:**

- Hardware flow control (RTS/CTS)
- Multi-threaded read/write operations
- Buffer overflow protection
- COBS encoding/decoding
- Checksum validation

#### `LatencyTest`  

High-precision latency measurement with statistical analysis.

```python
class LatencyTest:
    def main_test(num_times: int, max_wait: float, min_wait: float, 
                 samples: int, jitter: bool, length: int) -> None
    def handle_message(command: int, decoded_data: bytes) -> None
```

**Statistical Output:**

- Average, minimum, maximum latency
- 95th percentile calculations
- Dropped message tracking
- Bitrate measurements

#### `StatusMode`

System monitoring with comprehensive statistics.

```python  
class StatusMode:
    def execute_test() -> None
    def handle_message(command: int, decoded_data: bytes) -> None
```

**Monitoring Capabilities:**

- Error counter tracking
- Task performance analysis
- Memory usage statistics  
- Real-time system health

### Protocol Implementation

#### Message Format

All messages use COBS (Consistent Overhead Byte Stuffing) encoding:

```bash
[COBS_DATA][0x00]
```

#### Checksum Calculation

XOR checksum over all payload bytes:

```python
def calculate_checksum(data: bytes) -> bytes:
    checksum = 0
    for byte in data:
        checksum ^= byte
    return bytes([checksum])
```

#### Command Structure

Standard command format (before COBS encoding):

| ID (11 bits) | CMD (5 bits) | Length | Payload | Checksum  |
| ------------ | ------------ | ------ | ------- | --------- |
| Byte 0-1     | Byte 1       | Byte 2 | Byte 3+ | Last Byte |

## 📊 Performance Specifications

### Latency Measurement Precision

- **Resolution**: Microsecond precision using `time.perf_counter()`
- **Range**: 1μs to several seconds
- **Accuracy**: System-dependent, typically ±10μs
- **Sample Rate**: Up to 10kHz (limited by serial baudrate)

### Communication Specifications  

- **Protocol**: UART with COBS framing
- **Baudrate**: 115200 bps (configurable)
- **Flow Control**: Hardware RTS/CTS
- **Buffer Size**: 1024 bytes with overflow protection
- **Error Detection**: XOR checksum validation

### Statistical Analysis

- **Percentiles**: P50, P95, P99 calculations
- **Distribution**: Histogram analysis with configurable bins
- **Correlation**: Packet ID tracking for dropped message detection
- **Export**: JSON format with comprehensive metadata

## 🛠️ Development

### Project Structure

```bash
signalbridge-test-suite/
├── src/
│   ├── main.py                    # Application entry point
│   ├── application_manager.py     # Main application controller
│   ├── latency_test.py           # Latency measurement implementation
│   ├── command_mode.py           # Interactive command interface
│   ├── status_mode.py            # System monitoring
│   ├── serial_interface.py       # Serial communication layer
│   ├── visualize_results.py      # Test result visualization
│   ├── regression_test.py        # Automated testing
│   ├── checksum.py              # Checksum utilities
│   ├── logger_config.py         # Logging configuration
│   └── const.py                 # Configuration constants
├── test_results/                 # Test output directory
├── requirements.txt              # Production dependencies
├── requirements.test.txt         # Development/testing dependencies
├── logging_config.ini           # Logging configuration
└── README.md                    # This file
```

### Development Environment Setup

#### Prerequisites

- Python 3.14+
- pip package manager
- Virtual environment support
- Serial port access permissions

#### Setup Instructions

1. **Clone Repository:**

   ```bash
   git clone https://github.com/carlosmazzei/signalbridge-test-suite.git
   cd signalbridge-test-suite
   ```

2. **Create Virtual Environment:**

   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```

3. **Install Dependencies:**

   ```bash
   # Production dependencies
   pip install -r requirements.txt
   
   # Development dependencies (optional)  
   pip install -r requirements.test.txt
   ```

4. **Configure Serial Port:**
   Update `src/const.py` with your device's serial port:

   ```python
   PORT_NAME = "/dev/ttyUSB0"  # Linux
   # PORT_NAME = "COM3"        # Windows  
   # PORT_NAME = "/dev/cu.usbmodem1234561"  # macOS
   ```

### Code Quality

The project uses several tools for maintaining code quality:

- **ruff**: Fast Python linter and formatter
- **pre-commit**: Git hooks for code quality checks
- **pytest**: Testing framework (for future test development)
- **coverage**: Code coverage analysis

#### Running Code Quality Checks

```bash
# Lint code with ruff
ruff check src/

# Format code  
ruff format src/

# Run pre-commit hooks manually
pre-commit run --all-files
```

### Adding New Test Modes

1. **Create Test Module:**

   ```python
   # src/new_test_mode.py
   class NewTestMode:
       def __init__(self, serial_interface: SerialInterface):
           self.serial_interface = serial_interface
           
       def execute_test(self) -> None:
           # Implement test logic
           pass
           
       def handle_message(self, command: int, decoded_data: bytes) -> None:
           # Handle incoming messages
           pass
   ```

2. **Register in ApplicationManager:**

   ```python
   # Add to application_manager.py
   from new_test_mode import NewTestMode
   
   # In __init__:
   self.new_test_mode: NewTestMode | None = None
   
   # In initialize():
   self.new_test_mode = NewTestMode(self.serial_interface)
   
   # Add menu option and handler
   ```

3. **Update Main Menu:**
   Add new option to `display_menu()` and `_handle_user_choice()`

### Extending Serial Commands

1. **Add Command to Enum:**

   ```python
   # In serial_interface.py
   class SerialCommand(Enum):
       NEW_COMMAND = 25  # Add new command ID
   ```

2. **Implement Handler:**

   ```python
   # In appropriate test mode class
   def handle_message(self, command: int, decoded_data: bytes) -> None:
       if command == SerialCommand.NEW_COMMAND.value:
           # Handle new command
           pass
   ```

## 🔧 Configuration Management

### Serial Port Configuration

#### Automatic Port Detection

For systems with multiple serial devices:

```python
import serial.tools.list_ports

def find_signalbridge_port():
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if 'SignalBridge' in port.description:
            return port.device
    return None
```

#### Custom Configuration File

Create `config.json` for environment-specific settings:

```json
{
    "serial": {
        "port": "/dev/ttyUSB0",
        "baudrate": 115200,
        "timeout": 0.1
    },
    "testing": {
        "default_samples": 255,
        "max_wait_time": 0.1,
        "results_folder": "test_results"
    },
    "visualization": {
        "default_plot_type": "boxplot",
        "figure_size": [10, 8],
        "dpi": 100
    }
}
```

### Logging Configuration

The application uses a hierarchical logging configuration (`logging_config.ini`):

```ini
[loggers]
keys=root

[handlers]  
keys=consoleHandler,fileHandler

[formatters]
keys=simpleFormatter,detailedFormatter

[logger_root]
level=INFO
handlers=consoleHandler,fileHandler

[handler_consoleHandler]
class=StreamHandler
level=INFO
formatter=simpleFormatter
args=(sys.stdout,)

[handler_fileHandler]
class=FileHandler
level=DEBUG
formatter=detailedFormatter
args=('test_suite.log', 'a')
```

### Environment Variables

Support for environment-based configuration:

| Variable                | Default                   | Description                |
| ----------------------- | ------------------------- | -------------------------- |
| `SIGNALBRIDGE_PORT`     | `/dev/cu.usbmodem1234561` | Serial port path           |
| `SIGNALBRIDGE_BAUDRATE` | `115200`                  | Communication speed        |
| `LOG_CFG`               | `logging_config.ini`      | Logging configuration file |
| `TEST_RESULTS_DIR`      | `test_results`            | Output directory           |

## 🧪 Testing and Quality Assurance

### Unit Testing Framework

Although not fully implemented, the project includes testing dependencies:

```bash
# Install testing dependencies
pip install -r requirements.test.txt

# Run tests (when implemented)
pytest tests/ -v --cov=src/

# Generate coverage report
coverage html
```

### Regression Testing

The built-in regression test validates:

- **Echo Command Functionality**: Verifies roundtrip communication
- **Message Format Compliance**: Ensures proper protocol implementation  
- **Timing Requirements**: Validates response times within specifications
- **Error Handling**: Tests system behavior under error conditions

### Performance Benchmarking

Built-in performance metrics:

```python
# From status mode statistics
Communication Statistics:
- Bytes sent/received rates
- Command processing frequency
- Error rates and types
- Buffer utilization

Task Performance:
- CPU usage per task
- Memory utilization (stack high water mark)
- Execution time distribution
- Core allocation efficiency
```

## 📈 Monitoring and Diagnostics

### System Health Monitoring

Real-time monitoring capabilities:

#### Error Rate Tracking

- **Checksum Errors**: Data corruption detection
- **Buffer Overflows**: Communication bottleneck identification
- **Queue Errors**: Inter-task communication failures
- **Protocol Violations**: Invalid message format detection

#### Performance Metrics

- **Latency Statistics**: P50, P95, P99 measurements
- **Throughput Analysis**: Messages per second, bytes per second
- **Jitter Measurement**: Timing variation analysis
- **Dropped Packet Rate**: Communication reliability assessment

#### Resource Usage

- **Memory Utilization**: Stack usage monitoring
- **CPU Load Distribution**: Per-core and per-task analysis  
- **Buffer Occupancy**: Communication buffer usage patterns
- **Task Scheduling**: Execution time distribution

### Diagnostic Tools

#### Log Analysis

Structured logging with multiple levels:

```python
# Debug: Detailed execution flow
logger.debug("Processing message ID %d", message_id)

# Info: Normal operation status  
logger.info("Test completed: %d samples, %.2f ms avg", count, avg)

# Warning: Recoverable issues
logger.warning("High buffer utilization: %d%%", utilization)

# Error: System errors
logger.error("Serial communication failed: %s", error)
```

#### Real-time Statistics Dashboard

Status mode provides live system monitoring:

- Command counters with real-time updates
- Task performance visualization
- Error rate trending
- System health indicators

## 🚨 Troubleshooting

### Common Issues and Solutions

#### Serial Communication Problems

**Port Not Found / Permission Denied**:

```bash
# Linux: Add user to dialout group
sudo usermod -a -G dialout $USER
# Logout and login again

# macOS: Check port permissions
ls -l /dev/cu.usbmodem*

# Windows: Check Device Manager for COM port
```

**Connection Timeout**:

```python
# Increase timeout in const.py
TIMEOUT = 1.0  # Increase from 0.1 to 1.0 seconds

# Verify device is responding
# Use command mode to send test commands
```

**Data Corruption / Checksum Errors**:

```bash
# Check cable connections
# Verify baudrate matches device settings
# Test with lower baudrate (57600)
# Check for electromagnetic interference
```

#### Performance Issues

**High Latency Measurements**:

- Check system load (`top`, `htop` on Linux/macOS)
- Close unnecessary applications
- Use real-time scheduling if available
- Verify USB port is not shared with high-bandwidth devices

**Dropped Messages**:

```python
# Reduce test frequency
max_wait = 0.5  # Increase from 0.1 seconds

# Reduce sample count
samples = 100   # Decrease from 255

# Enable flow control
# Hardware RTS/CTS should be enabled by default
```

**Visualization Errors**:

```bash
# Install display backend for matplotlib
# Linux:
sudo apt-get install python3-tk

# macOS: 
# Usually works out of the box

# Windows:
# Install matplotlib with proper backend
pip install matplotlib[tk]
```

#### Application Crashes

**Memory Issues**:

```python
# Monitor memory usage
import psutil
process = psutil.Process()
print(f"Memory: {process.memory_info().rss / 1024 / 1024:.1f} MB")

# Reduce buffer sizes if needed
MAX_BUFFER_SIZE = 512  # Reduce from 1024
```

**Threading Deadlocks**:

- Check serial port is properly closed on exit
- Verify no multiple instances accessing same port
- Use `Ctrl+C` to force application exit
- Restart terminal if port remains locked

### Diagnostic Commands

#### System Information

```python
# Check Python version
python --version

# List installed packages  
pip list

# Check serial ports
python -c "import serial.tools.list_ports; print(list(serial.tools.list_ports.comports()))"
```

#### Port Testing

```bash
# Linux: Test port access
sudo chmod 666 /dev/ttyUSB0
echo "test" > /dev/ttyUSB0

# macOS: Test port availability  
ls -la /dev/cu.*

# Windows: Use Device Manager or PowerShell
Get-WmiObject -Class Win32_SerialPort
```

#### Log Analysis Diagnostic

```bash
# View recent log entries
tail -f test_suite.log

# Filter for errors
grep "ERROR" test_suite.log

# Monitor real-time logs with timestamps
tail -f test_suite.log | grep -E "(ERROR|WARNING)"
```

### Performance Optimization

#### System-level Optimization

```bash
# Linux: Disable CPU frequency scaling (temporarily)
sudo cpupower frequency-set --governor performance

# Increase process priority (Linux/macOS)  
sudo nice -n -10 python src/main.py

# Windows: Set high priority
# Use Task Manager > Details > Set Priority > High
```

#### Application-level Optimization

```python
# Reduce logging verbosity for production testing
# Edit logging_config.ini:
level=WARNING  # Change from DEBUG/INFO

# Optimize buffer sizes for your use case
BUFFER_HIGH_WATER = 512  # Reduce if memory constrained
BUFFER_LOW_WATER = 128   # Maintain ratio

# Use appropriate test parameters
samples = 100       # Reduce for faster testing
max_wait = 0.01     # Increase for high-throughput testing  
```

### Getting Help

1. **Check GitHub Issues**: Search for similar problems in the project repository
2. **Enable Debug Logging**: Set logging level to DEBUG for detailed diagnostics
3. **Collect System Information**: Include Python version, OS, and error logs when reporting issues
4. **Test Hardware Connection**: Verify device responds to basic commands before running complex tests
5. **Review Configuration**: Ensure serial port settings match device configuration

For additional support, please refer to the project repository or create a new issue with:

- Complete error messages and stack traces
- System configuration (OS, Python version)
- Steps to reproduce the problem  
- Test configuration being used

## 📝 Contributing

We welcome contributions to improve the SignalBridge Test Suite! Here's how to get involved:

### Development Workflow

1. **Fork the Repository**

   ```bash
   # Fork via GitHub UI, then:
   git clone https://github.com/yourusername/signalbridge-test-suite.git
   cd signalbridge-test-suite
   ```

2. **Create Development Environment**

   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   pip install -r requirements.test.txt
   ```

3. **Install Pre-commit Hooks**

   ```bash
   pre-commit install
   ```

4. **Create Feature Branch**

   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/issue-description
   ```

5. **Make Changes and Test**

   ```bash
   # Run linting
   ruff check src/
   
   # Format code
   ruff format src/
   
   # Test changes
   python src/main.py
   ```

6. **Commit and Push**

   ```bash
   git add .
   git commit -m "Add feature: description"
   git push origin feature/your-feature-name
   ```

7. **Create Pull Request**
   - Use the GitHub UI to create a pull request
   - Provide clear description of changes
   - Include test results if applicable

### Contribution Guidelines

#### Code Style

- Follow PEP 8 Python style guide
- Use ruff for linting and formatting
- Add type hints for function parameters and return values
- Include docstrings for public functions and classes

#### Testing

- Test new features with actual hardware when possible
- Include error handling for edge cases
- Verify backward compatibility
- Document any new configuration parameters

#### Documentation

- Update README.md for new features
- Add inline comments for complex logic
- Update configuration examples
- Include usage examples for new functionality

### Types of Contributions

#### Bug Fixes

- Serial communication issues
- Visualization problems
- Performance improvements
- Error handling enhancements

#### New Features

- Additional test modes
- New visualization types
- Protocol extensions
- Configuration enhancements

#### New Documentation

- Installation instructions
- Usage examples
- Troubleshooting guides
- API documentation

#### Performance Improvements

- Latency measurement precision
- Memory usage optimization
- Threading improvements
- Statistical analysis enhancements

### Reporting Issues

When reporting bugs or requesting features, please include:

1. **Environment Information**
   - Python version
   - Operating system
   - Hardware configuration
   - Device firmware version

2. **Problem Description**
   - Clear steps to reproduce
   - Expected vs actual behavior
   - Complete error messages
   - Relevant log output

3. **Configuration Details**
   - Serial port settings
   - Test parameters used
   - Any custom modifications

## 📄 License

This project is licensed under the GPL v3 License - see the [LICENSE](LICENSE) file for details.

### License Summary

The GNU General Public License v3.0 is a copyleft license that requires:

**Permissions:**

- Commercial use
- Distribution  
- Modification
- Private use

**Conditions:**

- Disclose source code
- Include license and copyright notice
- Same license for derivative works
- Document changes made to the code

**Limitations:**

- No liability protection
- No warranty provided

For the complete license text, visit: [GPL-3](https://www.gnu.org/licenses/gpl-3.0)

---

## 📞 Support and Community

### Getting Support

- **GitHub Issues**: Report bugs and request features
- **Discussions**: Ask questions and share experiences
- **Documentation**: Check this README and inline code documentation
- **Examples**: Review the provided usage examples

### Project Roadmap

Future improvements planned:

- Web-based dashboard for real-time monitoring
- Automated report generation  
- Additional protocol support (SPI, I2C)
- Database storage for test results
- Continuous integration improvements
- Performance profiling tools

### Acknowledgments

Special thanks to contributors and the embedded systems testing community for their valuable feedback and contributions to this project.
