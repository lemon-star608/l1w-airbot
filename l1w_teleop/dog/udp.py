import json
import math
import socket
import threading
import time
from dataclasses import dataclass, replace
from typing import Optional, Tuple

from .interface import DogStatusMonitor


SPEED_LEVELS = {
    0: "null",
    1: "slow",
    2: "normal",
    3: "fast",
}


def _firmware_joystick(
    forward: float, rotate: float, lateral: float
) -> Tuple[float, float, float, float]:
    """Convert robot-frame commands to dog_task's calibrated joystick order.

    Firmware order is [lateral, forward, rotate, head]. Positive firmware
    lateral, forward, and rotate mean right translation, forward motion, and
    right turn. Normalized commands use positive forward/left/left.
    """
    return (-lateral, forward, -rotate, 0.0)


@dataclass(frozen=True)
class DogStatus:
    connected: bool = False
    last_update_s: float = 0.0
    power_percent: Optional[int] = None
    voltage_v: Optional[float] = None
    current_a: Optional[float] = None
    temperature_c: Optional[float] = None
    function_mode: Optional[str] = None
    control_mode: Optional[str] = None
    motion_mode: Optional[str] = None
    forward_mps: Optional[float] = None
    lateral_mps: Optional[float] = None
    yaw_rate_rps: Optional[float] = None
    fault_count: Optional[int] = None
    speed_level: Optional[str] = None


@dataclass(frozen=True)
class L1WCommandStatistics:
    sent_sdk_control: int = 0
    sent_move_mode: int = 0
    sent_remote: int = 0
    sent_remote_zero: int = 0


class L1WUdpStatusMonitor(DogStatusMonitor):
    """Reads the documented L1-W UDP JSON stream.

    It sends only heartbeat packets. It does not request SDK control rights,
    send remote commands, or change posture.
    """

    def __init__(
        self,
        host: str = "192.168.234.1",
        command_port: int = 8081,
        receive_port: int = 8080,
        stale_after_s: float = 1.0,
        heartbeat_period_s: float = 0.05,
    ):
        self._host = host
        self._command_port = command_port
        self._stale_after_ns = int(stale_after_s * 1_000_000_000)
        self._heartbeat_period_s = heartbeat_period_s
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind(("0.0.0.0", receive_port))
        self._socket.settimeout(0.1)
        self._lock = threading.Lock()
        self._status = DogStatus()
        self._command_statistics = L1WCommandStatistics()
        self._running = True
        self._thread = threading.Thread(target=self._run, name="l1w-status", daemon=True)
        self._thread.start()

    def status(self) -> Optional[DogStatus]:
        with self._lock:
            return self._status

    def command_statistics(self) -> L1WCommandStatistics:
        with self._lock:
            return self._command_statistics

    def close(self) -> None:
        self._running = False
        self._thread.join(timeout=1.0)
        self._socket.close()

    def send_sdk_control_request(self) -> None:
        self._send_command(0xB3)
        self._increment_statistic("sent_sdk_control")

    def send_remote_zero(self) -> None:
        self._send_remote((0.0, 0.0, 0.0, 0.0))

    def send_remote(self, joystick: Tuple[float, float, float, float]) -> None:
        self._send_remote(joystick)

    def send_nonzero_remote(
        self, forward: float, rotate: float, lateral: float
    ) -> None:
        self._send_remote(_firmware_joystick(forward, rotate, lateral))

    def send_stand_up(self) -> None:
        self._send_command(0x7A)

    def send_move_mode(self) -> None:
        self._send_command(0x8A)
        self._increment_statistic("sent_move_mode")

    def send_balance_stand_mode(self) -> None:
        self._send_command(0x9A)

    def send_emergency_stop(self) -> None:
        self._send_command(0x5A)

    def _send_command(self, command: int) -> None:
        message = json.dumps(
            {"type": "cmd", "role": "sdk", "cmd": command}
        ).encode()
        try:
            self._socket.sendto(message, (self._host, self._command_port))
        except OSError as error:
            raise RuntimeError(f"failed to send L1-W command: {error}") from error

    def _send_remote(self, joystick: Tuple[float, float, float, float]) -> None:
        message = json.dumps(
            {
                "type": "remote",
                "role": "sdk",
                "joystick": list(joystick),
                "button": [0.0] * 14,
            }
        ).encode()
        try:
            self._socket.sendto(message, (self._host, self._command_port))
        except OSError as error:
            raise RuntimeError(f"failed to send L1-W remote command: {error}") from error
        self._increment_statistic("sent_remote")
        if not any(joystick):
            self._increment_statistic("sent_remote_zero")

    def _increment_statistic(self, name: str) -> None:
        with self._lock:
            value = getattr(self._command_statistics, name)
            self._command_statistics = replace(
                self._command_statistics,
                **{name: value + 1},
            )

    def _run(self) -> None:
        while self._running:
            self._send_heartbeat()
            deadline = time.monotonic() + self._heartbeat_period_s
            while self._running and time.monotonic() < deadline:
                try:
                    data, _ = self._socket.recvfrom(65536)
                except socket.timeout:
                    continue
                try:
                    message = json.loads(data)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                self._absorb(message)

    def _send_heartbeat(self) -> None:
        message = json.dumps({"type": "heartbeat", "role": "sdk"}).encode()
        try:
            self._socket.sendto(message, (self._host, self._command_port))
        except OSError:
            pass

    def _absorb(self, message: dict) -> None:
        message_type = message.get("type")
        with self._lock:
            status = self._status
            changed = {}
            if message_type == "dog_state":
                changed = {
                    "power_percent": _optional_int(message.get("power")),
                    "temperature_c": _optional_float(message.get("temp")),
                    "forward_mps": _optional_float(message.get("speed")),
                    "lateral_mps": _optional_float(message.get("shift_speed")),
                    "yaw_rate_rps": _optional_float(message.get("angle_speed")),
                }
            elif message_type == "dev_info":
                battery = message.get("battery") or {}
                changed = {
                    "voltage_v": _optional_float(battery.get("volt")),
                    "current_a": _optional_float(battery.get("current")),
                    "power_percent": _optional_int(battery.get("power")),
                }
            elif message_type == "feedback":
                changed = {
                    "function_mode": message.get("function"),
                    "control_mode": message.get("control_mode"),
                    "motion_mode": message.get("motion_mode"),
                }
            elif message_type == "speed_set":
                changed = {
                    "speed_level": _speed_level(message.get("level")),
                }
            elif message_type == "fault_info":
                faults = message.get("faults")
                if isinstance(faults, list):
                    changed = {"fault_count": len(faults)}

            now = time.monotonic()
            connected = (
                True
                if status.last_update_s == 0.0
                else now - status.last_update_s <= self._stale_after_ns / 1e9
            )
            self._status = DogStatus(
                **{
                    **status.__dict__,
                    **changed,
                    "last_update_s": now,
                    "connected": connected,
                }
            )


def _speed_level(value) -> Optional[str]:
    if value in SPEED_LEVELS:
        return SPEED_LEVELS[value]
    return _optional_str(value)


def _optional_str(value) -> Optional[str]:
    return value if isinstance(value, str) else None


def _optional_float(value) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _optional_int(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _scale(value: Optional[float], factor: float) -> Optional[float]:
    return value * factor if value is not None else None
