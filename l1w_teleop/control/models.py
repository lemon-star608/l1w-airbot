from dataclasses import dataclass, field


@dataclass(frozen=True)
class DogCommand:
    """Normalized dog motion in robot-frame convention.

    Positive forward, rotate, and lateral mean forward, left turn, and left
    translation. The UDP backend converts these values to the firmware's
    nonstandard joystick order and signs.
    """

    forward: float = 0.0
    rotate: float = 0.0
    lateral: float = 0.0
    enabled: bool = False


@dataclass(frozen=True)
class ArmCommand:
    """A Cartesian command for the mounted arm."""

    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0
    position: tuple = (0.0, 0.0, 0.0)
    orientation: tuple = (0.0, 0.0, 0.0, 1.0)
    gripper: float = 0.036
    enabled: bool = False
    mode: str = "pose"


@dataclass(frozen=True)
class RobotCommands:
    dog: DogCommand = field(default_factory=DogCommand)
    arm: ArmCommand = field(default_factory=ArmCommand)
    arm_mode_command: str = ""  # Empty or return_zero.
    dog_mode_command: str = ""  # Empty, stand_up, or damping.
    motion_mode: str = "damping"  # damping or motion.


@dataclass(frozen=True)
class MappingConfig:
    deadzone: float = 0.12
    enable_threshold: float = 0.5
    release_threshold: float = 0.4
    dog_forward_scale: float = 0.50
    dog_lateral_scale: float = 0.30
    dog_rotate_scale: float = 0.50
    arm_speed: float = 0.08
    pose_translation_scale: float = 1.0
    # XRoboToolkit headset-to-world convention. AIRBOT x/y/z <- VR -z/-x/y.
    pose_translation_axes: tuple = ((2, -1.0), (0, -1.0), (1, 1.0))
    lock_orientation: bool = False
    # SDK end_link orientation at the zero pose. Joint 6 can be rotated to make
    # the gripper horizontal only after the arm leaves the zero-pose IK branch;
    # rotating at zero is rejected by the controller's IK solver.
    lock_orientation_target: tuple = (0.0, 0.0, 0.0, 1.0)
    gripper_min: float = 0.0
    gripper_max: float = 0.072
    gripper_initial: float = 0.036
    allow_return_zero: bool = True
    # Mounted-arm safety policy: while the arm tracks, the dog must stop.
    arm_motion_stops_dog: bool = False


@dataclass(frozen=True)
class SafetyState:
    input_healthy: bool
    dog_enabled: bool
    arm_enabled: bool
    elapsed_s: float
