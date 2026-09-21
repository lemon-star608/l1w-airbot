import math
import unittest

from l1w_teleop.control import (
    ArmCommand,
    CommandSafetyGate,
    DogCommand,
    InputMapping,
    MappingConfig,
    RobotCommands,
)
from l1w_teleop.control.mapping import _unit_quaternion
from l1w_teleop.input.models import ControllerFrame, TeleopInputs


def inputs(
    left_axis=(0.0, 0.0),
    right_axis=(0.0, 0.0),
    left_trigger=0.0,
    right_grip=0.0,
    right_trigger=0.0,
    left_buttons=(False, False),
    right_buttons=(False, False),
    right_axis_click=False,
    left_pose=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0),
    right_pose=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0),
):
    frame = ControllerFrame(
        local_monotonic_ns=0,
        sdk_timestamp_ns=0,
        pose=(0.0,) * 7,
        grip=0.0,
        trigger=0.0,
        axis=(0.0, 0.0),
    )
    left = ControllerFrame(
        local_monotonic_ns=0,
        sdk_timestamp_ns=0,
        pose=left_pose,
        grip=0.0,
        trigger=left_trigger,
        axis=left_axis,
        buttons=left_buttons,
    )
    right = ControllerFrame(
        local_monotonic_ns=0,
        sdk_timestamp_ns=0,
        pose=right_pose,
        grip=right_grip,
        trigger=right_trigger,
        axis=right_axis,
        buttons=right_buttons,
        axis_click=right_axis_click,
    )
    return TeleopInputs(left=left, right=right)


