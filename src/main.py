import serial
import time
import sys
import datetime
import threading
import regression_tests

from latency_test import LatencyTest
from logger import Logger

import json
import curses
from cobs import cobs
from globals import current_mode
import random

stop_event = threading.Event()
MAX_LOG_MESSAGES = 20
logger = None


# Open a serial connection
def open_serial(port, baudrate, timeout):
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

    except Exception as e:
        # Print the exception
        logger.display_log("Error opening and configuring serial port")
        logger.display_log(f"Exception: {e}")
        return None


# Read thread
def read_data(ser):
    byte_string = b""
    logger.display_log("Starting read thread...")

    try:
        while not stop_event.is_set():
            byte = ser.read(1)
            if len(byte) != 0:
                if byte == b"\x00":
                    # Decode the byte string using COBS
                    decoded_data = cobs.decode(byte_string)
                    command = decoded_data[1] & 0x1F
                    handle_message(command, decoded_data, byte_string)

                    # Reset the byte string
                    byte_string = b""

                else:
                    byte_string += byte

    except Exception as e:
        # Print the exception
        logger.display_log(f"Exception: {str(e)}")
        logger.display_log("Error reading serial port")
        stop_event.set()
        ser.close()
        exit(1)


# Handle the received message
def handle_message(command, decoded_data, byte_string):

    if current_mode == "latency":
        latency_test.handle_message(command, decoded_data)

    elif current_mode == "command":
        # Filter non-ADC commands
        if command != 3:
            logger.display_log(f"Received raw: {byte_string}, decoded: {decoded_data}")
            print_decoded_message(decoded_data)

    elif current_mode == "regression":
        regression_tests.handle_message(logger, command, decoded_data, byte_string)

    # else:
    #    display_log()
    #    display_log("No mode selected...")


# Function to send commands
def send_command(ser):

    while True:
        hex_data = input("Enter hex data (x to exit): ")
        if hex_data == "x":
            logger.display_log("Exiting send command menu...")
            break

        if len(hex_data) % 2 != 0:
            logger.display_log("Invalid hex data")
            continue

        payload = bytes.fromhex(hex_data)
        message = cobs.encode(payload)
        message += b"\x00"
        ser.write(message)
        logger.display_log(f"Published (encoded) `{message}`")


def print_decoded_message(message):
    # Print each byte of the message
    logout = ""
    for i in range(len(message)):
        logout += f"{i}: {message[i]} "

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


def exit_program(ser, read_thread):
    stop_event.set()
    read_thread.join()
    ser.close()


def display_menu(menu_window):
    menu_window.clear()
    menu_window.addstr(0, 0, "1. Run latency test\n")
    menu_window.addstr(1, 0, "2. Send command\n")
    menu_window.addstr(2, 0, "3. Regression test\n")
    menu_window.addstr(3, 0, "4. Exit\n")
    menu_window.addstr(4, 0, "Enter a choice:\n")
    menu_window.refresh()


def main(stdscr):
    curses.curs_set(0)
    stdscr.clear()

    log_height = MAX_LOG_MESSAGES + 5
    log_window = curses.newwin(log_height, curses.COLS, 0, 0)
    menu_window = curses.newwin(curses.LINES - log_height, curses.COLS, log_height, 0)

    # Redirect sys.stdout to the new window
    sys.stdout = log_window

    stdscr.refresh()

    global logger
    logger = Logger(log_window, MAX_LOG_MESSAGES)

    # Open and configure serial port
    # port = "/dev/cu.SLAB_USBtoUART"
    port = "/dev/cu.usbmodem1234561"
    logger.display_log(f"Opening serial port: {port}...")
    ser = open_serial(port, 115200, 0.1)
    if ser == None:
        logger.display_log("Cannot open serial port...")
    else:
        # Start the read task in a separate thread
        read_thread = threading.Thread(target=read_data, args=(ser,))
        read_thread.start()

    latency_test = LatencyTest(ser, logger)

    try:
        while True:
            # display_log(log_window, "This is a log message.")
            display_menu(menu_window)

            key = stdscr.getch()
            if key == ord("1"):
                logger.display_log("Running test...")
                current_mode = "latency"     
                latency_test.execute_test()

            elif key == ord("2"):
                current_mode = "command"
                send_command(ser)

            elif key == ord("3"):
                current_mode = "regression"
                regression_tests.execute_test(ser)

            elif key == ord("4"):
                logger.display_log("Exiting...")
                # Wait for the read thread to finish
                logger.display_log("Stopping read thread and closing serial port...")
                exit_program(ser, read_thread)
                break
            else:
                logger.display_log("Invalid choice\n")

    except Exception as e:
        # curses.endwin()
        logger.display_log(f"Exception in main loop: {e}")


# Main program
if __name__ == "__main__":
    curses.wrapper(main)
