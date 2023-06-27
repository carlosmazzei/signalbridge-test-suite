import serial
import time
import threading

latency_results = []
latency_message = []

# Open a serial connection
def open_serial(port, baudrate, timeout):
    try:
        ser = serial.Serial(port, baudrate, timeout=timeout)
        ser.set_parity(serial.PARITY_NONE)
        ser.set_bytesize(serial.EIGHTBITS)
        ser.set_stopbits(serial.STOPBITS_ONE)
        ser.set_xonxoff(False)
        ser.set_rtscts(False)
        return ser
    except:
        print("Error opening and configuring serial port")
        return None

# Read thread
def read_data(ser):
    byte_string = b''
    while True:
        byte = ser.read()
        if byte == b'\x00':
            # Decode the byte string using COBS
            decoded_data = cobs.decode(byte_string)
            byte_string = b''
            try:
                counter = decoded_data[5]
                latency = time.time() - latency_message[counter]
                latency_results.append(latency)
                print(f"Message {counter} latency: {latency * 1e3} ms")
            except IndexError:
                print("Invalid message")
                return
        else:
            byte_string += byte

# Send 10 byte message to MQTT broker and wait for response. Log the time taken.
def publish(ser, iteration_counter):
    def on_publish(client, userdata, mid):
        print(f"Message ID: {mid}")

    header = bytes([0x00, 0x34, 0x03, 0x01, 0x02])
    counter = iteration_counter.to_bytes(1, byteorder='big')
    payload = header + counter

    start_time = time.time()
    latency_message[int.from_bytes(counter, "big")] = start_time

    ser.write(cobs.encode(payload))
    print(f"Published `{payload}` to topic `{publish_topic}`, counter {counter}")

# Main program
if __name__ == "__main__":

    # Open and configure serial port
    ser = open_serial("/dev/ttyUSB0", 115200, 0.1)
    if ser == None:
        print("Exiting...")
        exit(1)

    # Start the read task in a separate thread
    read_thread = threading.Thread(target=read_data, args=(ser,))
    read_thread.start()

    # Send byte messages
    for i in range(0, 255):
        publish(ser, i)
        time.sleep(1)
    
    # Sleep for 20 seconds
    print("Waiting for 20 seconds to collect results...")
    time.sleep(20)
    
    # Wait for the read thread to finish
    print("Stopping read thread and closing serial port...")
    read_thread.join()
    ser.close()
    print("Test ended")