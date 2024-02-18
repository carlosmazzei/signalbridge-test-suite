import serial
import time
import datetime
import threading
import latency_test
import regression_tests
import json
from cobs import cobs
from globals import current_mode
import random

stop_event = threading.Event()


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
        print(f"Serial port opened: {ser}")
        return ser

    except Exception as e:
        # Print the exception
        print()
        print(f"Exception: {str(e)}")
        print("Error opening and configuring serial port")
        print()
        return None


# Read thread
def read_data(ser):
    byte_string = b""
    print("Starting read thread...")

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
        print(f"Exception: {str(e)}")
        print("Error reading serial port")
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
            print()
            print(f"Received raw: {byte_string}, decoded: {decoded_data}")
            print_decoded_message(decoded_data)
    
    elif current_mode == "regression":
        regression_tests.handle_message(command, decoded_data, byte_string)

    #else:
    #    print()
    #    print("No mode selected...")


# Function to send commands
def send_command(ser):
    global latency_test_mode
    latency_test_mode = False

    while True:
        print()
        hex_data = input("Enter hex data (x to exit): ")
        if hex_data == "x":
            print("Exiting send command menu...")
            break

        if len(hex_data) % 2 != 0:
            print("Invalid hex data")
            continue

        payload = bytes.fromhex(hex_data)
        message = cobs.encode(payload)
        message += b"\x00"
        ser.write(message)
        print(f"Published (encoded) `{message}`")


def print_decoded_message(message):
    # Print each byte of the message
    logout = ""
    for i in range(len(message)):
        logout += f"{i}: {message[i]} "

    print(f"Decoded message: {logout}")
    rxid = message[0]
    rxid <<= 3
    rxid |= (message[1] & 0xE0) >> 5
    command = message[1] & 0x1F
    length = message[2]
    print(f"Id: {rxid}, Command: {command}")

    if command == 4:
        state = message[3] & 0x01
        col = (message[3] >> 4) & 0x0F
        row = (message[3] >> 1) & 0x0F
        print(f"Column: {col}, Row: {row}, State: {state}, Length: {length}")
    elif command == 3:
        channel = message[3]
        value = message[4] << 8
        value |= message[5]
        print(f"Channel: {channel}, Value: {value}")


def exit_program(ser, read_thread):
    stop_event.set()
    read_thread.join()
    ser.close()
    exit(1)


# Main program
if __name__ == "__main__":
    # Open and configure serial port
    # port = "/dev/cu.SLAB_USBtoUART"
    port = "/dev/cu.usbmodem1234561"
    print(f"Opening serial port: {port}...")
    ser = open_serial(port, 115200, 0.1)
    if ser == None:
        print("Exiting. Cannot open serial port...")
        exit(1)

    # Start the read task in a separate thread
    read_thread = threading.Thread(target=read_data, args=(ser,))
    read_thread.start()

    print()

    # Start the main program loop
    while True:
        print("1. Run latency test")
        print("2. Send commands")
        print("3. Regression test")
        print("4. Exit")
        print()
        choice = input("Enter your choice: ")
        if choice == "1":
            print("Running test...")
            # Run the test
            current_mode = "latency"
            latency_test.execute_test(ser)
            print()
        elif choice == "2":
            current_mode = "command"
            send_command(ser)
            print()
        elif choice == "3":
            current_mode = "regression"
            regression_tests.execute_test(ser)
            print()
        elif choice == "4":
            print("Exiting...")
            # Wait for the read thread to finish
            print("Stopping read thread and closing serial port...")
            exit_program(ser, read_thread)
        else:
            print("Invalid choice")
            print()
