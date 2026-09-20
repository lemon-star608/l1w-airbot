from dataclasses import dataclass


@dataclass(frozen=True)
class ControllerFrame:
    """A controller sample; timestamp is generated on this computer."""

    local_monotonic_ns: int
    sdk_timestamp_ns: int
    pose: tuple
    grip: float
    trigger: float
    axis: tuple
    buttons: tuple = (False, False)  # Primary A/X, secondary B/Y.
    axis_click: bool = False


@dataclass(frozen=True)
class TeleopInputs:
    left: ControllerFrame
    right: ControllerFrame
