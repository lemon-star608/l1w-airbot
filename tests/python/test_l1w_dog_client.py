import unittest
from unittest import mock

from l1w_teleop.dog.l1w import L1WDogClient
from l1w_teleop.dog.udp import DogStatus


def make_client(**kwargs):
    client = L1WDogClient.__new__(L1WDogClient)
    client.monitor = mock.Mock()
    status = {
        "connected": True,
        "control_mode": "rl",
        "forward_mps": 0.0,
        "lateral_mps": 0.0,
        "yaw_rate_rps": 0.0,
        **kwargs,
    }
    client.monitor.status.return_value = DogStatus(**status)
    client._balance_settle_ns = 1_000_000_000
    client._balance_linear_tolerance = 0.08
    client._balance_yaw_tolerance = 0.12
    client._state = "inactive"
    client._move_mode_sent = False
    client._zero_since_ns = None
    return client


class L1WDogClientTests(unittest.TestCase):
    def test_stand_waits_for_rl_and_three_axis_zero_before_balance(self):
        dog = make_client(control_mode="emergency")
        dog.set_mode("stand_up")
        dog.update()
        self.assertEqual(dog.state, "standing")

        dog.monitor.status.return_value = DogStatus(
            connected=True,
            control_mode="rl",
            forward_mps=0.0,
            lateral_mps=0.0,
            yaw_rate_rps=0.0,
        )
        dog.update()
        self.assertEqual(dog.state, "settling")
        dog.send_command(0.0, 0.0, 0.0)
        self.assertEqual(dog.state, "settling")
        self.assertEqual(dog.monitor.send_balance_stand_mode.call_count, 0)

        dog._zero_since_ns -= 1_000_000_001
        dog.send_zero()
        dog.monitor.status.return_value = DogStatus(
            connected=True,
            control_mode="rl",
            forward_mps=0.0,
            lateral_mps=0.0,
            yaw_rate_rps=0.0,
        )
        dog.send_zero()
        self.assertEqual(dog.state, "balance")

    def test_balance_is_sent_once_after_zero_window(self):
        dog = make_client()
        dog.set_mode("stand_up")
        dog.update()
        dog._zero_since_ns -= 1_000_000_001
        dog.send_zero()
        self.assertEqual(dog.monitor.send_balance_stand_mode.call_count, 1)

        dog.send_zero()
        self.assertEqual(dog.monitor.send_balance_stand_mode.call_count, 1)

    def test_nonzero_rotation_sends_move_mode_then_remote(self):
        dog = make_client()
        dog.set_mode("stand_up")
        dog.update()
        dog._zero_since_ns -= 1_000_000_001
        dog.send_zero()
        dog.monitor.status.return_value = DogStatus(
            connected=True,
            control_mode="rl",
            forward_mps=0.0,
            lateral_mps=0.0,
            yaw_rate_rps=0.0,
        )
        dog.send_zero()
        self.assertEqual(dog.state, "balance")

        dog.send_command(0.0, 0.2, 0.0)
        self.assertEqual(dog.state, "moving")
        self.assertEqual(dog.monitor.send_move_mode.call_count, 1)
        dog.monitor.send_nonzero_remote.assert_called_once_with(0.0, 0.2, 0.0)

    def test_balance_requires_rl_feedback(self):
        dog = make_client(control_mode="emergency")
        dog.set_mode("stand_up")
        dog._zero_since_ns -= 1_000_000_001
        dog.send_zero()
        self.assertEqual(dog.monitor.send_balance_stand_mode.call_count, 0)

    def test_feedback_loss_blocks_stand_and_balance_transitions(self):
        dog = make_client(control_mode="rl")
        dog.set_mode("stand_up")
        dog.monitor.status.return_value = DogStatus(
            connected=False,
            control_mode="rl",
            forward_mps=0.0,
            lateral_mps=0.0,
            yaw_rate_rps=0.0,
        )
        dog.update()
        self.assertEqual(dog.state, "standing")

        dog._zero_since_ns -= 1_000_000_001
        dog.update()
        self.assertEqual(dog.state, "standing")
        self.assertEqual(dog.monitor.send_balance_stand_mode.call_count, 0)

    def test_balance_requires_measured_linear_and_yaw_stop(self):
        dog = make_client(
            forward_mps=0.01,
            lateral_mps=0.01,
            yaw_rate_rps=0.20,
        )
        dog.set_mode("stand_up")
        dog._zero_since_ns -= 1_000_000_001
        dog.send_zero()
        self.assertEqual(dog.monitor.send_balance_stand_mode.call_count, 0)

    def test_moving_to_stop_sends_one_zero_then_balance(self):
        dog = make_client()
        dog.set_mode("stand_up")
        dog.update()
        dog.send_command(0.1, 0.0, 0.0)
        self.assertEqual(dog.state, "moving")

        dog.send_zero()
        self.assertEqual(dog.state, "settling")
        self.assertEqual(dog.monitor.send_remote_zero.call_count, 2)
        dog.send_zero()
        self.assertEqual(dog.monitor.send_remote_zero.call_count, 2)

        dog._zero_since_ns -= 1_000_000_001
        dog.send_zero()
        dog.monitor.status.return_value = DogStatus(
            connected=True,
            control_mode="rl",
            forward_mps=0.0,
            lateral_mps=0.0,
            yaw_rate_rps=0.0,
        )
        dog.send_zero()
        self.assertEqual(dog.state, "balance")
        self.assertEqual(dog.monitor.send_balance_stand_mode.call_count, 1)

    def test_balance_to_moving_sends_move_mode_once_then_remote(self):
        dog = make_client()
        dog.set_mode("stand_up")
        dog.update()
        dog._zero_since_ns -= 1_000_000_001
        dog.send_zero()
        self.assertEqual(dog.state, "balance")

        dog.send_command(0.1, 0.0, 0.0)
        self.assertEqual(dog.state, "moving")
        self.assertEqual(dog.monitor.send_move_mode.call_count, 1)
        dog.monitor.send_nonzero_remote.assert_called_once_with(0.1, 0.0, 0.0)

    def test_damping_uses_emergency_and_returns_inactive(self):
        dog = make_client()
        dog.set_mode("damping")
        self.assertEqual(dog.state, "inactive")
        self.assertEqual(dog.monitor.send_emergency_stop.call_count, 1)

        dog.send_command(0.1, 0.0, 0.0)
        dog.send_zero()
        self.assertEqual(dog.monitor.send_remote.call_count, 0)
        self.assertEqual(dog.monitor.send_remote_zero.call_count, 0)


if __name__ == "__main__":
    unittest.main()
