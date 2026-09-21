import json
import socket
import threading
import time


class TelelemetryPublisher:
    """Publishes the same telemetry object over UDP and newline-delimited TCP."""

    SCHEMA = 1

    def __init__(
        self,
        udp_host=None,
        udp_port=8766,
        tcp_host="0.0.0.0",
        tcp_port=9766,
        queue_seconds=0.2,
    ):
        self._udp_address = (
            (udp_host, int(udp_port)) if udp_host and int(udp_port) > 0 else None
        )
        self._tcp_address = (
            (tcp_host, int(tcp_port)) if tcp_host and int(tcp_port) > 0 else None
        )
        self._queue_seconds = queue_seconds
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setblocking(False)
        self._tcp_socket = None
        self._clients = []
        self._clients_lock = threading.Lock()
        self._pending = None
        self._pending_lock = threading.Lock()
        self._running = True
        self._thread = threading.Thread(target=self._run, name="telemetry", daemon=True)
        self._start_tcp_server()
        self._thread.start()

    def publish(self, telemetry: dict) -> None:
        payload = telemetry.copy()
        payload.setdefault("schema", self.SCHEMA)
        payload.setdefault("timestamp_ns", time.time_ns())
        encoded = json.dumps(payload, separators=(",", ":"), allow_nan=False).encode()
        with self._pending_lock:
            self._pending = encoded

    def close(self) -> None:
        self._running = False
        self._thread.join(timeout=1.0)
        with self._clients_lock:
            clients = list(self._clients)
            self._clients.clear()
        for client in clients:
            self._close_client(client)
        if self._tcp_socket is not None:
            try:
                self._tcp_socket.close()
            except OSError:
                pass
        try:
            self._socket.close()
        except OSError:
            pass

    def _start_tcp_server(self) -> None:
        if self._tcp_address is None:
            return
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(self._tcp_address)
        server.listen(4)
        server.settimeout(0.1)
        self._tcp_socket = server

    def _run(self) -> None:
        next_send = time.monotonic()
        while self._running:
            now = time.monotonic()
            if now < next_send:
                time.sleep(min(0.002, next_send - now))
                continue
            next_send = now + self._queue_seconds
            with self._pending_lock:
                encoded = self._pending
                self._pending = None
            if encoded is None:
                self._accept_tcp_clients()
                continue
            self._send_udp(encoded)
            self._accept_tcp_clients()
            self._send_tcp(encoded)

    def _accept_tcp_clients(self) -> None:
        if self._tcp_socket is None:
            return
        while True:
            try:
                client, _ = self._tcp_socket.accept()
            except socket.timeout:
                return
            except OSError:
                return
            client.setblocking(False)
            with self._clients_lock:
                self._clients.append(client)

    def _send_udp(self, encoded: bytes) -> None:
        if self._udp_address is None:
            return
        try:
            self._socket.sendto(encoded, self._udp_address)
        except (OSError, BlockingIOError):
            pass

    def _send_tcp(self, encoded: bytes) -> None:
        if not self._clients:
            return
        packet = encoded + b"\n"
        with self._clients_lock:
            clients = list(self._clients)
        alive = []
        for client in clients:
            try:
                client.sendall(packet)
                alive.append(client)
            except (OSError, BlockingIOError):
                self._close_client(client)
        with self._clients_lock:
            self._clients[:] = alive

    @staticmethod
    def _close_client(client) -> None:
        try:
            client.close()
        except OSError:
            pass


def dog_telemetry(status, joint_info=None) -> dict:
    connected = bool(status is not None and status.connected)
    legs = getattr(status, "leg_joints", None) if status is not None else None
    return {
        "connected": connected,
        "fsm": getattr(status, "function_mode", None) or "-",
        "blocked_reason": "",
        "battery_percent": getattr(status, "power_percent", None),
        "feedback": {
            "imu_quaternion_wxyz": getattr(status, "imu_wxyz", None)
            or (1.0, 0.0, 0.0, 0.0),
            "odom_position_xyz": getattr(status, "odom_xyz", None)
            or (0.0, 0.0, 0.32),
            "leg_joints_rad": legs,
            "leg_source": "leg_joint_info" if legs is not None else "-",
            "odom_source": "odom_info+imu_info" if connected else "-",
            "forward_mps": getattr(status, "forward_mps", None) or 0.0,
            "lateral_mps": getattr(status, "lateral_mps", None) or 0.0,
            "yaw_rate_rps": getattr(status, "yaw_rate_rps", None) or 0.0,
        },
    }


def arm_telemetry(connected, joints, gripper, end_pose) -> dict:
    position, orientation = end_pose or ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0))
    return {
        "connected": connected,
        "joint_angles_rad": list(joints or (0.0, 0.0, 0.0, 1.6, 0.0, -1.6)),
        "gripper_m": gripper if gripper is not None else 0.036,
        "end_pose": {
            "position_xyz": list(position),
            "orientation_xyzw": list(orientation),
        },
    }
