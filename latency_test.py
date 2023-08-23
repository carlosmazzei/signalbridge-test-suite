import serial
import time
import datetime
import threading
import json
from cobs import cobs
import random
from alive_progress import alive_bar

latency_results = []
latency_message = []
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
        print(f"Exception: {str(e)}")
        print("Error opening and configuring serial port")
        return None


# Read thread
def read_data(ser):
    byte_string = b""
    print("Starting read thread...")
    while not stop_event.is_set():
        byte = ser.read(1)
        if len(byte) != 0:
            if byte == b"\x00":
                # Decode the byte string using COBS
                decoded_data = cobs.decode(byte_string)
                if latency_test_mode == True:
                    try:
                        counter = decoded_data[5]
                        latency = time.time() - latency_message[counter]
                        latency_results.append(latency)
                        print(f"Message {counter} latency: {latency * 1e3} ms")
                    except IndexError:
                        print("Invalid message (Index Error)")
                        return
                else:
                    print()
                    print(f"Received raw: {byte_string}, decoded: {decoded_data}")
                    print_decoded_message(decoded_data)
                # Reset the byte string
                byte_string = b""

            else:
                byte_string += byte


# Send 10 byte message to MQTT broker and wait for response. Log the time taken.
def publish(ser, iteration_counter):
    header = bytes([0x00, 0x34, 0x03, 0x01, 0x02])
    counter = iteration_counter.to_bytes(1, byteorder="big")
    payload = header + counter

    start_time = time.time()
    latency_message[int.from_bytes(counter, "big")] = start_time

    message = cobs.encode(payload)
    message += b"\x00"
    ser.write(message)
    print(f"Published (encoded) `{message}`, counter {counter}")


# Main test
def main_test(ser, num_times=10, max_wait=0.5, min_wait=0, samples=255, jitter=False):
    # Get the current date and time
    current_datetime = datetime.datetime.now()
    # Format the date and time as a string
    formatted_datetime = current_datetime.strftime("%Y%m%d_%H%M%S")
    # Output filename
    filename = "output.json"
    output_filename = f"./tests/{formatted_datetime}_{filename}"

    # Open the file in append mode
    output_file = open(output_filename, "w")

    # Prepare the data to store in JSON format
    output_data = []
    latency_results_copy = [[] for i in range(num_times)]
    bar_title = f"Test / Jitter: {jitter}"

    # Loop for each byte
    with alive_bar(samples * num_times, title=bar_title) as bar:
        for j in range(num_times):
            latency_results.clear()

            # Calculate the waiting time
            waiting_time = min_wait + (max_wait - min_wait) * (j / (num_times - 1))
            print(f"Test {j}, waiting time: {waiting_time} s")
            random_max = (max_wait - min_wait) * 0.2

            for i in range(0, samples):
                publish(ser, i)
                if jitter == True:
                    # Sleep for a random amount of time
                    time.sleep(waiting_time + random.uniform(0, random_max))
                else:
                    time.sleep(waiting_time)
                bar()

            # Calculate the average latency
            latency_avg = sum(latency_results) / len(latency_results)
            print(f"Average latency: {latency_avg * 1e3} ms")
            # Calculate minimum latency
            latency_min = min(latency_results)
            print(f"Minimum latency: {latency_min * 1e3} ms")
            # Calculate maximum latency
            latency_max = max(latency_results)
            print(f"Maximum latency: {latency_max * 1e3} ms")
            latency_results_copy[j] = latency_results.copy()

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


def execute_test(ser):
    print("Waiting to start test for 5 seconds...")
    time.sleep(5)

    global latency_test_mode
    latency_test_mode = True

    # Run the test
    main_test(ser, num_times=10, max_wait=0.7, min_wait=0, samples=255)

    # Run again with jitter
    main_test(ser, num_times=10, max_wait=0.7, min_wait=0, samples=255, jitter=True)

    print("Test ended")


def send_command(ser):
    global latency_test_mode
    latency_test_mode = False

    while True:
        print()
        hex_data = input("Enter hex data (x to exit): ")
        if hex_data == "x":
            print("Exiting...")
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
    # for i in range(len(message)):
    #     print(f"{i}: {message[i]}")

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
        channel = (message[3] & 0xF0) >> 4
        value = (message[3] & 0x0F) + message[4]
        print(f"Channel: {channel}, Value: {value}")


# Main program
if __name__ == "__main__":
    # Open and configure serial port
    # port = "/dev/cu.SLAB_USBtoUART"
    port = "/dev/cu.usbmodem1234561"
    print(f"Opening serial port: {port}...")
    ser = open_serial(port, 115200, 0.1)
    if ser == None:
        print("Exiting...")
        exit(1)

    # Start the read task in a separate thread
    read_thread = threading.Thread(target=read_data, args=(ser,))
    read_thread.start()
    latency_message = [0] * 255
    global latency_test_mode
    latency_test_mode = False
    print()

    while True:
        print("1. Run test")
        print("2. Send commands")
        print("3. Exit")
        print()
        choice = input("Enter your choice: ")
        if choice == "1":
            print("Running test...")
            # Run the test
            execute_test(ser)
            print()
        elif choice == "2":
            send_command(ser)
            print()
            # Send commands
        elif choice == "3":
            print("Exiting...")
            # Wait for the read thread to finish
            print("Stopping read thread and closing serial port...")
            stop_event.set()
            read_thread.join()
            ser.close()
            exit(1)
        else:
            print("Invalid choice")
            print()
