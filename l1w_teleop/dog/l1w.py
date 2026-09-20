import time

from .interface import DogClient
from .udp import L1WUdpStatusMonitor


class L1WDogClient(DogClient):
    """L1-W SDK client mirroring the remote-control task's packet cadence."""

    def __init__(
        self,
        host: str = "192.168.234.1",
        command_port: int = 8081,
        receive_port: int = 8080,
        balance_settle_s: float = 1.0,
        balance_linear_tolerance: float = 0.08,
        balance_yaw_tolerance: float = 0.12,
    ):
        self.monitor = L1WUdpStatusMonitor(
            host=host,
            command_port=command_port,
            receive_port=receive_port,
        )
        self._balance_settle_ns = int(balance_settle_s * 1_000_000_000)
        self._balance_linear_tolerance = balance_linear_tolerance
        self._balance_yaw_tolerance = balance_yaw_tolerance
        self._state = "inactive"
        self._move_mode_sent = False
        self._zero_since_ns = None
        self._blocked_reason = ""

    def update(self) -> None:
        """Advance state transitions that do not require a new remote packet."""
        if self._state != "standing":
            return
        if not self._feedback_healthy():
            self._blocked_reason = "waiting for connected feedback"
            return
        status = self.monitor.status()
        if self._ready_controller():
            self._state = "settling"
            self._zero_since_ns = time.monotonic_ns()
            self._blocked_reason = "waiting to settle before balance"
        else:
            self._blocked_reason = (
                self._controller_block_reason(status.control_mode)
                or "waiting for rl/balance feedback"
            )

    @property
    def state(self) -> str:
        return self._state

    @property
    def blocked_reason(self) -> str:
        return self._blocked_reason

    def send_zero(self) -> None:
        if self._state in {"inactive", "standing", "balance"}:
            self._blocked_reason = "" if self._state != "standing" else self._blocked_reason
            return

        if self._state == "settling":
            self._blocked_reason = self._settling_block_reason()
            self._maybe_enter_balance()
            return

        # Official dog_task sends one stop packet, then waits for the robot to
        # settle instead of continuously publishing zero velocity.
        self.monitor.send_remote_zero()
        self._state = "settling"
        self._zero_since_ns = time.monotonic_ns()
        self._blocked_reason = self._settling_block_reason()

    def send_command(self, forward: float, rotate: float, lateral: float) -> None:
        if self._state in {"inactive", "standing"}:
            return
        if forward == 0.0 and rotate == 0.0 and lateral == 0.0:
            self.send_zero()
            return

        if self._state == "balance" or not self._move_mode_sent:
            # Official SDK examples send SetRemote directly after SDK control.
            # CMD_MOVE_MODE is sent once as the native mode request, but this
            # firmware may continue reporting its RL controller while moving.
            self.monitor.send_move_mode()
            self._move_mode_sent = True

        self._zero_since_ns = None
        self._state = "moving"
        self._blocked_reason = ""
        self.monitor.send_nonzero_remote(forward, rotate, lateral)

    def set_mode(self, mode: str) -> None:
        if mode == "stand_up":
            self.monitor.send_sdk_control_request()
            # Match the validated stand-balance bring-up sequence.
            time.sleep(0.2)
            self.monitor.send_remote_zero()
            time.sleep(0.2)
            self.monitor.send_stand_up()
            self._state = "standing"
            self._move_mode_sent = False
            self._zero_since_ns = time.monotonic_ns()
            self._blocked_reason = "waiting for rl/balance feedback"
        elif mode == "damping":
            self.monitor.send_emergency_stop()
            self._state = "inactive"
            self._move_mode_sent = False
            self._zero_since_ns = None
            self._blocked_reason = ""
        else:
            raise ValueError("mode must be stand_up or damping")

    def close(self) -> None:
        self.monitor.close()

    def _maybe_enter_balance(self) -> None:
        if self._state != "settling" or self._zero_since_ns is None:
            return
        settled = time.monotonic_ns() - self._zero_since_ns
        if settled < self._balance_settle_ns:
            return
        if not self._feedback_healthy():
            return
        if not self._ready_for_balance():
            return
        self.monitor.send_balance_stand_mode()
        self._state = "balance"
        self._move_mode_sent = False
        self._blocked_reason = ""

    def _settling_block_reason(self) -> str:
        if self._zero_since_ns is None:
            return "missing zero-window timestamp"
        elapsed_s = (time.monotonic_ns() - self._zero_since_ns) / 1_000_000_000
        if elapsed_s < self._balance_settle_ns / 1_000_000_000:
            return f"zero window {elapsed_s:.2f}s"
        if not self._feedback_healthy():
            return "waiting for connected feedback"
        status = self.monitor.status()
        reason = self._controller_block_reason(status.control_mode)
        speeds = (
            status.forward_mps,
            status.lateral_mps,
            status.yaw_rate_rps,
        )
        for name, value, tolerance in (
            ("vx", status.forward_mps, self._balance_linear_tolerance),
            ("vy", status.lateral_mps, self._balance_linear_tolerance),
            ("yaw", status.yaw_rate_rps, self._balance_yaw_tolerance),
        ):
            if value is None:
                reason += f"; {name} missing"
            elif abs(value) > tolerance:
                reason += f"; {name}={value:+.3f}"
        return reason or "ready for balance"

    def _controller_block_reason(self, control_mode):
        if control_mode in {"rl", "balance_stand", "balance"}:
            return ""
        return f"control={control_mode}"

    def _ready_for_balance(self) -> bool:
        return self._ready_controller() and self._measured_stop()

    def _ready_controller(self) -> bool:
        status = self.monitor.status()
        return (
            self._feedback_healthy()
            and status.control_mode in {"rl", "balance_stand", "balance"}
        )

    def _measured_stop(self) -> bool:
        status = self.monitor.status()
        speeds = (
            status.forward_mps,
            status.lateral_mps,
            status.yaw_rate_rps,
        )
        if any(value is None for value in speeds):
            return False
        return (
            abs(speeds[0]) <= self._balance_linear_tolerance
            and abs(speeds[1]) <= self._balance_linear_tolerance
            and abs(speeds[2]) <= self._balance_yaw_tolerance
        )

    def _feedback_healthy(self) -> bool:
        status = self.monitor.status()
        return status is not None and status.connected
