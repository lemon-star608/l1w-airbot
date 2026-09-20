import unittest

from l1w_teleop.input import PicoInputMonitor
from l1w_teleop.input.monitor import SourceState


class StaticSource:
    def __init__(self):
        self.state = SourceState(timestamp_ns=100)

    def read(self):
        return self.state


class InputMonitorTests(unittest.TestCase):
    def test_first_sample_is_ok_and_repeat_is_stale(self):
        source = StaticSource()
        monitor = PicoInputMonitor(source, stale_after_s=0.0)
        _, stale = monitor.read()
        self.assertFalse(stale)
        _, stale = monitor.read()
        self.assertTrue(stale)

    def test_nonfinite_sample_becomes_safe_and_stale(self):
        source = StaticSource()
        source.state = SourceState(
            timestamp_ns=200,
            left_pose=(float("nan"), 0, 0, 0, 0, 0, 1),
            right_pose=(0, 0, 0, 0, 0, 0, 1),
        )
        monitor = PicoInputMonitor(source)
        inputs, stale = monitor.read()
        self.assertTrue(stale)
        self.assertEqual(inputs.left.pose, (0.0,) * 7)
        self.assertEqual(inputs.left.grip, 0.0)


if __name__ == "__main__":
    unittest.main()
