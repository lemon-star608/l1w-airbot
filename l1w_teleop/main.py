import argparse
import signal
import time

from .arm.mock import MockArmClient
from .arm.airbot import AirbotArmClient
from .control import CommandSafetyGate, InputMapping, RobotCommands
from .dog.l1w import L1WDogClient
from .dog.mock import MockDogClient
from .dog.udp import L1WUdpStatusMonitor
from .input import MockInputSource, PicoInputMonitor, XRobotToolkitSource
from .telemetry import TelelemetryPublisher, arm_telemetry, dog_telemetry


def run() -> None:
    args = _parse_args()
    if args.source == "xrt":
        source = XRobotToolkitSource()
    else:
        source = MockInputSource(rate_hz=args.rate)
    monitor = PicoInputMonitor(source, stale_after_s=args.stale_after)
    mapping = InputMapping(_mapping_config(args))
    safety = CommandSafetyGate(startup_hold_s=args.startup_hold)
    dog = _make_dog_client(args)
    dog_monitor = _make_dog_monitor(args, dog)
    arm = _make_arm_client(args)
    telemetry_publisher = (
        TelelemetryPublisher(
            udp_host=args.telemetry_host,
            udp_port=args.telemetry_udp_port,
            tcp_host=args.telemetry_tcp_bind,
            tcp_port=args.telemetry_tcp_port,
            queue_seconds=1.0 / args.telemetry_rate,
        )
        if args.telemetry_udp_port or args.telemetry_tcp_port
        else None
    )
    print(
        f"telemetry udp={args.telemetry_host or 'off'}:{args.telemetry_udp_port} "
        f"tcp={args.telemetry_tcp_bind or 'off'}:{args.telemetry_tcp_port}",
        flush=True,
    )
    running = True

    def stop(_signum, _frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    period = 1.0 / args.rate
    next_tick = time.monotonic()
    iterations = 0
    last_dog_runtime = None

    try:
        if args.command_mode == "hardware":
            arm.enable_control()
        while running and (args.duration <= 0 or iterations < args.duration * args.rate):
            inputs, stale = monitor.read()
            current_arm_pose = arm.get_end_pose() if not stale else None
            current_arm_joints = (
                arm.get_joint_angles()
                if args.arm_backend == "airbot" and not stale
                else None
            )
            commands = mapping.map(
                inputs,
                arm_mode=args.arm_mode,
                input_healthy=not stale,
                current_arm_pose=current_arm_pose,
            )
            commands, safety_state = safety.apply(commands, not stale)
            if hasattr(arm, "recover_rejected_pose"):
                arm.recover_rejected_pose()
            dog.update()
            _dispatch(dog, arm, commands, args.command_mode)
            dog_runtime = _dog_runtime(dog, args.dog_backend)
            if dog_runtime != last_dog_runtime:
                print(f"DOGFSM {dog_runtime or '-'}", flush=True)
                last_dog_runtime = dog_runtime
            _print_sample(
                iterations,
                inputs,
                stale,
                commands,
                safety_state.dog_enabled,
                safety_state.arm_enabled,
                dog_monitor.status() if dog_monitor else None,
                _dog_runtime(dog, args.dog_backend),
                getattr(dog_monitor, "command_statistics", lambda: None)()
                if dog_monitor is not None
                else None,
                current_arm_pose,
                current_arm_joints,
                args.print_every,
            )
            _publish_telemetry(
                telemetry_publisher,
                inputs=inputs,
                stale=stale,
                commands=commands,
                dog_status=dog_monitor.status() if dog_monitor else None,
                arm_backend=args.arm_backend,
                arm=arm,
                current_arm_pose=current_arm_pose,
                current_arm_joints=current_arm_joints,
            )
            iterations += 1
            next_tick += period
            sleep_s = next_tick - time.monotonic()
            if sleep_s > 0:
                time.sleep(sleep_s)
            else:
                next_tick = time.monotonic()
    finally:
        try:
            _dispatch(dog, arm, RobotCommands(), args.command_mode)
        finally:
            monitor.close()
        if args.dog_backend == "l1w":
            dog.close()
        if args.arm_backend == "airbot":
            arm.close()
        if dog_monitor is not None and args.dog_backend != "l1w":
            dog_monitor.close()
        if telemetry_publisher is not None:
            telemetry_publisher.close()


def _parse_args():
    parser = _argument_parser()
    args = parser.parse_args()
    if not 0.0 < args.arm_pose_scale:
        parser.error("--arm-pose-scale must be positive")
    if args.telemetry_rate <= 0:
        parser.error("--telemetry-rate must be positive")
    for name in (
        "--dog-forward-scale",
        "--dog-lateral-scale",
        "--dog-rotate-scale",
    ):
        value = getattr(args, name[2:].replace("-", "_"))
        if not 0.0 <= value <= 1.0:
            parser.error(f"{name} must be between 0 and 1")
    return args


def _argument_parser():
    parser = argparse.ArgumentParser(description="Read-only PICO controller monitor")
    parser.add_argument("--source", choices=("mock", "xrt"), default="mock")
    parser.add_argument("--rate", type=float, default=50.0)
    parser.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="Run until Ctrl+C/SIGTERM, or stop after this many seconds",
    )
    parser.add_argument("--stale-after", type=float, default=0.30)
    parser.add_argument("--print-every", type=int, default=10)
    parser.add_argument(
        "--command-mode",
        choices=("monitor", "trace", "hardware"),
        default="monitor",
    )
    parser.add_argument("--arm-mode", choices=("pose", "joystick"), default="pose")
    parser.add_argument("--arm-backend", choices=("mock", "airbot"), default="mock")
    parser.add_argument("--arm-host", default="localhost")
    parser.add_argument("--arm-port", type=int, default=50051)
    parser.add_argument(
        "--dog-backend",
        choices=("mock", "l1w-status", "l1w"),
        default="mock",
    )
    parser.add_argument("--dog-host", default="192.168.234.1")
    parser.add_argument("--dog-command-port", type=int, default=8081)
    parser.add_argument("--dog-receive-port", type=int, default=8080)
    parser.add_argument(
        "--startup-hold",
        type=float,
        default=2.0,
    )
    parser.add_argument("--dog-balance-settle", type=float, default=1.0)
    parser.add_argument(
        "--dog-forward-scale",
        type=float,
        default=0.50,
        help="Dimensionless L1-W forward remote axis scale.",
    )
    parser.add_argument(
        "--dog-lateral-scale",
        type=float,
        default=0.30,
        help="Dimensionless L1-W lateral remote axis scale.",
    )
    parser.add_argument(
        "--dog-rotate-scale",
        type=float,
        default=0.50,
        help="Dimensionless L1-W rotate remote axis scale.",
    )
    parser.add_argument(
        "--arm-pose-scale",
        type=float,
        default=1.0,
        help="AIRBOT meters per meter of PICO movement in hardware mode.",
    )
    parser.add_argument(
        "--lock-arm-orientation",
        action=_lock_arm_orientation_action(),
        default=True,
        help="Hold the SDK return-zero orientation and control position only "
        "(default: true).",
    )
    parser.add_argument(
        "--telemetry-host",
        default="",
        help="Mac destination IP for telemetry UDP; empty disables UDP.",
    )
    parser.add_argument(
        "--telemetry-udp-port",
        type=int,
        default=8766,
        help="UDP destination port; 0 disables UDP telemetry.",
    )
    parser.add_argument(
        "--telemetry-tcp-bind",
        default="0.0.0.0",
        help="TCP telemetry bind address on NX; set empty to disable TCP.",
    )
    parser.add_argument(
        "--telemetry-tcp-port",
        type=int,
        default=9766,
        help="TCP telemetry port for SSH port forwarding; 0 disables TCP.",
    )
    parser.add_argument("--telemetry-rate", type=float, default=30.0)
    return parser


