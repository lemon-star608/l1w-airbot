import math
import time
from typing import Optional

from .interface import ArmClient


class AirbotArmClient(ArmClient):
    """AIRBOT SDK adapter.

    Construction and get_end_pose are read-only. A caller must explicitly call
    enable_control before any motion method can reach the arm.
    """

    G2_GRIPPER_RANGE = (0.0, 0.072)
    POSE_COMMAND_EPSILON_M = 0.001
    POSE_COMMAND_EPSILON_RAD = 0.02
    REJECTED_POSE_RETRY_S = 0.5

    def __init__(
        self,
        host: str = "localhost",
        port: int = 50051,
        arm_dof: int = 6,
    ):
        from arm_sdk import AirbotClient, ArmControlOptions, CartesianPose

        self._cartesian_pose_type = CartesianPose
        self._options_type = ArmControlOptions
        self._client = AirbotClient(host=host, port=port, arm_dof=arm_dof)
        self._control_enabled = False
        self._last_pose = None
        self._last_gripper = None
        self._hold_pose = None
        self._hold_gripper = None
        self._hold_command_active = False
        self._last_command_rejected = False
        self._rejected_at = None

    def enable_control(self) -> None:
        from arm_sdk import Controller

        if self._control_enabled:
            return
        if not self._client.acquire_control():
            raise RuntimeError("failed to acquire AIRBOT control lease")
        if not self._client.switch_controller(Controller.servo_control):
            raise RuntimeError("failed to switch AIRBOT to servo control")
        self._control_enabled = True
        self._hold_command_active = False

    def current_gripper(self) -> float:
        state = self._client.get_eef_joint_state()
        if state is None:
            return 0.036
        return self._clamped_gripper(float(state.eef_pos))

    def hold(self) -> None:
        if self._hold_command_active:
            return
        pose = self._hold_pose or self.get_end_pose() or self._last_pose
        if pose is None:
            return
        gripper = self._hold_gripper
        if gripper is None:
            gripper = self.current_gripper()
        self._send_pose(pose[0], pose[1], gripper)
        self._hold_pose = (
            tuple(float(value) for value in pose[0]),
            tuple(float(value) for value in pose[1]),
        )
        self._hold_gripper = gripper
        self._hold_command_active = True

    def get_end_pose(self):
        pose = self._client.get_end_pose()
        if pose is None:
            return self._last_pose
        result = (
            tuple(float(value) for value in pose.position),
            tuple(float(value) for value in pose.orientation),
        )
        self._last_pose = result
        return result

    def get_joint_angles(self):
        state = self._client.get_arm_joint_state()
        if state is None:
            return None
        return tuple(float(value) for value in state.angles)

    def send_cartesian_velocity(self, vx: float, vy: float, vz: float, gripper: float) -> None:
        raise NotImplementedError("AIRBOT velocity control is not enabled yet")

    def send_cartesian_pose(self, position, orientation, gripper: float) -> None:
        position = tuple(float(value) for value in position)
        orientation = tuple(float(value) for value in orientation)
        if self._last_command_rejected:
            return
        if self._pose_matches_hold(position, orientation):
            return
        self._last_command_rejected = False
        if not self._send_pose(position, orientation, gripper):
            self._last_command_rejected = True
            self._rejected_at = time.monotonic()
            return
        self._last_gripper = self._clamped_gripper(gripper)
        self._hold_pose = (
            tuple(float(value) for value in position),
            tuple(float(value) for value in orientation),
        )
        self._hold_gripper = self._clamped_gripper(gripper)
        self._hold_command_active = False

    def recover_rejected_pose(self) -> None:
        """Retry one rejected Cartesian target, then clear the failure state."""
        if not self._last_command_rejected:
            return
        if (
            self._rejected_at is not None
            and time.monotonic() - self._rejected_at
            < AirbotArmClient.REJECTED_POSE_RETRY_S
        ):
            return
        self._last_command_rejected = False
        self._rejected_at = None
        if self._hold_pose is None:
            return
        if not self._send_pose(
            self._hold_pose[0], self._hold_pose[1], self._hold_gripper
        ):
            self._last_command_rejected = True
            self._rejected_at = time.monotonic()
            return
        self._last_gripper = self._hold_gripper
        self._hold_command_active = False

    @property
    def last_command_rejected(self) -> bool:
        return self._last_command_rejected

    def return_zero(self) -> None:
        self._require_control()
        if not self._client.return_zero():
            raise RuntimeError("AIRBOT return_zero was rejected")

    def move_joint(
        self, angles, blocking: bool = False, timeout_ms: int = 5000
    ) -> bool:
        self._require_control()
        gripper = self._last_gripper
        if gripper is None:
            gripper = self.current_gripper()
        options = self._options_type()
        options.eef_pos = gripper
        options.eef_eff = 6.0
        options.blocking = blocking
        accepted = self._client.move_joint(
            [float(value) for value in angles], options, timeout_ms=timeout_ms
        )
        if accepted and blocking:
            self._hold_pose = None
            self._hold_gripper = gripper
            self._hold_command_active = False
        return accepted

    def close(self) -> None:
        self._client.close()

    def emergency_hold(self) -> None:
        if self._control_enabled and self._hold_pose is not None:
            self._send_pose(
                self._hold_pose[0], self._hold_pose[1], self._hold_gripper
            )

    def _send_pose(self, position, orientation, gripper: float) -> bool:
        self._require_control()
        pose = self._cartesian_pose_type(
            position=tuple(float(value) for value in position),
            orientation=tuple(float(value) for value in orientation),
        )
        options = self._options_type()
        options.eef_pos = self._clamped_gripper(gripper)
        options.eef_eff = 6.0
        accepted = self._client.move_end_pose(pose, options)
        if not accepted:
            print(
                "AIRBOT rejected move_end_pose; keeping the last accepted target",
                flush=True,
            )
        return accepted

    def _pose_matches_hold(self, position, orientation) -> bool:
        if self._hold_pose is None:
            return False
        return (
            _distance(position, self._hold_pose[0])
            <= AirbotArmClient.POSE_COMMAND_EPSILON_M
            and _rotation_distance(orientation, self._hold_pose[1])
            <= AirbotArmClient.POSE_COMMAND_EPSILON_RAD
        )

    def _require_control(self) -> None:
        if not self._control_enabled:
            raise RuntimeError("AIRBOT control was not explicitly enabled")

    @staticmethod
    def _clamped_gripper(value: float) -> float:
        minimum, maximum = AirbotArmClient.G2_GRIPPER_RANGE
        return max(minimum, min(maximum, float(value)))


def _distance(a, b) -> float:
    return sum((float(av) - float(bv)) ** 2 for av, bv in zip(a, b)) ** 0.5


def _rotation_distance(a, b) -> float:
    norm_a = math.sqrt(sum(float(v) ** 2 for v in a))
    norm_b = math.sqrt(sum(float(v) ** 2 for v in b))
    if norm_a <= 1e-12 or norm_b <= 1e-12:
        return math.pi
    dot = abs(sum(float(av) * float(bv) for av, bv in zip(a, b))) / (norm_a * norm_b)
    return 2.0 * math.acos(max(-1.0, min(1.0, dot)))
