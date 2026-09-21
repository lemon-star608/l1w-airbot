import json
import socket
import time
import unittest

from l1w_teleop.dog.udp import DogStatus, L1WUdpStatusMonitor
from l1w_teleop.telemetry import TelelemetryPublisher, arm_telemetry, dog_telemetry


class TelemetryTests(unittest.TestCase):
    def test_dog_monitor_extracts_motion_feedback(self):
        monitor = L1WUdpStatusMonitor(
            host="127.0.0.1", command_port=38081, receive_port=38080
        )
        try:
            monitor._absorb({"type": "imu_info", "quat": [0, 0, 0, 1]})
            monitor._absorb({"type": "odom_info", "position": [1, 2, 3]})
            monitor._absorb(
                {"type": "leg_joint_info", "angles": list(range(16))}
            )
            monitor._absorb(
                {
                    "type": "leg_joint_info",
                    "lf": {"angles": [0, 1, 2, 3]},
                    "rf": {"angles": [4, 5, 6, 7]},
                    "lr": {"angles": [8, 9, 10, 11]},
                    "rr": {"angles": [12, 13, 14, 15]},
                }
            )
            monitor._absorb(
                {
                    "type": "leg_joint_info",
                    "leg_joint_info": {
                        "leg_abad_joint": [0.1, 0.2, 0.3, 0.4],
                        "leg_hip_joint": [1.1, 1.2, 1.3, 1.4],
                        "leg_knee_joint": [2.1, 2.2, 2.3, 2.4],
                        "leg_foot_joint": [3.1, 3.2, 3.3, 3.4],
                    },
                }
            )
            status = monitor.status()
            self.assertEqual(status.imu_wxyz, (0.0, 0.0, 0.0, 1.0))
            self.assertEqual(status.odom_xyz, (1.0, 2.0, 3.0))
            self.assertEqual(
                status.leg_joints,
                (
                    0.1, 1.1, 2.1, 3.1,
                    0.2, 1.2, 2.2, 3.2,
                    0.3, 1.3, 2.3, 3.3,
                    0.4, 1.4, 2.4, 3.4,
                ),
            )
        finally:
            monitor.close()

    def test_publisher_sends_udp_and_tcp_json(self):
        publisher = TelelemetryPublisher(
            udp_host="127.0.0.1",
            udp_port=39999,
            tcp_host="127.0.0.1",
            tcp_port=39998,
            queue_seconds=0.01,
        )
        client = socket.create_connection(("127.0.0.1", 39998), timeout=1)
        client.settimeout(1)
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.bind(("127.0.0.1", 39999))
        udp.settimeout(1)
        try:
            payload = {
                "schema": 1,
                "timestamp_ns": time.time_ns(),
                "input": {"healthy": True, "motion_mode": "motion"},
                "dog": dog_telemetry(
                    DogStatus(connected=True, leg_joints=tuple(range(16)))
                ),
                "arm": arm_telemetry(
                    True,
                    (0.1, 0.2, 0.3, 0.4, 0.5, 0.6),
                    0.072,
                    ((0.3, 0.0, 0.3), (0.0, 0.0, 0.0, 1.0)),
                ),
            }
            publisher.publish(payload)
            tcp_packet = client.recv(65536)
            self.assertTrue(tcp_packet.endswith(b"\n"))
            decoded_tcp = json.loads(tcp_packet)
            udp_packet, _ = udp.recvfrom(65536)
            decoded_udp = json.loads(udp_packet)
            self.assertEqual(decoded_tcp, decoded_udp)
            self.assertEqual(
                decoded_tcp["arm"]["joint_angles_rad"],
                [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
            )
            self.assertEqual(
                decoded_tcp["dog"]["feedback"]["leg_joints_rad"],
                list(range(16)),
            )
        finally:
            client.close()
            udp.close()
            publisher.close()


if __name__ == "__main__":
    unittest.main()
