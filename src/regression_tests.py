import serial
from cobs import cobs


def handle_message(command, decoded_data, byte_string):
    if command == 20:
        try:
            if decoded_data == bytes([0x00, 0x34, 0x02, 0x01, 0x02]):
                print("[OK] Echo command")
            else:
                print("[FAIL] Echo command")
            
            print(f"Expected: {bytes([0x00, 0x34, 0x02, 0x01, 0x02])}")
            print(f"Received: {byte_string}, command: {command}, decoded: {decoded_data}")
            print("Test ended")
        except IndexError:
            print("Invalid message (Index Error)")
            return


def test_echo_command(ser):
    payload = bytes([0x00, 0x34, 0x02, 0x01, 0x02])
    message = cobs.encode(payload)
    message += b"\x00"
    ser.write(message)


def execute_test(ser):

    # Scenario 1: send echo command and expect to get the same message back
    test_echo_command(ser)

    
