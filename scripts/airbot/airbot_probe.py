#!/usr/bin/env python3
"""Print read-only AIRBOT end-effector and joint states."""

import argparse
import time


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=50051)
    parser.add_argument("--duration", type=float, default=3.0)
    parser.add_argument("--period", type=float, default=0.2)
    args = parser.parse_args()
    if args.duration <= 0 or args.period <= 0:
        parser.error("--duration and --period must be positive")

    from l1w_teleop.arm.airbot import AirbotArmClient

    client = AirbotArmClient(host=args.host, port=args.port)
    try:
        deadline = time.monotonic() + args.duration
        while time.monotonic() < deadline:
            end = client.get_end_pose()
            joints = client.get_joint_angles()
            gripper = client.current_gripper()
            print(f"end={end} joints={joints} gripper={gripper:.4f}", flush=True)
            time.sleep(args.period)
    finally:
        client.close()


if __name__ == "__main__":
    main()
