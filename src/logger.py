from datetime import datetime
from typing import Any


class Logger:
    """Log messages to the stack so it can be printed in the correct order."""

    _instance = None

    def __new__(cls, *args: Any, **kwargs: str):
        """Check if instance already exists."""
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, max_log_messages: int):
        """Initialize the logger with a maximum number of log messages to store."""
        self.log_messages = []
        self.max_log_messages = max_log_messages

    def display_log(self, message: str) -> None:
        """Append messages to the end of the logger."""
        # Add timestamp between brackets before message
        timestamp = datetime.now().strftime("%H:%M:%S")
        message = f"[{timestamp}] {message}"

        self.log_messages.append(message)
        if len(self.log_messages) > self.max_log_messages:
            self.log_messages.pop(0)  # Remove the oldest message

    def show_log(self) -> None:
        """Show the log in the log stack."""
        for _, msg in enumerate(self.log_messages):
            print(msg)
