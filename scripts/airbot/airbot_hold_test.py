#!/usr/bin/env python3
"""Energize AIRBOT servo mode and hold its current pose.

This is the first controlled hardware test. It never follows the PICO and
never commands return-zero. The explicit confirmation flag is mandatory.
"""

import argparse
import time


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=50051)
    parser.add_argument("--duration", type=float, default=5.0)
    parser.add_argument(
        "--i-understand-this-will-energize-the-arm",
        action="store_true",
        help="Required confirmation before enabling servo control.",
    )
    args = parser.parse_args()
    if not args.i_understand_this_will_energize_the_arm:
        parser.error(
            "refusing to energize the arm; add "
            "--i-understand-this-will-energize-the-arm"
        )

    from l1w_teleop.arm.airbot import AirbotArmClient

    client = AirbotArmClient(host=args.host, port=args.port)
    try:
        before = client.get_end_pose()
        print(f"before={before}", flush=True)
        client.enable_control()
        client.hold()
        deadline = time.monotonic() + max(args.duration, 0.0)
        while time.monotonic() < deadline:
            client.hold()
            print(f"hold={client.get_end_pose()}", flush=True)
            time.sleep(0.1)
    finally:
        client.close()


if __name__ == "__main__":
    main()
