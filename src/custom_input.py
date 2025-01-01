"""Custom input function to handle input in a thread-safe manner."""

import sys
import threading

input_lock = threading.Lock()


def custom_input(prompt: str) -> str:
    """Thread-safe input function."""
    with input_lock:
        # Clear the current line
        sys.stdout.write("\r" + " " * (len(prompt) + 20) + "\r")
        sys.stdout.flush()
        # Print the prompt and get input
        user_input = input(prompt)
        # Print a newline to move cursor to next line
        print()
        return user_input
