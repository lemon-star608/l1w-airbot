import math
import time
from typing import Tuple
from dataclasses import dataclass

from .models import ControllerFrame, TeleopInputs


@dataclass
class SourceState:
    timestamp_ns: int = 0
    left_pose: tuple = (0.0,) * 7
    right_pose: tuple = (0.0,) * 7
    left_grip: float = 0.0
    right_grip: float = 0.0
    left_trigger: float = 0.0
    right_trigger: float = 0.0
    left_axis: tuple = (0.0, 0.0)
    right_axis: tuple = (0.0, 0.0)
    left_buttons: tuple = (False, False)
    right_buttons: tuple = (False, False)
    left_axis_click: bool = False
    right_axis_click: bool = False


class InputSource:
    def read(self) -> SourceState:
        raise NotImplementedError

    def close(self):
        pass


class MockInputSource(InputSource):
    """Produces a small deterministic motion for offline UI tests."""

    def __init__(self, rate_hz: float = 50.0):
        self._period_ns = int(1_000_000_000 / rate_hz)
        self._tick = 0
        self._started_ns = time.monotonic_ns()

    def read(self) -> SourceState:
        self._tick += 1
        elapsed = self._tick * self._period_ns
        value = min(1.0, self._tick / 25.0)
        return SourceState(
            timestamp_ns=elapsed,
            left_pose=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0),
            right_pose=(value * 0.20, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0),
            left_grip=value if self._tick % 100 < 50 else 0.0,
            right_grip=value,
            left_trigger=0.0,
            right_trigger=0.5,
            left_axis=(0.0, value if self._tick % 200 < 100 else 0.0),
            right_axis=(0.0, 0.0),
            left_buttons=(self._tick % 400 < 200, False),
            right_buttons=(self._tick % 600 < 300, False),
            left_axis_click=False,
            right_axis_click=False,
        )


class XRobotToolkitSource(InputSource):
    """Reads the official PICO PC-Service pybind API."""

    def __init__(self):
        import xrobotoolkit_sdk as xrt

        self._xrt = xrt
        self._xrt.init()

    def read(self) -> SourceState:
        xrt = self._xrt
        return SourceState(
            timestamp_ns=int(xrt.get_time_stamp_ns()),
            left_pose=tuple(xrt.get_left_controller_pose()),
            right_pose=tuple(xrt.get_right_controller_pose()),
            left_grip=float(xrt.get_left_grip()),
            right_grip=float(xrt.get_right_grip()),
            left_trigger=float(xrt.get_left_trigger()),
            right_trigger=float(xrt.get_right_trigger()),
            left_axis=tuple(xrt.get_left_axis()),
            right_axis=tuple(xrt.get_right_axis()),
            left_buttons=(bool(xrt.get_X_button()), bool(xrt.get_Y_button())),
            right_buttons=(bool(xrt.get_A_button()), bool(xrt.get_B_button())),
            left_axis_click=bool(xrt.get_left_axis_click()),
            right_axis_click=bool(xrt.get_right_axis_click()),
        )

    def close(self):
        self._xrt.close()


class PicoInputMonitor:
    """Adds local timing, finite-value checks, and stale-data detection."""

    def __init__(self, source: InputSource, stale_after_s: float = 0.30):
        self._source = source
        self._stale_after_ns = int(stale_after_s * 1_000_000_000)
        self._last_timestamp_ns = None
        self._last_fingerprint = None
        self._first_unchanged_ns = None

    def read(self) -> Tuple[TeleopInputs, bool]:
        state = self._source.read()
        local_ns = time.monotonic_ns()
        fingerprint = (
            state.timestamp_ns,
            state.left_pose,
            state.right_pose,
            state.left_grip,
            state.right_grip,
            state.left_trigger,
            state.right_trigger,
            state.left_axis,
            state.right_axis,
            state.left_buttons,
            state.right_buttons,
            state.left_axis_click,
            state.right_axis_click,
        )
        changed = fingerprint != self._last_fingerprint
        self._last_timestamp_ns = state.timestamp_ns
        if changed or self._first_unchanged_ns is None:
            self._first_unchanged_ns = local_ns
        self._last_fingerprint = fingerprint
        stale = local_ns - self._first_unchanged_ns > self._stale_after_ns
        frames = []
        for side in ("left", "right"):
            pose = tuple(getattr(state, f"{side}_pose"))
            axis = tuple(getattr(state, f"{side}_axis"))
            grip = float(getattr(state, f"{side}_grip"))
            trigger = float(getattr(state, f"{side}_trigger"))
            buttons = tuple(bool(v) for v in getattr(state, f"{side}_buttons"))
            axis_click = bool(getattr(state, f"{side}_axis_click"))
            finite = all(_finite(value) for value in pose + axis + (grip, trigger))
            if not finite:
                pose = (0.0,) * 7
                axis = (0.0, 0.0)
                grip = 0.0
                trigger = 0.0
                stale = True
            frames.append(
                ControllerFrame(
                    local_monotonic_ns=local_ns,
                    sdk_timestamp_ns=state.timestamp_ns,
                    pose=pose,
                    grip=grip,
                    trigger=trigger,
                    axis=axis,
                    buttons=buttons,
                    axis_click=axis_click,
                )
            )
        return TeleopInputs(left=frames[0], right=frames[1]), stale

    def close(self):
        self._source.close()


def _finite(value) -> bool:
    try:
        return math.isfinite(value)
    except TypeError:
        return False
