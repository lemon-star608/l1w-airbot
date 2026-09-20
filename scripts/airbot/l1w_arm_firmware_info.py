#!/usr/bin/env python3
"""Query AIRBOT firmware without acquiring arm control."""

from arm_sdk import AirbotClient


def main() -> None:
    client = AirbotClient(port=50051)
    try:
        info = client.get_firmware_info()
        if info is None:
            raise RuntimeError("the AIRBOT service returned no firmware info")
        print(info)
    finally:
        client.close()


if __name__ == "__main__":
    main()
