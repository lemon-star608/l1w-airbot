import unittest
import threading
from unittest import mock

from l1w_teleop.control import InputMapping, MappingConfig
from l1w_teleop.dog.udp import (
    DogStatus,
    L1WCommandStatistics,
    L1WUdpStatusMonitor,
    _firmware_joystick,
)
from l1w_teleop.input.models import ControllerFrame, TeleopInputs


class L1WUdpStatusMonitorTests(unittest.TestCase):
    def test_physical_joystick_directions_map_to_firmware_actions(self):
        mapping = InputMapping(MappingConfig(deadzone=0.1))

        def joystick(left_axis=(0.0, 0.0), right_axis=(0.0, 0.0)):
            left = ControllerFrame(
                local_monotonic_ns=0,
                sdk_timestamp_ns=0,
                pose=(0.0,) * 7,
                grip=0.0,
                trigger=1.0,
                axis=left_axis,
                buttons=(True, False),
            )
            right = ControllerFrame(
                local_monotonic_ns=0,
                sdk_timestamp_ns=0,
                pose=(0.0,) * 7,
                grip=0.0,
                trigger=0.0,
                axis=right_axis,
            )
            command = mapping.map(TeleopInputs(left=left, right=right)).dog
            return _firmware_joystick(
                command.forward, command.rotate, command.lateral
            )

        # PICO reports negative Y for forward and negative X for left.
        self.assertEqual(joystick(left_axis=(0.0, -1.0)), (0.0, 0.5, 0.0, 0.0))
        self.assertEqual(joystick(left_axis=(-1.0, 0.0)), (-0.3, 0.0, 0.0, 0.0))
        self.assertEqual(joystick(right_axis=(-1.0, 0.0)), (0.0, 0.0, -0.5, 0.0))

    def test_absorbs_core_state_without_control_messages(self):
        monitor = L1WUdpStatusMonitor.__new__(L1WUdpStatusMonitor)
        monitor._stale_after_ns = 1_000_000_000
        monitor._status = DogStatus()
        monitor._command_statistics = L1WCommandStatistics()
        monitor._lock = threading.Lock()

        monitor._absorb(
            {
                "type": "dog_state",
                "power": 34,
                "temp": 58.2,
                "speed": -0.001,
                "shift_speed": 0.002,
                "angle_speed": -0.003,
            }
        )
        monitor._absorb(
            {
                "type": "dev_info",
                "battery": {"volt": 43.12, "current": -1.64, "power": 34},
            }
        )
        monitor._absorb(
            {
                "type": "feedback",
                "function": "sdk",
                "control_mode": "emergency",
                "motion_mode": "forbid",
            }
        )
        monitor._absorb(
            {
                "type": "fault_info",
                "faults": [{"level": "warn"}, {"level": "warn"}],
            }
        )

        status = monitor.status()
        self.assertTrue(status.connected)
        self.assertEqual(status.power_percent, 34)
        self.assertAlmostEqual(status.voltage_v, 43.120)
        self.assertAlmostEqual(status.current_a, -1.640)
        self.assertEqual(status.function_mode, "sdk")
        self.assertEqual(status.control_mode, "emergency")
        self.assertEqual(status.motion_mode, "forbid")
        self.assertEqual(status.fault_count, 2)

        monitor._absorb({"type": "speed_set", "level": 2})
        self.assertEqual(monitor.status().speed_level, "normal")

    def test_zero_control_messages_are_bounded(self):
        monitor = L1WUdpStatusMonitor.__new__(L1WUdpStatusMonitor)
        monitor._host = "192.168.234.1"
        monitor._command_port = 8081
        monitor._socket = mock.Mock()
        monitor._command_statistics = L1WCommandStatistics()
        monitor._lock = threading.Lock()

        monitor.send_sdk_control_request()
        monitor.send_stand_up()
        monitor.send_move_mode()
        monitor.send_balance_stand_mode()
        monitor.send_nonzero_remote(0.5, 0.2, 0.3)
        monitor.send_remote_zero()
        monitor.send_emergency_stop()

        messages = [call.args[0] for call in monitor._socket.sendto.call_args_list]
        self.assertEqual(messages[0], b'{"type": "cmd", "role": "sdk", "cmd": 179}')
        self.assertEqual(messages[1], b'{"type": "cmd", "role": "sdk", "cmd": 122}')
        self.assertEqual(messages[2], b'{"type": "cmd", "role": "sdk", "cmd": 138}')
        self.assertEqual(messages[3], b'{"type": "cmd", "role": "sdk", "cmd": 154}')
        self.assertIn(b'"joystick": [-0.3, 0.5, -0.2, 0.0]', messages[4])
        self.assertIn(b'"joystick": [0.0, 0.0, 0.0, 0.0]', messages[5])
        self.assertIn(b'"button": [0.0', messages[4])
        self.assertEqual(messages[6], b'{"type": "cmd", "role": "sdk", "cmd": 90}')

        statistics = monitor.command_statistics()
        self.assertEqual(statistics.sent_sdk_control, 1)
        self.assertEqual(statistics.sent_move_mode, 1)
        self.assertEqual(statistics.sent_remote, 2)
        self.assertEqual(statistics.sent_remote_zero, 1)


if __name__ == "__main__":
    unittest.main()
