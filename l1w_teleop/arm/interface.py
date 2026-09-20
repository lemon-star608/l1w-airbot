from abc import ABC, abstractmethod


class ArmClient(ABC):
    """Boundary for the AIRBOT official SDK client."""

    @abstractmethod
    def hold(self) -> None:
        """Keep the arm in its current commanded pose."""

    @abstractmethod
    def get_end_pose(self):
        """Return ((x, y, z), (qx, qy, qz, qw)), or None if unavailable."""

    @abstractmethod
    def send_cartesian_velocity(self, vx: float, vy: float, vz: float, gripper: float) -> None:
        """Send a bounded Cartesian velocity and gripper target."""

    @abstractmethod
    def send_cartesian_pose(self, position, orientation, gripper: float) -> None:
        """Send a Cartesian pose and gripper target."""

    @abstractmethod
    def return_zero(self) -> None:
        """Return the arm to its configured home pose."""

    @abstractmethod
    def move_joint(self, angles, blocking: bool = False, timeout_ms: int = 5000) -> bool:
        """Command a joint-space target."""
