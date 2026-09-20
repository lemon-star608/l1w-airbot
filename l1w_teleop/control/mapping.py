import math
from typing import Optional, Tuple

from ..input.models import TeleopInputs
from .models import ArmCommand, DogCommand, MappingConfig, RobotCommands


PosePair = Tuple[tuple, tuple]


class InputMapping:
    def __init__(self, config: Optional[MappingConfig] = None):
        self._config = config or MappingConfig()
        self._pose_anchor = None
        self._last_pose_target = None
        self._arm_engaged = False
        self._gripper_target = self._config.gripper_initial
        self._right_stick_was_pressed = False
        self._motion_mode = "damping"

    def map(
        self,
        inputs: TeleopInputs,
        arm_mode: str = "pose",
        input_healthy: bool = True,
        current_arm_pose: Optional[PosePair] = None,
    ) -> RobotCommands:
        previous_mode = self._motion_mode
        self._update_motion_mode(inputs, input_healthy)
        mode_transition = self._transition_command(previous_mode, self._motion_mode)
        if arm_mode == "pose":
            arm = self._map_pose_arm(
                inputs, input_healthy and self._motion_mode == "motion", current_arm_pose
            )
        elif arm_mode == "joystick":
            arm = self._map_joystick_arm(
                inputs, input_healthy and self._motion_mode == "motion"
            )
        else:
            raise ValueError("arm_mode must be pose or joystick")
        dog = self._map_dog(inputs)
        if self._config.arm_motion_stops_dog and arm.enabled:
            dog = DogCommand(enabled=False)
        if self._motion_mode != "motion":
            dog = DogCommand(enabled=False)
        return RobotCommands(
            dog=dog,
            arm=arm,
            arm_mode_command=self._arm_mode_command(inputs),
            dog_mode_command=mode_transition,
            motion_mode=self._motion_mode,
        )

    def _map_dog(self, inputs: TeleopInputs) -> DogCommand:
        config = self._config
        dog_enabled = self._motion_mode == "motion" and inputs.left.trigger >= config.enable_threshold
        # PICO joystick Y is negative when pushed forward.
        forward_raw = -_rescaled(inputs.left.axis[1], config.deadzone)
        lateral_raw = _rescaled(inputs.left.axis[0], config.deadzone)
        # Positive PICO X is right; normalized lateral and rotation are left.
        rotate_raw = -_rescaled(inputs.right.axis[0], config.deadzone)
        if not dog_enabled:
            return DogCommand(enabled=False)
        return DogCommand(
            forward=_scaled(forward_raw, config.dog_forward_scale),
            rotate=_scaled(rotate_raw, config.dog_rotate_scale),
            lateral=_scaled(-lateral_raw, config.dog_lateral_scale),
            enabled=dog_enabled,
        )

    def _arm_mode_command(self, inputs: TeleopInputs) -> str:
        if self._motion_mode != "motion":
            self._right_stick_was_pressed = inputs.right.axis_click
            return ""
        if not self._config.allow_return_zero:
            self._right_stick_was_pressed = inputs.right.axis_click
            return ""
        edge = inputs.right.axis_click and not self._right_stick_was_pressed
        self._right_stick_was_pressed = inputs.right.axis_click
        if not edge or inputs.right.grip >= self._config.release_threshold:
            return ""
        return "return_zero"

    def _update_motion_mode(self, inputs: TeleopInputs, input_healthy: bool) -> None:
        if not input_healthy:
            self._motion_mode = "damping"
            return
        # Right A is reserved by the XRoboToolkit app; use left X instead.
        if inputs.left.buttons[0]:
            self._motion_mode = "motion"
        elif inputs.right.buttons[1]:
            self._motion_mode = "damping"

    def _transition_command(self, previous: str, current: str) -> str:
        if previous == current:
            return ""
        return "stand_up" if current == "motion" else "damping"

    def _map_joystick_arm(self, inputs: TeleopInputs, enabled: bool) -> ArmCommand:
        config = self._config
        self._update_arm_engagement(inputs, enabled)
        arm_enabled = enabled and self._arm_engaged
        gripper = self._gripper_command(inputs)
        arm_x_raw = _rescaled(inputs.right.axis[0], config.deadzone)
        arm_y_raw = _rescaled(inputs.right.axis[1], config.deadzone)
        if not arm_enabled:
            return ArmCommand(gripper=gripper, enabled=False, mode="joystick")
        return ArmCommand(
            vx=_scaled(arm_y_raw, config.arm_speed),
            vy=_scaled(arm_x_raw, config.arm_speed),
            vz=0.0,
            gripper=gripper,
            enabled=True,
            mode="joystick",
        )

    def _map_pose_arm(
        self,
        inputs: TeleopInputs,
        input_healthy: bool,
        current_arm_pose: Optional[PosePair],
    ) -> ArmCommand:
        config = self._config
        self._update_arm_engagement(inputs, input_healthy)
        gripper = self._gripper_command(inputs)
        if not self._arm_engaged or current_arm_pose is None or len(inputs.right.pose) != 7:
            self._pose_anchor = None
            if self._last_pose_target is None and current_arm_pose is not None:
                self._last_pose_target = (
                    tuple(float(v) for v in current_arm_pose[0]),
                    _unit_quaternion(current_arm_pose[1]),
                )
            held_pose = self._last_pose_target or ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0))
            return ArmCommand(
                position=held_pose[0],
                orientation=held_pose[1],
                gripper=gripper,
                enabled=False,
                mode="pose",
            )

        controller_position = tuple(float(v) for v in inputs.right.pose[:3])
        controller_orientation = _unit_quaternion(inputs.right.pose[3:])
        arm_position = tuple(float(v) for v in current_arm_pose[0])
        arm_orientation = _unit_quaternion(current_arm_pose[1])

        if self._pose_anchor is None:
            self._pose_anchor = (
                controller_position,
                controller_orientation,
                arm_position,
                arm_orientation,
            )
            self._last_pose_target = (arm_position, arm_orientation)

        anchor_cp, anchor_cq, anchor_ap, anchor_aq = self._pose_anchor
        delta_p = tuple(
            (controller_position[source] - anchor_cp[source])
            * sign
            * config.pose_translation_scale
            for source, sign in config.pose_translation_axes
        )
        desired_p = tuple(anchor_ap[i] + delta_p[i] for i in range(3))

        if config.lock_orientation:
            desired_q = _unit_quaternion(config.lock_orientation_target)
        else:
            controller_world_q = _frame_rotation_quaternion(controller_orientation)
            anchor_world_q = _frame_rotation_quaternion(anchor_cq)
            delta_q = _quaternion_multiply(
                controller_world_q,
                _quaternion_inverse(anchor_world_q),
            )
            desired_q = _quaternion_multiply(delta_q, anchor_aq)

        target_p = desired_p
        target_q = _unit_quaternion(desired_q)
        self._last_pose_target = (target_p, target_q)
        return ArmCommand(
            position=target_p,
            orientation=target_q,
            gripper=gripper,
            enabled=True,
            mode="pose",
        )

    def _update_arm_engagement(self, inputs: TeleopInputs, enabled: bool) -> None:
        config = self._config
        if self._arm_engaged:
            self._arm_engaged = (
                enabled and inputs.right.grip >= config.release_threshold
            )
        else:
            self._arm_engaged = (
                enabled and inputs.right.grip >= config.enable_threshold
            )

    def _gripper_command(self, inputs: TeleopInputs) -> float:
        config = self._config
        if self._arm_engaged:
            self._gripper_target = _map_gripper(
                inputs.right.trigger, config.gripper_min, config.gripper_max
            )
        return self._gripper_target


