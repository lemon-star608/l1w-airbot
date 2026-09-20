from .interface import DogClient


class MockDogClient(DogClient):
    def __init__(self):
        self.zero_count = 0
        self.commands = []
        self.mode_commands = []

    def send_zero(self) -> None:
        self.zero_count += 1

    def send_command(self, forward: float, rotate: float, lateral: float) -> None:
        self.commands.append((forward, rotate, lateral))

    def set_mode(self, mode: str) -> None:
        self.mode_commands.append(mode)

    def update(self) -> None:
        """Match the real client's non-packet state-update hook."""
