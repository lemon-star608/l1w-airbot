from .interface import ArmClient


class MockArmClient(ArmClient):
    def __init__(self):
        self.hold_count = 0
        self.commands = []
        self.pose_commands = []
        self.joint_commands = []
        self.zero_count = 0
        self.control_enabled = False
        self._pose = ((0.30, 0.0, 0.30), (0.0, 0.0, 0.5, -0.5))

    def enable_control(self) -> None:
        self.control_enabled = True

    def hold(self) -> None:
        self.hold_count += 1

    def get_end_pose(self):
        return self._pose

    def get_joint_angles(self):
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    def send_cartesian_velocity(self, vx: float, vy: float, vz: float, gripper: float) -> None:
        self.commands.append((vx, vy, vz, gripper))

    def send_cartesian_pose(self, position, orientation, gripper: float) -> None:
        self.pose_commands.append((tuple(position), tuple(orientation), gripper))
        self._pose = (tuple(position), tuple(orientation))

    def return_zero(self) -> None:
        self.zero_count += 1
        self._pose = ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0))

    def move_joint(self, angles, blocking: bool = False, timeout_ms: int = 5000) -> bool:
        self.joint_commands.append((tuple(angles), blocking, timeout_ms))
        return True

    def close(self) -> None:
        self.control_enabled = False