def _lock_arm_orientation_action():
    # argparse.BooleanOptionalAction is unavailable on the NX's Python 3.8.
    if hasattr(argparse, "BooleanOptionalAction"):
        return argparse.BooleanOptionalAction
    return "store_true"


def _make_dog_client(args):
    if args.dog_backend != "l1w":
        return MockDogClient()
    if args.command_mode not in {"trace", "hardware"}:
        raise RuntimeError("L1-W dog control is not enabled in this mode")
    if not _real_dog_run_is_confirmed(args):
        raise RuntimeError(
            "real L1-W control requires source xrt, 5-30 s duration or 0 for "
            "run-until-stop, 10-100 Hz rate, and a valid command mode; in "
            "hardware mode it must be paired with AIRBOT pose teleoperation"
        )
    return L1WDogClient(
        host=args.dog_host,
        command_port=args.dog_command_port,
        receive_port=args.dog_receive_port,
        balance_settle_s=args.dog_balance_settle,
    )


def _real_dog_run_is_confirmed(args):
    confirmed = (
        args.source == "xrt"
        and (args.duration == 0 or 5 <= args.duration <= 30)
        and 10 <= args.rate <= 100
    )
    if args.command_mode == "trace":
        return confirmed
    return confirmed and _hardware_run_is_confirmed(args)


