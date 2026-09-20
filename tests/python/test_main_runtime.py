import unittest
from argparse import Namespace
from unittest import mock

from l1w_teleop import main
from l1w_teleop.control.models import ArmCommand, DogCommand, RobotCommands


def runtime_args(**overrides):
    values = {
        "source": "xrt",
        "rate": 50.0,
        "duration": 0.0,
        "stale_after": 0.30,
        "print_every": 10,
        "command_mode": "hardware",
        "arm_mode": "pose",
        "arm_backend": "airbot",
        "arm_host": "localhost",
        "arm_port": 50051,
        "dog_backend": "l1w",
        "dog_host": "192.168.234.1",
        "dog_command_port": 8081,
        "dog_receive_port": 8080,
        "startup_hold": 2.0,
        "dog_balance_settle": 1.0,
        "dog_forward_scale": 0.50,
        "dog_lateral_scale": 0.30,
        "dog_rotate_scale": 0.50,
        "arm_pose_scale": 1.0,
        "lock_arm_orientation": True,
        "i_understand_this_will_move_the_airbot": True,
        "i_understand_this_will_control_the_dog": True,
    }
    values.update(overrides)
    return Namespace(**values)


class MainRuntimeTests(unittest.TestCase):
    def test_hardware_real_dog_requires_confirmed_real_arm(self):
        with mock.patch.object(main, "L1WDogClient") as client:
            main._make_dog_client(runtime_args())
            client.assert_called_once()

        with self.assertRaisesRegex(RuntimeError, "confirmed AIRBOT"):
            main._make_dog_client(
                runtime_args(i_understand_this_will_move_the_airbot=False)
            )

    def test_hardware_mapping_stops_dog_while_arm_tracks(self):
        config = main._mapping_config(runtime_args())
        self.assertTrue(config.arm_motion_stops_dog)
        self.assertFalse(config.allow_return_zero)

    def test_hardware_dispatch_stops_dog_before_sending_arm_target(self):
        dog = mock.Mock()
        arm = mock.Mock()
        calls = []
        dog.send_zero.side_effect = lambda: calls.append("dog")
        arm.send_cartesian_pose.side_effect = lambda *args: calls.append("arm")
        commands = RobotCommands(
            dog=DogCommand(0.2, 0.0, 0.0, enabled=False),
            arm=ArmCommand(
                position=(0.3, 0.0, 0.3),
                orientation=(0.0, 0.0, 0.0, 1.0),
                gripper=0.036,
                enabled=True,
                mode="pose",
            ),
        )

        main._dispatch(dog, arm, commands, "hardware")

        dog.send_zero.assert_called_once_with()
        arm.send_cartesian_pose.assert_called_once_with(
            (0.3, 0.0, 0.3), (0.0, 0.0, 0.0, 1.0), 0.036
        )
        self.assertEqual(calls, ["dog", "arm"])

    def test_hardware_damping_transition_commands_dog_damping(self):
        dog = mock.Mock()
        arm = mock.Mock()
        commands = RobotCommands(
            dog_mode_command="damping",
            arm=ArmCommand(enabled=False),
        )

        main._dispatch(dog, arm, commands, "hardware")

        dog.set_mode.assert_called_once_with("damping")
        dog.send_zero.assert_called_once_with()
        arm.hold.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
