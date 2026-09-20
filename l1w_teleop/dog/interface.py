from abc import ABC, abstractmethod


class DogClient(ABC):
    """Boundary for the L1-W high-level command interface."""

    @abstractmethod
    def send_zero(self) -> None:
        """Hold the dog stationary using its native safe state."""

    @abstractmethod
    def send_command(self, forward: float, rotate: float, lateral: float) -> None:
        """Send the normalized SDK remote command."""

    @abstractmethod
    def set_mode(self, mode: str) -> None:
        """Set stand_up or damping mode."""


class DogStatusMonitor(ABC):
    """Read-only L1-W UDP status source."""

    @abstractmethod
    def status(self):
        """Return the latest snapshot, or None before robot feedback."""

    @abstractmethod
    def close(self):
        """Release the UDP socket."""