def _mapping_config(args):
    from .control import MappingConfig

    config = MappingConfig(
        dog_forward_scale=args.dog_forward_scale,
        dog_lateral_scale=args.dog_lateral_scale,
        dog_rotate_scale=args.dog_rotate_scale,
    )
    if args.command_mode == "hardware":
        config = MappingConfig(
            **{
                **config.__dict__,
                "pose_translation_scale": args.arm_pose_scale,
                "lock_orientation": args.lock_arm_orientation,
                "arm_speed": 0.02,
                "allow_return_zero": False,
                "arm_motion_stops_dog": args.dog_backend == "l1w",
            }
        )
    return config


def _make_dog_monitor(args, dog):
    if args.dog_backend == "mock":
        return None
    if args.dog_backend == "l1w":
        return dog.monitor
    return L1WUdpStatusMonitor(
        host=args.dog_host,
        command_port=args.dog_command_port,
        receive_port=args.dog_receive_port,
    )


def _make_arm_client(args):
    if args.arm_backend == "mock":
        return MockArmClient()
    if args.command_mode == "monitor":
        return AirbotArmClient(host=args.arm_host, port=args.arm_port)
    if args.command_mode != "hardware":
        raise RuntimeError(
            "AIRBOT trace mode is not enabled; use monitor or hardware"
        )
    if not _hardware_run_is_confirmed(args):
        raise RuntimeError(
            "hardware AIRBOT teleoperation requires source xrt, pose mode, the "
            "AIRBOT backend, and a 10-100 Hz rate"
        )
    return AirbotArmClient(host=args.arm_host, port=args.arm_port)


def _hardware_run_is_confirmed(args):
    return (
        args.source == "xrt"
        and args.arm_mode == "pose"
        and args.arm_backend == "airbot"
        and 10 <= args.rate <= 100
    )


def _dispatch(dog, arm, commands: RobotCommands, command_mode: str) -> None:
    # Monitor mode never leaves the read-only boundary.
    if command_mode == "monitor":
        return
    if command_mode == "hardware":
        if commands.dog_mode_command == "stand_up":
            dog.set_mode("stand_up")
        elif commands.dog_mode_command == "damping":
            dog.set_mode("damping")
        _dispatch_dog_motion(dog, commands)
        if commands.arm.enabled:
            arm.send_cartesian_pose(
                commands.arm.position,
                commands.arm.orientation,
                commands.arm.gripper,
            )
        else:
            arm.hold()
        return
    if commands.dog_mode_command == "stand_up":
        dog.set_mode("stand_up")
        return
    if commands.dog_mode_command == "damping":
        dog.set_mode("damping")
        return
    if commands.arm_mode_command == "return_zero":
        arm.return_zero()
        return
    _dispatch_dog_motion(dog, commands)
    if commands.arm.enabled:
        if commands.arm.mode == "pose":
            arm.send_cartesian_pose(
                commands.arm.position,
                commands.arm.orientation,
                commands.arm.gripper,
            )
        else:
            arm.send_cartesian_velocity(
                commands.arm.vx, commands.arm.vy, commands.arm.vz, commands.arm.gripper
            )
    else:
        arm.hold()