def _rescaled(value: float, deadzone: float) -> float:
    value = _unit(value)
    if abs(value) <= deadzone:
        return 0.0
    sign = 1.0 if value > 0 else -1.0
    return sign * (abs(value) - deadzone) / (1.0 - deadzone)


def _scaled(value: float, scale: float) -> float:
    return _unit(value * scale)


def _unit(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return max(-1.0, min(1.0, value))


def _map_gripper(trigger: float, minimum: float, maximum: float) -> float:
    trigger = max(0.0, min(1.0, _unit(trigger)))
    return minimum + trigger * (maximum - minimum)


def _unit_quaternion(value) -> tuple:
    value = tuple(float(v) for v in value)
    if len(value) != 4 or not all(math.isfinite(v) for v in value):
        return (0.0, 0.0, 0.0, 1.0)
    norm = math.sqrt(sum(v * v for v in value))
    if norm <= 1e-9:
        return (0.0, 0.0, 0.0, 1.0)
    return tuple(v / norm for v in value)


def _frame_rotation_quaternion(value) -> tuple:
    """Apply the XRoboToolkit VR-to-world rotation to a quaternion."""
    # Equivalent to R_HEADSET_TO_WORLD = [[0,0,-1],[-1,0,0],[0,1,0]].
    # It is a 120-degree rotation; signs come from the matrix antisymmetric
    # terms, not from an arbitrary axis permutation.
    frame_q = (0.5, -0.5, -0.5, 0.5)
    return _quaternion_multiply(
        _quaternion_multiply(frame_q, _unit_quaternion(value)),
        _quaternion_inverse(frame_q),
    )


def _quaternion_multiply(a, b) -> tuple:
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def _quaternion_inverse(q) -> tuple:
    x, y, z, w = _unit_quaternion(q)
    return (-x, -y, -z, w)
