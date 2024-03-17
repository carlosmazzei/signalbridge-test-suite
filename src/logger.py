from datetime import datetime


class Logger:

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, max_log_messages):
        self.log_messages = []
        self.max_log_messages = max_log_messages

    def display_log(self, message):

        # Add timestamp between brackets before message
        timestamp = datetime.now().strftime("%H:%M:%S")
        message = f"[{timestamp}] {message}"

        self.log_messages.append(message)
        if len(self.log_messages) > self.max_log_messages:
            self.log_messages.pop(0)  # Remove the oldest message

    def show_log(self):
        for msg in enumerate(self.log_messages):
            print(msg)
