#!/usr/bin/env python3
import argparse
import time

from arm_sdk.client import (
    AirbotClient,
    ArmControlOptions,
    Controller,
    WaypointSegmentOptions,
    WaypointsControlOptions,
)


def build_options(eff: float = 12.0, blocking: bool = True) -> ArmControlOptions:
    return ArmControlOptions(
        eff=[eff] * 6,
        eef_eff=10.0,
        velocity_scaling_factor=1.0,
        acceleration_scaling_factor=1.0,
        allow_planning_time=2.0,
        blocking=blocking,
    )


def print_state(client: AirbotClient, label: str) -> None:
    state = client.get_arm_joint_state()
    if state is None:
        print(f"{label}: joint state unavailable")
        return
    angles = ", ".join(f"{angle:+.3f}" for angle in state.angles)
    print(f"{label}: [{angles}] rad")


def run_showcase(client: AirbotClient, repeat: int) -> None:
    if not client.acquire_control():
        raise RuntimeError("could not acquire arm control lease")

    # Full commanded motor speed for the six arm joints.
    client.set_arm_speed([2.4] * 6)
    client.set_eef_speed(5.0)

    if not client.switch_controller(Controller.planning_control):
        raise RuntimeError("could not enter planning_control")

    options = build_options()

    # Opening salute: large pose, then throw the gripper open.
    hero = [0.65, -0.75, 0.85, 0.25, -0.65, 0.65]
    if not client.move_joint(hero, options, timeout_ms=5000):
        raise RuntimeError("hero pose rejected")

    if not client.switch_controller(Controller.servo_control):
        raise RuntimeError("could not enter servo_control for gripper")
    for gripper_pos in (1.0, 0.0, 1.0):
        if not client.move_eef(gripper_pos, options, timeout_ms=3000):
            raise RuntimeError(f"gripper move rejected: {gripper_pos}")

    if not client.switch_controller(Controller.planning_control):
        raise RuntimeError("could not return to planning_control")

    segment = WaypointSegmentOptions(
        motion_type="ptp",
        sampling_time=0.01,
        min_blend_radius=0.12,
        velocity_scaling_factor=1.0,
        acceleration_scaling_factor=1.0,
        allow_planning_time=2.0,
    )
    waypoint_options = WaypointsControlOptions(
        default_segment=segment,
        blocking=True,
    )

    # Fast cross-body wave with blended corners. The sequence stays inside the
    # configured joint limits while using nearly the full travel of each joint.
    waypoints = [
        [1.05, -0.75, 0.65, 0.65, -0.75, 0.95],
        [-1.05, -0.75, 0.65, -0.65, -0.75, -0.95],
        [0.75, -1.05, 0.95, -0.20, -0.95, 0.75],
        [-0.75, -0.35, 0.55, 0.20, -0.55, -0.75],
        [0.00, -1.05, 1.05, -0.20, -1.05, 1.05],
    ]

    for index in range(repeat):
        print_state(client, f"pass {index + 1}/{repeat} start")
        if not client.move_joint_waypoints(
            waypoints,
            waypoint_options,
            timeout_ms=15000,
        ):
            raise RuntimeError("waypoint showcase rejected")
        print_state(client, f"pass {index + 1}/{repeat} end")

    # Dramatic final pose, two gripper snaps, then a deterministic home return.
    final = [0.00, -1.05, 1.05, 0.20, -1.05, 0.20]
    if not client.move_joint(final, options, timeout_ms=5000):
        raise RuntimeError("final pose rejected")

    if not client.switch_controller(Controller.servo_control):
        raise RuntimeError("could not enter servo_control for final gripper")
    for gripper_pos in (0.0, 1.0, 0.0):
        if not client.move_eef(gripper_pos, options, timeout_ms=3000):
            raise RuntimeError(f"final gripper move rejected: {gripper_pos}")

    if not client.return_zero():
        raise RuntimeError("return-to-zero rejected")
    time.sleep(1.5)
    print_state(client, "final")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=50051)
    parser.add_argument("--repeat", type=int, default=2)
    args = parser.parse_args()

    client = AirbotClient(host=args.host, port=args.port)
    try:
        run_showcase(client, args.repeat)
    finally:
        client.release_control()
        client.close()


if __name__ == "__main__":
    main()