class InputMappingTests(unittest.TestCase):
    def test_deadzone_and_disabled_deadman_give_safe_zero(self):
        mapping = InputMapping()
        result = mapping.map(inputs(left_axis=(0.10, 0.08), right_axis=(0.11, 0.0)))
        self.assertFalse(result.dog.enabled)
        self.assertFalse(result.arm.enabled)
        self.assertEqual(
            (result.dog.forward, result.dog.rotate, result.dog.lateral),
            (0.0, 0.0, 0.0),
        )

    def test_dog_mapping_is_scaled_and_limited(self):
        config = MappingConfig(
            deadzone=0.1,
            dog_forward_scale=0.2,
            dog_lateral_scale=0.2,
            dog_rotate_scale=0.3,
        )
        result = InputMapping(config).map(
            inputs(
                left_axis=(1.0, -20.0),
                right_axis=(1.0, 0.0),
                left_trigger=0.6,
                left_buttons=(True, False),
            )
        )
        self.assertTrue(result.dog.enabled)
        self.assertAlmostEqual(result.dog.forward, 0.2)
        self.assertAlmostEqual(result.dog.rotate, -0.3)
        self.assertAlmostEqual(result.dog.lateral, -0.2)

    def test_default_dog_speeds_use_walk_test_values(self):
        result = InputMapping().map(
            inputs(
                left_axis=(1.0, -1.0),
                right_axis=(1.0, 0.0),
                left_trigger=1.0,
                left_buttons=(True, False),
            )
        )
        self.assertTrue(result.dog.enabled)
        self.assertAlmostEqual(result.dog.forward, 0.50)
        self.assertAlmostEqual(result.dog.lateral, -0.30)
        self.assertAlmostEqual(result.dog.rotate, -0.50)

    def test_pico_joystick_forward_direction_is_positive_dog_forward(self):
        result = InputMapping(MappingConfig(deadzone=0.1)).map(
            inputs(
                left_axis=(0.0, -1.0),
                left_trigger=1.0,
                left_buttons=(True, False),
            )
        )
        self.assertTrue(result.dog.enabled)
        self.assertAlmostEqual(result.dog.forward, 0.50)
        self.assertAlmostEqual(result.dog.lateral, 0.0)
        self.assertAlmostEqual(result.dog.rotate, 0.0)

    def test_pico_left_x_commands_right_lateral_only(self):
        result = InputMapping(MappingConfig(deadzone=0.1)).map(
            inputs(
                left_axis=(1.0, 0.0),
                left_trigger=1.0,
                left_buttons=(True, False),
            )
        )
        self.assertTrue(result.dog.enabled)
        self.assertAlmostEqual(result.dog.forward, 0.0)
        self.assertAlmostEqual(result.dog.lateral, -0.30)
        self.assertAlmostEqual(result.dog.rotate, 0.0)

    def test_pico_right_x_commands_left_rotation_only(self):
        result = InputMapping(MappingConfig(deadzone=0.1)).map(
            inputs(
                right_axis=(1.0, 0.0),
                left_trigger=1.0,
                left_buttons=(True, False),
            )
        )
        self.assertTrue(result.dog.enabled)
        self.assertAlmostEqual(result.dog.forward, 0.0)
        self.assertAlmostEqual(result.dog.lateral, 0.0)
        self.assertAlmostEqual(result.dog.rotate, -0.50)

    def test_arm_requires_right_grip_and_maps_trigger_to_gripper(self):
        mapping = InputMapping()
        mapping.map(inputs(left_buttons=(True, False)))
        result = mapping.map(
            inputs(right_axis=(0.5, -0.5), right_grip=0.7, right_trigger=1.0),
            arm_mode="joystick",
        )
        self.assertTrue(result.arm.enabled)
        self.assertAlmostEqual(result.arm.vx, -0.0345454545, places=8)
        self.assertAlmostEqual(result.arm.vy, 0.0345454545, places=8)
        self.assertAlmostEqual(result.arm.vz, 0.0)
        self.assertAlmostEqual(result.arm.gripper, 0.072)

    def test_joystick_arm_requires_motion_mode(self):
        result = InputMapping().map(
            inputs(right_axis=(0.5, 0.0), right_grip=0.8),
            arm_mode="joystick",
        )
        self.assertFalse(result.arm.enabled)
        self.assertEqual(result.arm.vx, 0.0)

    def test_gripper_target_latches_while_grip_is_released(self):
        arm_pose = ((0.30, 0.00, 0.20), (0.0, 0.0, 0.0, 1.0))
        mapping = InputMapping()
        mapping.map(inputs(left_buttons=(True, False)), current_arm_pose=arm_pose)
        opened = mapping.map(
            inputs(right_grip=0.8, right_trigger=1.0),
            current_arm_pose=arm_pose,
        )
        released = mapping.map(
            inputs(right_grip=0.0, right_trigger=0.0),
            current_arm_pose=arm_pose,
        )
        self.assertAlmostEqual(opened.arm.gripper, 0.072)
        self.assertTrue(opened.arm.enabled)
        self.assertAlmostEqual(released.arm.gripper, 0.072)
        self.assertFalse(released.arm.enabled)
        trigger_released = mapping.map(
            inputs(right_grip=0.0, right_trigger=0.0),
            current_arm_pose=arm_pose,
        )
        self.assertAlmostEqual(trigger_released.arm.gripper, 0.072)
        reengaged = mapping.map(
            inputs(right_grip=0.8, right_trigger=0.0),
            current_arm_pose=arm_pose,
        )
        self.assertAlmostEqual(reengaged.arm.gripper, 0.0)

    def test_pose_mode_anchors_to_current_arm_pose(self):
        arm_pose = ((0.30, 0.00, 0.20), (0.0, 0.0, 0.0, 1.0))
        mapping = InputMapping(MappingConfig(pose_translation_scale=1.0))
        mapping.map(
            inputs(left_buttons=(True, False)), current_arm_pose=arm_pose
        )
        first = mapping.map(inputs(right_grip=0.8), current_arm_pose=arm_pose)
        second = mapping.map(
            inputs(right_grip=0.8),
            arm_mode="pose",
            current_arm_pose=arm_pose,
        )
        self.assertTrue(first.arm.enabled)
        self.assertEqual(first.arm.position, arm_pose[0])
        self.assertEqual(first.arm.orientation, arm_pose[1])
        self.assertTrue(second.arm.enabled)

    def test_pose_mode_release_resets_anchor(self):
        arm_pose = ((0.30, 0.00, 0.20), (0.0, 0.0, 0.0, 1.0))
        mapping = InputMapping(MappingConfig(pose_translation_scale=1.0))
        mapping.map(inputs(left_buttons=(True, False)), current_arm_pose=arm_pose)
        released = mapping.map(inputs(right_grip=0.1), current_arm_pose=arm_pose)
        self.assertFalse(released.arm.enabled)
        self.assertTrue(mapping.map(
            inputs(right_grip=0.8), arm_mode="pose", current_arm_pose=arm_pose
        ).arm.enabled)

    def test_pose_mode_release_keeps_held_pose_and_reengages_without_jump(self):
        arm_pose = ((0.30, 0.00, 0.20), (0.0, 0.0, 0.0, 1.0))
        config = MappingConfig(
            pose_translation_scale=1.0,
        )
        mapping = InputMapping(config)
        mapping.map(inputs(left_buttons=(True, False)), current_arm_pose=arm_pose)
        mapping.map(
            inputs(right_grip=0.8), arm_mode="pose", current_arm_pose=arm_pose
        )
        released = mapping.map(
            inputs(right_grip=0.1), arm_mode="pose", current_arm_pose=arm_pose
        )
        self.assertFalse(released.arm.enabled)
        self.assertEqual(released.arm.position, arm_pose[0])

        reengaged = mapping.map(inputs(right_grip=0.8), current_arm_pose=arm_pose)
        self.assertTrue(reengaged.arm.enabled)
        self.assertEqual(reengaged.arm.position, arm_pose[0])

    def test_pose_mode_grip_has_hysteresis(self):
        arm_pose = ((0.30, 0.00, 0.20), (0.0, 0.0, 0.0, 1.0))
        mapping = InputMapping()
        mapping.map(
            inputs(left_buttons=(True, False)), current_arm_pose=arm_pose
        )
        self.assertTrue(mapping.map(
            inputs(right_grip=0.55),
            arm_mode="pose",
            current_arm_pose=arm_pose,
        ).arm.enabled)
        self.assertTrue(mapping.map(
            inputs(right_grip=0.45),
            arm_mode="pose",
            current_arm_pose=arm_pose,
        ).arm.enabled)
        self.assertFalse(mapping.map(
            inputs(right_grip=0.35),
            arm_mode="pose",
            current_arm_pose=arm_pose,
        ).arm.enabled)

    def test_pose_translation_is_scaled_without_local_workspace_limit(self):
        arm_pose = ((0.30, 0.00, 0.20), (0.0, 0.0, 0.0, 1.0))
        config = MappingConfig(
            pose_translation_scale=1.0,
        )
        mapping = InputMapping(config)
        mapping.map(
            inputs(left_buttons=(True, False)), current_arm_pose=arm_pose
        )
        mapping.map(
            inputs(right_grip=0.8), current_arm_pose=arm_pose
        )
        moved = mapping.map(
            inputs(right_grip=0.8, right_pose=(1.0, 1.0, 1.0, 0, 0, 0, 1)),
            arm_mode="pose",
            current_arm_pose=arm_pose,
        )
        self.assertTrue(moved.arm.enabled)
        self.assertAlmostEqual(moved.arm.position[0], -0.70)
        self.assertAlmostEqual(moved.arm.position[1], -1.00)
        self.assertAlmostEqual(moved.arm.position[2], 1.20)

    def test_pose_mode_translates_vr_frame_into_airbot_frame(self):
        arm_pose = ((0.30, 0.00, 0.20), (0.0, 0.0, 0.0, 1.0))
        mapping = InputMapping(
            MappingConfig(
                pose_translation_scale=0.1,
            )
        )
        mapping.map(inputs(left_buttons=(True, False)), current_arm_pose=arm_pose)
        mapping.map(
            inputs(right_grip=0.8), arm_mode="pose", current_arm_pose=arm_pose
        )
        moved = mapping.map(
            inputs(right_grip=0.8, right_pose=(1.0, 2.0, 3.0, 0, 0, 0, 1)),
            arm_mode="pose",
            current_arm_pose=arm_pose,
        )

        self.assertAlmostEqual(moved.arm.position[0], 0.00)
        self.assertAlmostEqual(moved.arm.position[1], -0.10)
        self.assertAlmostEqual(moved.arm.position[2], 0.40)

    def test_pose_mode_maps_relative_vr_rotation_to_arm_orientation(self):
        arm_pose = ((0.25, -0.09, 0.58), (0.0, 0.0, 0.0, 1.0))
        config = MappingConfig()
        mapping = InputMapping(config)
        mapping.map(inputs(left_buttons=(True, False)), current_arm_pose=arm_pose)
        mapping.map(inputs(right_grip=0.8), current_arm_pose=arm_pose)

        # A +90-degree VR-X rotation becomes a 90-degree AIRBOT -Y rotation.
        # This locks the frame transform, not only the angle.
        moved = mapping.map(
            inputs(
                right_grip=0.8,
                right_pose=(
                    0.0, 0.0, 0.0,
                    math.sqrt(0.5), 0.0, 0.0, math.sqrt(0.5),
                ),
            ),
            arm_mode="pose",
            current_arm_pose=arm_pose,
        )

        self.assertTrue(moved.arm.enabled)
        target = moved.arm.orientation
        norm = math.sqrt(sum(value * value for value in target))
        self.assertAlmostEqual(norm, 1.0)
        angle = 2.0 * math.acos(max(-1.0, min(1.0, target[3])))
        self.assertAlmostEqual(angle, math.pi / 2.0, places=6)
        self.assertAlmostEqual(target[0], 0.0, places=6)
        self.assertAlmostEqual(target[1], -math.sqrt(0.5), places=6)
        # Also lock the other VR axes: +Y maps to AIRBOT +Z, +Z to -X.
        axis_cases = (
            ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
            ((0.0, 0.0, 1.0), (-1.0, 0.0, 0.0)),
        )
        for vr_axis, airbot_axis in axis_cases:
            mapping = InputMapping(config)
            mapping.map(inputs(left_buttons=(True, False)), current_arm_pose=arm_pose)
            mapping.map(inputs(right_grip=0.8), current_arm_pose=arm_pose)
            rotated = mapping.map(
                inputs(
                    right_grip=0.8,
                    right_pose=(0.0, 0.0, 0.0, *[value * math.sqrt(0.5) for value in vr_axis], math.sqrt(0.5)),
                ),
                arm_mode="pose",
                current_arm_pose=arm_pose,
            )
            target = rotated.arm.orientation
            for actual, expected in zip(target[:3], airbot_axis):
                self.assertAlmostEqual(
                    actual, expected * math.sin(math.pi / 4.0), places=6
                )
        self.assertAlmostEqual(target[2], 0.0, places=6)
        self.assertAlmostEqual(target[3], math.cos(math.pi / 4.0), places=6)

    def test_pose_mode_can_lock_sdk_return_zero_orientation(self):
        arm_pose = ((0.30, 0.00, 0.20), (0.1, -0.2, 0.3, 0.9))
        mapping = InputMapping(MappingConfig(lock_orientation=True))
        mapping.map(inputs(left_buttons=(True, False)), current_arm_pose=arm_pose)
        mapping.map(inputs(right_grip=0.8), current_arm_pose=arm_pose)

        moved = mapping.map(
            inputs(
                right_grip=0.8,
                right_pose=(0.3, 0.0, 0.0, math.sqrt(0.5), 0.0, 0.0, math.sqrt(0.5)),
            ),
            current_arm_pose=arm_pose,
        )

        self.assertTrue(moved.arm.enabled)
        self.assertAlmostEqual(moved.arm.position[0], 0.30)
        self.assertAlmostEqual(moved.arm.position[1], -0.30)
        self.assertAlmostEqual(moved.arm.position[2], 0.20)
        for actual, expected in zip(
            moved.arm.orientation, MappingConfig.lock_orientation_target
        ):
            self.assertAlmostEqual(actual, expected, places=8)


    def test_pose_mode_locks_the_sdk_zero_orientation(self):
        arm_pose = ((0.30, 0.00, 0.20), (0.0, 0.0, 0.5, -0.5))
        mapping = InputMapping(
            MappingConfig(
                lock_orientation=True,
                lock_orientation_target=(0.0, 0.0, 0.0, 1.0),
            )
        )
        mapping.map(inputs(left_buttons=(True, False)), current_arm_pose=arm_pose)

        moved = mapping.map(
            inputs(right_grip=0.8, right_pose=(0.3, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0)),
            current_arm_pose=arm_pose,
        )

        self.assertTrue(moved.arm.enabled)
        self.assertEqual(moved.arm.orientation, (0.0, 0.0, 0.0, 1.0))

    def test_release_sets_velocity_to_zero(self):
        result = InputMapping().map(
            inputs(left_axis=(0.5, 0.5), left_trigger=0.1)
        )
        self.assertFalse(result.dog.enabled)
        self.assertEqual(result.dog.forward, 0.0)

    def test_motion_mode_transitions_with_dedicated_buttons(self):
        mapping = InputMapping()
        enter = mapping.map(inputs(left_buttons=(True, False)))
        self.assertEqual(enter.motion_mode, "motion")
        self.assertEqual(enter.dog_mode_command, "stand_up")

        motion = mapping.map(inputs(right_buttons=(False, False), left_trigger=0.8))
        self.assertEqual(motion.motion_mode, "motion")
        self.assertTrue(motion.dog.enabled)

        exit_motion = mapping.map(inputs(right_buttons=(False, True)))
        self.assertEqual(exit_motion.motion_mode, "damping")
        self.assertEqual(exit_motion.dog_mode_command, "damping")
        self.assertFalse(exit_motion.dog.enabled)

    def test_arm_return_zero_requires_motion_and_right_stick_click(self):
        mapping = InputMapping()
        result = mapping.map(
            inputs(left_buttons=(True, False), right_axis_click=True)
        )
        self.assertEqual(result.motion_mode, "motion")
        self.assertEqual(result.arm_mode_command, "return_zero")

        blocked = InputMapping().map(inputs(right_axis_click=True))
        self.assertEqual(blocked.motion_mode, "damping")
        self.assertEqual(blocked.arm_mode_command, "")

    def test_arm_return_zero_triggers_once_per_stick_press(self):
        mapping = InputMapping()
        mapping.map(inputs(left_buttons=(True, False)))
        first = mapping.map(inputs(right_axis_click=True))
        held = mapping.map(inputs(right_axis_click=True))
        released = mapping.map(inputs(right_axis_click=False))
        again = mapping.map(inputs(right_axis_click=True))
        self.assertEqual(first.arm_mode_command, "return_zero")
        self.assertEqual(held.arm_mode_command, "")
        self.assertEqual(released.arm_mode_command, "")
        self.assertEqual(again.arm_mode_command, "return_zero")

    def test_hardware_mapping_disables_return_zero_without_pose_clamp(self):
        config = MappingConfig(
            pose_translation_scale=0.2,
            allow_return_zero=False,
        )
        mapping = InputMapping(config)
        arm_pose = ((0.126, 0.0, 0.211), (0.0, 0.0, 0.0, 1.0))
        mapping.map(
            inputs(left_buttons=(True, False), right_axis_click=True),
            current_arm_pose=arm_pose,
        )
        moved = mapping.map(
            inputs(right_grip=1.0, right_pose=(1.0, 1.0, 1.0, 0, 0, 0, 1)),
            current_arm_pose=arm_pose,
        )
        self.assertEqual(moved.arm_mode_command, "")
        self.assertLessEqual(
            max(
                abs(target - anchor)
                for target, anchor in zip(moved.arm.position, arm_pose[0])
            ),
            0.2 * math.sqrt(3.0) + 1e-9,
        )

    def test_mounted_arm_tracking_forces_the_dog_to_stop(self):
        config = MappingConfig(arm_motion_stops_dog=True)
        mapping = InputMapping(config)
        arm_pose = ((0.30, 0.0, 0.20), (0.0, 0.0, 0.0, 1.0))
        mapping.map(inputs(left_buttons=(True, False)), current_arm_pose=arm_pose)

        dog_only = mapping.map(
            inputs(left_axis=(0.0, -1.0), left_trigger=1.0),
            current_arm_pose=arm_pose,
        )
        self.assertTrue(dog_only.dog.enabled)

        arm_tracking = mapping.map(
            inputs(
                left_axis=(0.0, -1.0),
                left_trigger=1.0,
                right_grip=1.0,
            ),
            current_arm_pose=arm_pose,
        )
        self.assertTrue(arm_tracking.arm.enabled)
        self.assertFalse(arm_tracking.dog.enabled)


