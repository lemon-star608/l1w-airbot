#!/usr/bin/env python3
"""Request L1-W SDK control and send zero-speed only.

This test does not stand up, move, sit down, or send emergency stop. The
explicit confirmation flag is mandatory.
"""

import argparse
import time


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="192.168.234.1")
    parser.add_argument("--command-port", type=int, default=8081)
    parser.add_argument("--receive-port", type=int, default=8080)
    parser.add_argument("--duration", type=float, default=5.0)
    parser.add_argument(
        "--i-understand-this-will-request-dog-sdk-control",
        action="store_true",
        help="Required confirmation before requesting SDK control.",
    )
    args = parser.parse_args()
    if not args.i_understand_this_will_request_dog_sdk_control:
        parser.error(
            "refusing to request dog SDK control; add "
            "--i-understand-this-will-request-dog-sdk-control"
        )
    if not 5.0 <= args.duration <= 30.0:
        parser.error("--duration must be between 5 and 30 seconds")

    from l1w_teleop.dog.udp import L1WUdpStatusMonitor

    monitor = L1WUdpStatusMonitor(
        host=args.host,
        command_port=args.command_port,
        receive_port=args.receive_port,
    )
    try:
        deadline = time.monotonic() + args.duration
        next_packet = 0.0
        requested = False
        while time.monotonic() < deadline:
            now = time.monotonic()
            if now >= next_packet:
                if not requested:
                    monitor.send_sdk_control_request()
                    requested = True
                else:
                    monitor.send_remote_zero()
                next_packet = now + 0.05
            status = monitor.status()
            print(
                " ".join(
                    [
                        f"connected={int(status.connected)}",
                        f"function={status.function_mode or '-'}",
                        f"control={status.control_mode or '-'}",
                        f"motion={status.motion_mode or '-'}",
                        f"vx={status.forward_mps if status.forward_mps is not None else float('nan'):+.3f}",
                        f"vy={status.lateral_mps if status.lateral_mps is not None else float('nan'):+.3f}",
                        f"yaw={status.yaw_rate_rps if status.yaw_rate_rps is not None else float('nan'):+.3f}",
                    ]
                ),
                flush=True,
            )
            time.sleep(0.1)
    finally:
        monitor.close()


if __name__ == "__main__":
    main()
