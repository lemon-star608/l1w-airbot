# PICO L1-W + AIRBOT teleoperation

中文说明见 [`README.zh-CN.md`](README.zh-CN.md).

This project runs on the NX compute unit inside a GENISOM L1-W robot dog. A
PICO 4 Ultra controller pair drives the dog through the GENISOM L1-W UDP
protocol and an AIRBOT Play G2 arm through the official AIRBOT gRPC service.

## Architecture

```text
PICO XRoboToolkit app -> NX 192.168.234.234 TCP 63901
NX PC-Service         -> xrobotoolkit_sdk localhost TCP 60061
NX l1w_teleop         -> dog controller / 3588 192.168.234.1 UDP 8081
NX l1w_teleop         -> local AIRBOT service TCP 50051
NX can1               -> DISCOVER USB-CAN -> AIRBOT arm
```

The NX is `robot@192.168.234.234`. The 3588 dog controller is reachable at
`192.168.234.1`; do not point dog commands at the NX itself. The PICO app must
connect to `192.168.234.234`, not `192.168.234.1`.

The project source is already deployed on the NX at `~/ws/pico-L1W`. PC-Service
and the AIRBOT CAN interface are persistent systemd services. The AIRBOT gRPC
server is deliberately manual so an operator confirms the work area before the
arm is energized.

## Required SDKs

The NX runtime is already provisioned with the following independent stacks:

| Stack | Installed on | Purpose | Reference |
| --- | --- | --- | --- |
| GENISOM L1-W SDK | pinned submodule in this repository | Dog UDP protocol, state decoding, and optional C++ diagnostics | [zsibot/genisom_L1_sdk](https://github.com/zsibot/genisom_L1_sdk) |
| AIRBOT Play service and Python SDK | NX | Arm gRPC server, IK, limits, planning, and Python client | [AIRBOT documentation](https://docs.discover-robotics.com) |
| XRoboToolkit PC-Service | NX `/opt/apps/roboticsservice` | PICO input transport | [XR-Robotics/XRoboToolkit-PC-Service](https://github.com/XR-Robotics/XRoboToolkit-PC-Service) |
| XRoboToolkit Python binding | NX Python 3.10 user packages | Controller state access | [XR-Robotics/XRoboToolkit-PC-Service-Pybind](https://github.com/XR-Robotics/XRoboToolkit-PC-Service-Pybind) |
| XRoboToolkit PICO app | PICO headset | Controller input and app connection | [XR-Robotics/XRoboToolkit-Unity-Client-Quest](https://github.com/XR-Robotics/XRoboToolkit-Unity-Client-Quest) |

The deployed versions are `airbot-arm 5.2.5`, `arm-sdk 5.2.3`, and the
XRoboToolkit 1.1.1 PICO app. Use one Python environment for
`xrobotoolkit_sdk`, `arm_sdk`, and `l1w_teleop`; on the NX this is system
Python 3.10.

The L1-W SDK is included as a git submodule. On a development machine that
needs the optional C++ diagnostics, initialize it with:

```bash
git submodule update --init --recursive
```

## Every-Session Bring-Up

The detailed runbook is
[`docs/nx-pico-teleop-runbook.md`](docs/nx-pico-teleop-runbook.md). The
essential sequence is below.

1. SSH to the NX:

```bash
ssh robot@192.168.234.234
```

2. Confirm the persistent services and CAN interface:

```bash
systemctl is-active airbot-can1 xrobo-pc-service
ip -brief link show can1
pgrep -af RoboticsServiceProcess
```

3. Put on the headset, open the XRoboToolkit app, and connect it to
   `192.168.234.234`.

4. In a foreground NX session, start the AIRBOT service:

```bash
sudo airbot-arm --address 127.0.0.1:50051 -i can1 -t airbot_play_g2 --no-return
```

Keep this session open. `--no-return` prevents the server from commanding a
return-to-zero motion when it exits.

5. Return the arm to its zero joint pose before every teleoperation session.
   Hardware mode locks Cartesian orientation to the SDK zero-pose quaternion
   `(0, 0, 0, 1)`; starting from a bent pose can make the first target fail IK:

```bash
export PATH="$HOME/.local/bin:$PATH"
arm-sdk examples run airbot_example_return_zero
```

This physically moves the arm. Keep people and fixtures clear, and wait until
the joint readings are near zero before continuing.

6. In another NX session, run read-only checks:

```bash
cd ~/ws/pico-L1W
PYTHONPATH=. python3 scripts/airbot/airbot_probe.py --host localhost --port 50051
PYTHONPATH=. python3 -m l1w_teleop \
  --source xrt --command-mode monitor \
  --dog-backend l1w-status --arm-backend airbot \
  --rate 50 --duration 0
```

Input must report `OK`, the dog state must be connected, and the arm state must
be readable before continuing.

7. Start combined hardware teleoperation:

```bash
cd ~/ws/pico-L1W
PYTHONPATH=. python3 -m l1w_teleop \
  --source xrt --command-mode hardware \
  --dog-backend l1w --arm-backend airbot --arm-mode pose \
  --duration 0
```

The defaults are 50 Hz, locked zero-pose arm orientation, and one-to-one PICO
translation. On the NX, `--arm-host` defaults to localhost and `--dog-host`
defaults to `192.168.234.1`.

## Controls and Stop Order

- Left X: stand the dog and enter motion mode.
- Left trigger: dog deadman.
- Left joystick: drive the dog; releasing the trigger zeroes dog motion.
- Right grip: arm deadman and Cartesian anchor.
- Right trigger: open the gripper.
- Right B: command dog damping.
- Ctrl+C: stop teleop after pressing right B and releasing both deadmen.

Arm and dog commands are deliberately time-shared. Engaging the right grip
stops and settles the dog; dog motion can resume only after the arm deadman is
released. Stop `l1w_teleop` first, then stop `airbot-arm`.

For an early test, limit the duration and lower dog scales, for example:

```bash
--duration 10 --dog-forward-scale 0.25 \
--dog-lateral-scale 0.15 --dog-rotate-scale 0.25
```

Keep the handheld safety controller available and keep the area clear. These
commands move real hardware.

## Repository Layout

- `l1w_teleop/`: Python teleoperation runtime and safety/mapping logic.
- `src/status_monitor.cpp`: C++ ground-truth reader built against the official
  prebuilt GENISOM SDK. It binds UDP 8080 and must not run concurrently with
  the Python dog client.
- `scripts/airbot/`: AIRBOT read-only probes and explicitly confirmed hardware
  tests.
- `scripts/l1w/`: explicitly confirmed L1-W zero-speed and stand tests.
- `tests/python/`: unit and runtime tests.
- `docs/`: operational runbooks and command mapping.
- `docs/archive/`: historical design plans and superseded hardware notes.
- `third_party/genisom_L1_sdk`: official SDK submodule.

## Development

Build the optional C++ ground-truth monitor:

```bash
git submodule update --init --recursive
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
```

Run Python tests:

```bash
PYTHONPATH=. python3 -m unittest discover -s tests/python -t . -v
```

## Safety Boundaries

The executable defaults to monitor mode and does not dispatch commands. Real
motion requires explicitly selecting hardware command mode and real backends.
Hardware sessions must keep the handheld safety controller available and the
area clear. AIRBOT uses `can1`, not the NX board CAN `can0`.