class CommandSafetyGateTests(unittest.TestCase):
    def test_startup_blocks_enabled_commands(self):
        gate = CommandSafetyGate(startup_hold_s=10.0)
        command = RobotCommands()
        result, state = gate.apply(command, True)
        self.assertFalse(result.dog.enabled)
        self.assertFalse(result.arm.enabled)
        self.assertFalse(state.dog_enabled)
        self.assertFalse(state.arm_enabled)

    def test_startup_defers_dog_mode_transition(self):
        gate = CommandSafetyGate(startup_hold_s=10.0)
        command = RobotCommands(dog_mode_command="stand_up", motion_mode="motion")
        result, _ = gate.apply(command, True)
        self.assertEqual(result.dog_mode_command, "")

        gate._started_ns -= 11_000_000_000
        result, _ = gate.apply(RobotCommands(motion_mode="motion"), True)
        self.assertEqual(result.dog_mode_command, "stand_up")

        result, _ = gate.apply(RobotCommands(motion_mode="motion"), True)
        self.assertEqual(result.dog_mode_command, "")

    def test_startup_clears_deferred_transition_on_input_loss(self):
        gate = CommandSafetyGate(startup_hold_s=10.0)
        gate.apply(
            RobotCommands(dog_mode_command="stand_up", motion_mode="motion"), True
        )
        gate.apply(RobotCommands(motion_mode="motion"), False)
        gate._started_ns -= 11_000_000_000
        result, _ = gate.apply(RobotCommands(motion_mode="motion"), True)
        self.assertEqual(result.dog_mode_command, "")

    def test_unhealthy_input_blocks_commands(self):
        gate = CommandSafetyGate(startup_hold_s=0.0)
        command = RobotCommands()
        result, state = gate.apply(command, False)
        self.assertFalse(result.dog.enabled)
        self.assertFalse(result.arm.enabled)
        self.assertFalse(state.input_healthy)

    def test_enabled_commands_pass_after_startup_when_healthy(self):
        gate = CommandSafetyGate(startup_hold_s=0.0)
        command = RobotCommands(
            dog=DogCommand(0.1, 0.0, 0.0, enabled=True),
            arm=ArmCommand(0.02, 0.0, 0.0, 0.07, enabled=True),
        )
        result, state = gate.apply(command, True)
        self.assertTrue(result.dog.enabled)
        self.assertTrue(result.arm.enabled)
        self.assertTrue(state.input_healthy)

    def test_safety_gate_preserves_disabled_pose_target(self):
        gate = CommandSafetyGate(startup_hold_s=0.0)
        command = RobotCommands(
            arm=ArmCommand(
                position=(0.3, 0.0, 0.3),
                orientation=(0.0, 0.0, 0.71, -0.71),
                gripper=0.07,
                enabled=False,
                mode="pose",
            )
        )
        result, _ = gate.apply(command, False)
        self.assertFalse(result.arm.enabled)
        self.assertEqual(result.arm.position, (0.3, 0.0, 0.3))
        self.assertEqual(result.arm.orientation, (0.0, 0.0, 0.71, -0.71))
        self.assertEqual(result.arm.gripper, 0.07)

    def test_safety_gate_preserves_mode_state_and_commands(self):
        gate = CommandSafetyGate(startup_hold_s=0.0)
        command = RobotCommands(
            dog_mode_command="stand_up",
            arm_mode_command="return_zero",
            motion_mode="motion",
        )
        result, state = gate.apply(command, True)
        self.assertTrue(state.input_healthy)
        self.assertEqual(result.dog_mode_command, "stand_up")
        self.assertEqual(result.arm_mode_command, "return_zero")
        self.assertEqual(result.motion_mode, "motion")


if __name__ == "__main__":
    unittest.main()
