import os
import threading

import regression_tests
import serial
from checksum import calculate_checksum
from cobs import cobs
from globals import current_mode
from latency_test import LatencyTest
from logger import Logger

MAX_LOG_MESSAGES = 20


def open_serial(port: str, baudrate: int, timeout: float) -> serial.Serial | None:
    """Open serial interface in the port with the baudrate and timeout provided."""
    try:
        ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            timeout=timeout,
            parity=serial.PARITY_NONE,
            bytesize=serial.EIGHTBITS,
            stopbits=serial.STOPBITS_ONE,
            xonxoff=False,
            rtscts=False,
        )
        logger.display_log(f"Serial port opened: {ser}")
        return ser

    except serial.SerialException as e:
        # Print the exception
        logger.display_log("Error opening serial port")
        logger.display_log(f"Exception: {e}")
        return None

    except Exception as e:
        # Print the exception
        logger.display_log(f"Exception: {e}")
        return None


def read_data(ser: serial.Serial) -> None:
    """Read data from the serial port and decode it using COBS and handle the received message."""
    byte_string: bytes = b""
    logger.display_log("Starting read thread...")

    try:
        while not stop_event.is_set():
            byte: bytes = ser.read(1)
            if len(byte) != 0:
                if byte == b"\x00":
                    # Decode the byte string using COBS
                    decoded_data: bytes = cobs.decode(byte_string)
                    command: int = decoded_data[1] & 0x1F
                    handle_message(command, decoded_data, byte_string)

                    # Reset the byte string
                    byte_string = b""

                else:
                    byte_string += byte

    except Exception as e:
        # Print the exception
        logger.display_log(f"Exception: {e}")
        logger.display_log("Error reading serial port")
        stop_event.set()
        ser.close()
        exit(1)


def handle_message(command: int, decoded_data: bytes, byte_string: bytes) -> None:
    """Handle the message received."""
    if current_mode == "latency":
        if latency_test is LatencyTest:
            latency_test.handle_message(command, decoded_data)

    elif current_mode == "command":
        # Filter non-ADC commands
        if command != 3:
            logger.display_log(f"Received raw: {byte_string}, decoded: {decoded_data}")
            print_decoded_message(decoded_data)

    elif current_mode == "regression":
        regression_tests.handle_message(logger, command, decoded_data, byte_string)

    # else:
    #    display_log("No mode selected...")


def send_command(ser: serial.Serial) -> None:
    """Send command using the serial interface provided."""
    while True:
        hex_data = input("Enter hex data (x to exit): ")
        if hex_data == "x":
            logger.display_log("Exiting send command menu...")
            break

        if len(hex_data) % 2 != 0:
            logger.display_log("Invalid hex data")
            continue

        payload = bytes.fromhex(hex_data)
        checksum = calculate_checksum(payload)
        payload_with_checksum = payload + bytes([checksum])
        message = cobs.encode(payload_with_checksum) + b"\x00"

        ser.write(message)
        logger.display_log(f"Published (encoded) `{message}`")


def print_decoded_message(message: bytes) -> None:
    """Print each byte of the message."""
    logout = ""
    for i, msg in enumerate(message):
        logout += f"{i}: {msg}"

    logger.display_log(f"Decoded message: {logout}")
    rxid = message[0]
    rxid <<= 3
    rxid |= (message[1] & 0xE0) >> 5
    command = message[1] & 0x1F
    length = message[2]
    logger.display_log(f"Id: {rxid}, Command: {command}")

    if command == 4:
        state = message[3] & 0x01
        col = (message[3] >> 4) & 0x0F
        row = (message[3] >> 1) & 0x0F
        logger.display_log(
            f"Column: {col}, Row: {row}, State: {state}, Length: {length}"
        )
    elif command == 3:
        channel = message[3]
        value = message[4] << 8
        value |= message[5]
        logger.display_log(f"Channel: {channel}, Value: {value}")


def exit_program(ser: serial.Serial | None, read_thread: threading.Thread) -> None:
    """Join threads and exit program."""
    stop_event.set()
    read_thread.join()
    if ser is not None:
        ser.close()


def display_menu() -> None:
    """Display the menu."""
    print()
    print("1. Run latency test")
    print("2. Send command")
    print("3. Regression test")
    print("4. Exit")


def main() -> None:
    """Run main program."""
    global current_mode

    # Open and configure serial port
    # port = "/dev/cu.SLAB_USBtoUART"
    port = "/dev/cu.usbmodem1234561"
    logger.display_log(f"Opening serial port: {port}...")
    ser = open_serial(port, 115200, 0.1)
    if ser is None:
        logger.display_log("Cannot open serial port. Exiting...")
        logger.show_log()
        exit(1)
    else:
        # Start the read task in a separate thread
        read_thread = threading.Thread(target=read_data, args=(ser,))
        read_thread.start()

    global latency_test
    latency_test = LatencyTest(ser, logger)

    try:
        while True:
            os.system("clear")  # noqa: S607, S605
            logger.show_log()
            display_menu()

            key = input("Enter a choice: ")
            if key == "1":
                os.system("clear")  # noqa: S607, S605
                logger.display_log("Running test...")
                current_mode = "latency"
                latency_test.execute_test()

            elif key == "2":
                current_mode = "command"
                if ser is not None:
                    send_command(ser)

            elif key == "3":
                current_mode = "regression"
                regression_tests.execute_test(ser)

            elif key == "4":
                logger.display_log("Exiting...")
                # Wait for the read thread to finish
                logger.display_log("Stopping read thread and closing serial port...")
                exit_program(ser, read_thread)
                break
            else:
                logger.display_log("Invalid choice\n")

    except Exception as e:
        logger.display_log(f"Exception in main loop: {e}")


# Main program

logger = Logger(MAX_LOG_MESSAGES)
stop_event = threading.Event()

if __name__ == "__main__":
    latency_test = None

    main()
