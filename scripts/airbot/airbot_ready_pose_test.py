#!/usr/bin/env python3
"""Move AIRBOT to a bent, non-singular pose before Cartesian tuning."""

import argparse
import time


from l1w_teleop.arm.airbot import AirbotArmClient


READY_POSE = AirbotArmClient.READY_JOINTS


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=50051)
    parser.add_argument("--duration", type=float, default=6.0)
    parser.add_argument(
        "--i-understand-this-will-move-the-airbot",
        action="store_true",
        help="Required confirmation before moving joints.",
    )
    args = parser.parse_args()
    if not args.i_understand_this_will_move_the_airbot:
        parser.error(
            "refusing to move the arm; add "
            "--i-understand-this-will-move-the-airbot"
        )
    if not 3.0 <= args.duration <= 15.0:
        parser.error("--duration must be between 3 and 15 seconds")

    from l1w_teleop.arm.airbot import AirbotArmClient

    client = AirbotArmClient(host=args.host, port=args.port)
    try:
        print(
            f"before_end={client.get_end_pose()} "
            f"joints={client.get_joint_angles()}",
            flush=True,
        )
        client.enable_control()
        if not client.move_joint(READY_POSE):
            raise RuntimeError("AIRBOT rejected the ready pose")
        print("phase=moving-to-ready", flush=True)

        deadline = time.monotonic() + args.duration
        while time.monotonic() < deadline:
            print(
                f"end={client.get_end_pose()} joints={client.get_joint_angles()}",
                flush=True,
            )
            time.sleep(0.2)
    finally:
        client.close()


if __name__ == "__main__":
    main()
