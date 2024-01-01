# UART Test Routines

This project includes:

- UART Latency test for ESP32 and CP2102
- Simple interface to send commands

Run program to calculate latency of a set of echo messages sent to the controller

To install dependencies and create a virtual environment in Python, you can use the following steps:

## Project Setup

1. **Install Python:**

Make sure Python is installed on your system. You can download the latest version from the official Python website: [https://www.python.org/downloads/](https://www.python.org/downloads/)

2. **Install `virtualenv` (if not installed):**

Open a terminal or command prompt and run the following command to install `virtualenv` globally:

```sh
pip install virtualenv
```

3. **Create a Virtual Environment:**

Choose or create a directory where you want to store your project and navigate to it using the terminal or command prompt. Then, run the following command to create a virtual environment:

```sh
virtualenv venv
```

Replace `venv` with the desired name for your virtual environment.

4. **Activate the Virtual Environment:**

Activate the virtual environment using the appropriate command based on your operating system:

- On Windows:

```sh
venv\Scripts\activate
```

- On macOS and Linux:

```sh
source venv/bin/activate
```

Once activated, you should see the virtual environment's name in your command prompt or terminal, indicating that you are now working within the virtual environment.

5. **Install Dependencies:**

With the virtual environment activated, you can use `pip` to install the required dependencies for your project. For example:

```sh
pip install package_name
```

Replace `package_name` with the actual name of the package you want to install. You can also install dependencies from a `requirements.txt` file using:

```sh
pip install -r requirements.txt
```

6. **Deactivate the Virtual Environment:**

When you're done working in the virtual environment, you can deactivate it using the following command:

```sh
deactivate
```

By following these steps, you can create and activate a virtual environment, install dependencies, and manage your project's dependencies in an isolated environment. This helps in avoiding conflicts between different projects and ensures that your project uses the specified versions of libraries. 

## Test Application

Use the following command to run the application:

```sh
python3 latency_test.py
```

And you should see the menu:

```sh
1. Run test
2. Send commands
3. Exit
```

### Run test

This option will start the latency test

The test message sent is

| Byte 0 | Byte 1 | Byte 2 | Byte 3 | Byte 4 | Byte 5 | Byte 6 | Byte 7 | Byte 8 | Byte 9 |
|--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|
| x00    | x34    | x03    | x01    | x02    | x03    | ?      | ?      | ?      | ?      |
|00000000|00110100|00000011|00000001|00000010|00000011| ?      | ?      | ?      | ?      |

Corresponding to (packet total of 10 bytes)

- Id = 1 (First 11 bits)
- Cmd = 20 (PC_ECHO_CMD) (5 bits)
- Length = 3
- Data Byte 1 = 1
- Data byte 2 = 2
- Data byte 3 = 3 (used as identifier)
- Other bytes not initialized

The test will create and output file in the following format: `./tests/{formatted_datetime}_{filename}`

Where filename is `output.json`

### Test Parameters

You can change the test parameters accordingly

```python
def main_test(ser, num_times=10, max_wait=0.5, min_wait=0, samples=255, jitter=False)
```

- ser: Serial interface client created
- num_times: Number of times to run the test cases
- max_wait: Maximum wait time in milliseconds between samples
- min_wait: Minimum wait time in milliseconds between samples
- samples: Number of samples (max of 255)
- jitter: Boolean to identify to add jitter to the wait time (20% of max wait time and an uniform distribution)

### Send commands

This menu option is used to send desired commands to the interface in order to test other functions

For example sending the heap status command to get 

| Byte 0 | Byte 1 | Byte 2 | Byte 3 | Byte 4 | Byte 5 | Byte 6 | Byte 7 | Byte 8 | Byte 9 |
|--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|
| x00    | x38    | x01    | x01    | ?      | ?      | ?      | ?      | ?      | ?      |
|00000000|00111000|00000001|00000001| ?      | ?      | ?      | ?      | ?      | ?      |