def _dispatch_dog_motion(dog, commands: RobotCommands) -> None:
    if commands.dog.enabled:
        dog.send_command(commands.dog.forward, commands.dog.rotate, commands.dog.lateral)
    else:
        dog.send_zero()


def _publish_telemetry(
    publisher,
    *,
    inputs,
    stale,
    commands,
    dog_status,
    arm_backend,
    arm,
    current_arm_pose,
    current_arm_joints,
):
    if publisher is None:
        return
    try:
        gripper = arm.current_gripper()
    except Exception:
        gripper = commands.arm.gripper
    arm_connected = arm_backend == "airbot" and current_arm_joints is not None
    publisher.publish(
        {
            "input": {"healthy": not stale, "motion_mode": commands.motion_mode},
            "dog": dog_telemetry(dog_status),
            "arm": arm_telemetry(
                arm_connected, current_arm_joints, gripper, current_arm_pose
            ),
        }
    )


def _print_sample(
    index,
    inputs,
    stale,
    commands,
    dog_enabled,
    arm_enabled,
    dog_status,
    dog_fsm,
    dog_tx,
    current_arm_pose,
    current_arm_joints,
    print_every,
):
    if index % print_every:
        return
    left = inputs.left
    right = inputs.right
    status = "STALE" if stale else "OK"
    print(
        f"#{index:05d} {status} "
        f"L pose={_fmt(left.pose)} grip={left.grip:.2f} trigger={left.trigger:.2f} axis={_fmt(left.axis)} | "
        f"R pose={_fmt(right.pose)} grip={right.grip:.2f} trigger={right.trigger:.2f} axis={_fmt(right.axis)} | "
        f"btn A{int(right.buttons[0])}B{int(right.buttons[1])}X{int(left.buttons[0])}Y{int(left.buttons[1])} Rstick={int(right.axis_click)} | "
        f"mode={commands.motion_mode} "
        f"dog={dog_enabled:d}:{commands.dog.forward:+.2f},{commands.dog.rotate:+.2f},{commands.dog.lateral:+.2f} "
        f"dogstate={_dog_status(dog_status)} "
        f"dogtx={_dog_tx(dog_tx)} "
        f"dogfsm={dog_fsm or '-'} "
        f"dogcmd={commands.dog_mode_command or '-'} "
        f"armcmd={commands.arm_mode_command or '-'} "
        f"arm={arm_enabled:d}:{commands.arm.mode} p={_fmt(commands.arm.position)} "
        f"q={_fmt(commands.arm.orientation)} g={commands.arm.gripper:.3f}",
        flush=True,
    )
    if current_arm_pose is not None:
        error = _distance(commands.arm.position, current_arm_pose[0])
        print(
            f"       armcur={_fmt(current_arm_pose[0])} "
            f"tracking_error={error:.3f} m",
            flush=True,
        )
    if current_arm_joints is not None:
        print(f"       armjoints={_fmt(current_arm_joints)}", flush=True)


def _fmt(pose):
    return "[" + ", ".join(f"{value:+.2f}" for value in pose) + "]"


def _dog_runtime(dog, backend):
    if backend != "l1w":
        return None
    reason = dog.blocked_reason
    return f"{dog.state}" if not reason else f"{dog.state} ({reason})"


def _dog_tx(statistics):
    if statistics is None:
        return "-"
    return (
        f"sdk={statistics.sent_sdk_control},"
        f"mv={statistics.sent_move_mode},"
        f"rx={statistics.sent_remote},"
        f"zero={statistics.sent_remote_zero}"
    )


def _distance(a, b):
    return sum((float(av) - float(bv)) ** 2 for av, bv in zip(a, b)) ** 0.5


def _dog_status(status):
    if status is None:
        return "mock"
    fields = (
        status.power_percent,
        status.function_mode,
        status.control_mode,
        status.motion_mode,
        status.forward_mps,
        status.lateral_mps,
        status.yaw_rate_rps,
        status.fault_count,
        status.speed_level,
    )
    if not status.connected:
        return "disconnected"
    formatted = []
    for value in fields:
        if value is None:
            formatted.append("-")
        elif isinstance(value, float):
            formatted.append(f"{value:+.3f}")
        else:
            formatted.append(str(value))
    return "1:" + ",".join(formatted)
