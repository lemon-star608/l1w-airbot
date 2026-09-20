import unittest
from unittest import mock

import math
import time

from l1w_teleop.arm.airbot import AirbotArmClient


class FakePose:
    position = (0.3, 0.0, 0.3)
    orientation = (0.0, 0.0, 0.5, -0.5)


class FakeGripper:
    eef_pos = 0.036


class FakeJointState:
    angles = (0.1, -0.2, 0.3, -0.1, 0.2, -0.3)


class FakeReadyJointState:
    angles = (0.0, -0.45, 0.85, -0.75, -0.5, 0.0)


class FakeOptions:
    last = None

    def __init__(self):
        self.eef_pos = None
        self.eef_eff = None
        FakeOptions.last = self


class AirbotArmClientTests(unittest.TestCase):
    def test_reads_pose_without_enabling_control(self):
        client = AirbotArmClient.__new__(AirbotArmClient)
        sdk_client = mock.Mock()
        sdk_client.get_end_pose.return_value = FakePose()
        client._client = sdk_client
        client._control_enabled = False
        client._last_pose = None

        pose = client.get_end_pose()

        self.assertEqual(pose[0], (0.3, 0.0, 0.3))
        sdk_client.acquire_control.assert_not_called()
        sdk_client.switch_controller.assert_not_called()

    def test_reads_joint_angles_without_enabling_control(self):
        client = AirbotArmClient.__new__(AirbotArmClient)
        sdk_client = mock.Mock()
        sdk_client.get_arm_joint_state.return_value = FakeJointState()
        client._client = sdk_client

        self.assertEqual(
            client.get_joint_angles(),
            (0.1, -0.2, 0.3, -0.1, 0.2, -0.3),
        )
        sdk_client.acquire_control.assert_not_called()

    def test_checks_ready_pose_without_enabling_control(self):
        client = AirbotArmClient.__new__(AirbotArmClient)
        sdk_client = mock.Mock()
        client._client = sdk_client

        sdk_client.get_arm_joint_state.return_value = FakeReadyJointState()
        self.assertTrue(client.is_at_ready_pose())

        sdk_client.get_arm_joint_state.return_value = FakeJointState()
        self.assertFalse(client.is_at_ready_pose())
        sdk_client.acquire_control.assert_not_called()

    def test_motion_requires_explicit_enable(self):
        client = AirbotArmClient.__new__(AirbotArmClient)
        client._client = mock.Mock()
        client._control_enabled = False
        client._last_pose = ((0.3, 0.0, 0.3), (0.0, 0.0, 0.5, -0.5))
        client._client.get_end_pose.return_value = None
        client._last_gripper = 0.036
        client._hold_pose = None
        client._hold_gripper = None
        client._hold_command_active = False
        client._last_command_rejected = False
        client._last_command_rejected = False
        client._client.get_eef_joint_state.return_value = FakeGripper()

        with self.assertRaisesRegex(RuntimeError, "explicitly enabled"):
            client.hold()

    def test_hold_is_sent_once_until_a_new_cartesian_target(self):
        client = AirbotArmClient.__new__(AirbotArmClient)
        sdk_client = mock.Mock()
        sdk_client.get_end_pose.return_value = FakePose()
        sdk_client.get_eef_joint_state.return_value = FakeGripper()
        client._client = sdk_client
        client._cartesian_pose_type = lambda position, orientation: (position, orientation)
        client._options_type = FakeOptions
        client._control_enabled = True
        client._last_pose = None
        client._last_gripper = None
        client._hold_pose = None
        client._hold_gripper = None
        client._hold_command_active = False
        client._last_command_rejected = False

        client.hold()
        client.hold()
        client.send_cartesian_pose((0.2, 0.0, 0.2), (0.0, 0.0, 0.0, 1.0), 0.036)
        client.hold()

        self.assertEqual(sdk_client.move_end_pose.call_count, 3)

    def test_repeated_pose_target_within_epsilon_is_not_resent(self):
        client = AirbotArmClient.__new__(AirbotArmClient)
        sdk_client = mock.Mock()
        sdk_client.get_end_pose.return_value = FakePose()
        sdk_client.get_eef_joint_state.return_value = FakeGripper()
        client._client = sdk_client
        client._cartesian_pose_type = lambda position, orientation: (position, orientation)
        client._options_type = FakeOptions
        client._control_enabled = True
        client._last_pose = None
        client._last_gripper = None
        client._hold_pose = None
        client._hold_gripper = None
        client._hold_command_active = False
        client._last_command_rejected = False

        client.hold()
        client.send_cartesian_pose(
            (0.3, 0.0, 0.3), (0.0, 0.0, 0.5, -0.5), 0.036
        )
        client.send_cartesian_pose(
            (0.3008, 0.0002, 0.3001), (0.0, 0.0, 0.5, -0.5), 0.036
        )
        client.send_cartesian_pose(
            (0.302, 0.0, 0.3), (0.0, 0.0, 0.55, -0.5), 0.036
        )

        self.assertEqual(sdk_client.move_end_pose.call_count, 2)

    def test_rejected_pose_keeps_last_accepted_target(self):
        client = AirbotArmClient.__new__(AirbotArmClient)
        sdk_client = mock.Mock()
        sdk_client.get_end_pose.return_value = FakePose()
        sdk_client.get_eef_joint_state.return_value = FakeGripper()
        sdk_client.move_end_pose.return_value = False
        client._client = sdk_client
        client._cartesian_pose_type = lambda position, orientation: (position, orientation)
        client._options_type = FakeOptions
        client._control_enabled = True
        client._last_pose = None
        client._last_gripper = 0.036
        client._hold_pose = ((0.3, 0.0, 0.3), (0.0, 0.0, 0.5, -0.5))
        client._hold_gripper = 0.036
        client._hold_command_active = True
        client._last_command_rejected = False
        client._rejected_at = None

        client.send_cartesian_pose((0.4, 0.0, 0.3), (0.0, 0.0, 0.0, 1.0), 0.02)

        self.assertTrue(client.last_command_rejected)
        self.assertEqual(client._hold_pose, ((0.3, 0.0, 0.3), (0.0, 0.0, 0.5, -0.5)))
        self.assertEqual(client._hold_gripper, 0.036)
        self.assertTrue(client._hold_command_active)

    def test_rejected_pose_is_retried_once_not_on_every_sample(self):
        client = AirbotArmClient.__new__(AirbotArmClient)
        sdk_client = mock.Mock()
        sdk_client.get_end_pose.return_value = FakePose()
        sdk_client.get_eef_joint_state.return_value = FakeGripper()
        sdk_client.move_end_pose.return_value = False
        client._client = sdk_client
        client._cartesian_pose_type = lambda position, orientation: (
            position,
            orientation,
        )
        client._options_type = FakeOptions
        client._control_enabled = True
        client._last_pose = None
        client._last_gripper = 0.036
        client._hold_pose = ((0.3, 0.0, 0.3), (0.0, 0.0, 0.0, 1.0))
        client._hold_gripper = 0.036
        client._hold_command_active = True
        client._last_command_rejected = False

        client.send_cartesian_pose((0.4, 0.0, 0.3), (0.0, 0.0, 0.0, 1.0), 0.02)
        client.send_cartesian_pose((0.5, 0.0, 0.3), (0.0, 0.0, 0.0, 1.0), 0.02)
        client.send_cartesian_pose((0.6, 0.0, 0.3), (0.0, 0.0, 0.0, 1.0), 0.02)
        self.assertEqual(sdk_client.move_end_pose.call_count, 1)

        client._rejected_at -= AirbotArmClient.REJECTED_POSE_RETRY_S
        client.recover_rejected_pose()
        self.assertEqual(sdk_client.move_end_pose.call_count, 2)
        self.assertTrue(client.last_command_rejected)

        client._rejected_at -= AirbotArmClient.REJECTED_POSE_RETRY_S
        client.recover_rejected_pose()
        self.assertEqual(sdk_client.move_end_pose.call_count, 3)

    def test_gripper_is_clamped(self):
        self.assertEqual(AirbotArmClient._clamped_gripper(-1.0), 0.0)
        self.assertEqual(AirbotArmClient._clamped_gripper(0.5), 0.072)
        self.assertEqual(AirbotArmClient.G2_GRIPPER_RANGE, (0.0, 0.072))

    def test_move_joint_preserves_current_gripper(self):
        client = AirbotArmClient.__new__(AirbotArmClient)
        client._client = mock.Mock()
        client._options_type = FakeOptions
        client._control_enabled = True
        client._last_gripper = 0.036

        self.assertTrue(
            client.move_joint((0.0, -0.45, 0.85, -0.75, 0.0, 0.0))
        )
        client._client.move_joint.assert_called_once_with(
            [0.0, -0.45, 0.85, -0.75, 0.0, 0.0],
            FakeOptions.last,
            timeout_ms=5000,
        )
        self.assertEqual(FakeOptions.last.eef_pos, 0.036)

    def test_blocking_joint_move_clears_stale_cartesian_hold(self):
        client = AirbotArmClient.__new__(AirbotArmClient)
        client._client = mock.Mock()
        client._options_type = FakeOptions
        client._control_enabled = True
        client._last_gripper = 0.036
        client._hold_pose = ((0.3, 0.0, 0.3), (0.0, 0.0, 0.0, 1.0))
        client._hold_gripper = 0.036
        client._hold_command_active = True

        self.assertTrue(
            client.move_joint(
                (0.0, -0.45, 0.85, -0.75, -0.5, math.pi / 2.0),
                blocking=True,
                timeout_ms=5000,
            )
        )
        self.assertTrue(FakeOptions.last.blocking)
        self.assertIsNone(client._hold_pose)
        self.assertFalse(client._hold_command_active)

    def test_move_joint_reads_gripper_when_no_previous_target(self):
        client = AirbotArmClient.__new__(AirbotArmClient)
        client._client = mock.Mock()
        client._options_type = FakeOptions
        client._control_enabled = True
        client._last_gripper = None
        client._client.get_eef_joint_state.return_value = FakeGripper()

        self.assertTrue(client.move_joint((0.0, -0.45, 0.85, -0.75, 0.0, 0.0)))
        self.assertEqual(FakeOptions.last.eef_pos, 0.036)


if __name__ == "__main__":
    unittest.main()
