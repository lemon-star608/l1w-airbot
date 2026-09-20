#!/usr/bin/env python3
"""Request L1-W SDK control, stand without repeated zero commands, then damp."""

import argparse
import time


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="192.168.234.1")
    parser.add_argument("--command-port", type=int, default=8081)
    parser.add_argument("--receive-port", type=int, default=8080)
    parser.add_argument(
        "--duration",
        type=float,
        default=15.0,
        help="Seconds to stand before automatic damping.",
    )
    parser.add_argument(
        "--mode",
        choices=("stand", "balance", "stand-balance"),
        default="stand",
        help=(
            "Stand controller sequence to test: 0x7A stand, direct 0x9A "
            "balance, or 0x7A followed by 0x9A."
        ),
    )
    parser.add_argument(
        "--switch-delay",
        type=float,
        default=1.0,
        help="Seconds to wait after rl feedback before stand-balance sends 0x9A.",
    )
    parser.add_argument(
        "--i-understand-this-will-stand-the-dog",
        action="store_true",
        help="Required confirmation before commanding stand-up.",
    )
    args = parser.parse_args()
    if not args.i_understand_this_will_stand_the_dog:
        parser.error(
            "refusing to stand the dog; add "
            "--i-understand-this-will-stand-the-dog"
        )
    if not 5.0 <= args.duration <= 30.0:
        parser.error("--duration must be between 5 and 30 seconds")
    if not 0.2 <= args.switch_delay <= 3.0:
        parser.error("--switch-delay must be between 0.2 and 3 seconds")

    from l1w_teleop.dog.udp import L1WUdpStatusMonitor

    monitor = L1WUdpStatusMonitor(
        host=args.host,
        command_port=args.command_port,
        receive_port=args.receive_port,
    )
    try:
        monitor.send_sdk_control_request()
        time.sleep(0.2)
        monitor.send_remote_zero()
        time.sleep(0.2)
        if args.mode == "balance":
            monitor.send_balance_stand_mode()
        else:
            monitor.send_stand_up()
        print(f"phase={args.mode}", flush=True)

        if args.mode == "stand-balance":
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                status = monitor.status()
                if status.control_mode == "rl":
                    break
                time.sleep(0.05)
            else:
                print("phase=stand-balance-timeout", flush=True)
            time.sleep(args.switch_delay)
            monitor.send_balance_stand_mode()
            print("phase=balance", flush=True)

        deadline = time.monotonic() + args.duration
        while time.monotonic() < deadline:
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

        monitor.send_emergency_stop()
        print("phase=damping", flush=True)
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            status = monitor.status()
            print(
                " ".join(
                    [
                        f"connected={int(status.connected)}",
                        f"function={status.function_mode or '-'}",
                        f"control={status.control_mode or '-'}",
                        f"motion={status.motion_mode or '-'}",
                    ]
                ),
                flush=True,
            )
            time.sleep(0.1)
    finally:
        monitor.close()


if __name__ == "__main__":
    main()
