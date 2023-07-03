import serial
import time
import threading
from cobs import cobs

latency_results = []
latency_message = []

# Open a serial connection
def open_serial(port, baudrate, timeout):
    try:
        ser = serial.Serial(port = port, 
                            baudrate = baudrate, 
                            timeout = timeout,
                            parity = serial.PARITY_NONE,
                            bytesize = serial.EIGHTBITS,
                            stopbits = serial.STOPBITS_ONE,
                            xonxoff = False,
                            rtscts = False)
        print(f"Serial port opened: {ser}")
        return ser
        
    except Exception as e:
        # Print the exception
        print(f"Exception: {str(e)}")
        print("Error opening and configuring serial port")
        return None

# Read thread
def read_data(ser):
    byte_string = b''
    print("Starting read thread...")
    while True:
        byte = ser.read(1)
        if len(byte) != 0:
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
                print(f"Received byte string: {byte_string}")

# Send 10 byte message to MQTT broker and wait for response. Log the time taken.
def publish(ser, iteration_counter):  
    header = bytes([0x00, 0x34, 0x03, 0x01, 0x02])
    counter = iteration_counter.to_bytes(1, byteorder='big')
    payload = header + counter

    start_time = time.time()
    latency_message[int.from_bytes(counter, "big")] = start_time

    message = cobs.encode(payload)
    message += b'\x00'
    ser.write(message)
    print(f"Published (encoded) `{message}`, counter {counter}")

# Main program
if __name__ == "__main__":

    # Open and configure serial port
    port = "/dev/cu.SLAB_USBtoUART"
    print(f"Opening serial port: {port}...")
    ser = open_serial(port, 115200, 0.1)
    if ser == None:
        print("Exiting...")
        exit(1)

    # Start the read task in a separate thread
    read_thread = threading.Thread(target=read_data, args=(ser,))
    read_thread.start()

    latency_message = [0] * 255

    print("Waiting to start test for 10 seconds...")
    time.sleep(10)

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