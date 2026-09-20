# PICO L1-W + AIRBOT teleoperation

This project runs on the NX compute unit inside a GENISOM L1-W robot dog. It
uses a PICO 4 Ultra controller pair to teleoperate the dog through the L1-W
SDK UDP endpoint and an AIRBOT Play G2 arm through the official AIRBOT gRPC
service.

## Architecture

```text
PICO XRoboToolkit app -> NX 192.168.234.234 TCP 63901
NX PC-Service         -> xrobotoolkit_sdk localhost TCP 60061
NX l1w_teleop         -> dog controller / 3588 192.168.234.1 UDP 8081
NX l1w_teleop         -> local AIRBOT service TCP 50051
NX can1               -> DISCOVER USB-CAN -> AIRBOT arm
```

The NX is `robot@192.168.234.234`. The 3588 dog controller is reachable at
`192.168.234.1`; do not point dog commands at the NX itself.

## Deploy once on NX

From the development machine:

```bash
./scripts/nx/nx_deploy_pico_runtime.sh robot@192.168.234.234
```

The script installs the arm64 PC-Service package, builds `xrobotoolkit_sdk`
for NX Python 3.10, and enables `xrobo-pc-service`. AIRBOT CAN persistence is
installed separately with:

```bash
./scripts/nx/nx_airbot_can_setup.sh robot@192.168.234.234
```

## Daily bring-up

The complete procedure, including read-only checks and stop order, is in
[`docs/nx-pico-teleop-runbook.md`](docs/nx-pico-teleop-runbook.md).

Start the AIRBOT service in a foreground NX session:

```bash
sudo airbot-arm --address 127.0.0.1:50051 -i can1 -t airbot_play_g2 --no-return
```

Then start combined hardware teleoperation in another session:

```bash
cd ~/ws/pico-L1W
PYTHONPATH=. python3 -m l1w_teleop \
  --source xrt --command-mode hardware \
  --dog-backend l1w --arm-backend airbot --arm-mode pose \
  --rate 50 --lock-arm-orientation --arm-pose-scale 1.0 \
  --i-understand-this-will-control-the-dog \
  --i-understand-this-will-move-the-airbot
```

Left X enters motion mode and stands the dog; left trigger is the dog
deadman; left joystick drives the dog. Right grip is the arm deadman; right
trigger controls the gripper. Right B commands dog damping. Arm tracking
forces the dog through its stop/settle cycle.

## Repository layout

- `l1w_teleop/`: Python teleoperation runtime and safety/mapping logic.
- `src/status_monitor.cpp`: C++ ground-truth reader built against the official
  prebuilt GENISOM SDK. It binds UDP 8080 and must not run concurrently with
  the Python dog client.
- `scripts/nx/`: one-time NX deployment and persistent service setup.
- `scripts/airbot/`: AIRBOT read-only probes and explicitly confirmed hardware
  tests.
- `scripts/l1w/`: explicitly confirmed L1-W zero-speed and stand tests.
- `tests/python/`: unit and runtime tests.
- `docs/`: operational runbooks and command mapping.
- `docs/archive/`: historical design plans and superseded hardware notes.
- `third_party/genisom_L1_sdk`: official SDK submodule.

## Development

Build the C++ ground-truth monitor:

```bash
git submodule update --init --recursive
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
```

Run Python tests:

```bash
PYTHONPATH=. python3 -m unittest discover -s tests/python -t . -v
```

Use the same Python environment for `xrobotoolkit_sdk`, `arm_sdk`, and
`l1w_teleop`. On NX this is `/usr/bin/python3.10`; do not mix it with a Conda
environment.

## Safety boundaries

The executable defaults to monitor mode and does not dispatch commands. Real
motion requires explicit confirmation flags. Hardware sessions must keep the
handheld safety controller available and the area clear. AIRBOT uses `can1`,
not the NX board CAN `can0`.

Historical design notes are retained in
`docs/archive/ROADMAP-2026-09.md`; current operating procedures in `docs/`
take precedence when information differs.
