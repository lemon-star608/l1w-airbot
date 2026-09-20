# AIRBOT runtime on L1-W

Installed on the robot:

- server package: `airbot-arm 5.2.5`
- Python SDK: `arm-sdk 5.2.3`
- `grpcio 1.80.0`
- `protobuf 6.31.1`

The wheel metadata understates its generated-code requirements. Importing
`arm_sdk` 5.2.3 requires at least `grpcio 1.80.0` and Protobuf `6.31.1`; those
are the versions now installed under `~/.local`.

Read-only checks that do not start the server:

```sh
python3 -c 'import arm_sdk, grpc, google.protobuf; print(arm_sdk.version(), grpc.__version__, google.protobuf.__version__)'
arm-sdk --help
```

The server package contains no systemd unit and does not auto-start. For the
first hardware query, start it in the foreground with `--no-return`, then from
a second SSH session run:

```sh
airbot-arm --no-return -i can1 -t airbot_play_g2 --address 127.0.0.1:50051
python3 scripts/airbot/l1w_arm_firmware_info.py
```

`--no-return` is mandatory for our tests: without it, the server commands the
arm to return to zero when it exits. Do not use the bundled
`airbot_example_get_arm_joint_states` example as the first test. It acquires
control and enables gravity compensation, so the arm can physically move or be
moved.
