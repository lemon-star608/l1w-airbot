# PICO L1-W + AIRBOT teleoperation

中文说明见 [`README.zh-CN.md`](README.zh-CN.md)。

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

## Software stack

Three independent SDK stacks are used. Do not confuse their install locations.

### GENISOM L1-W dog SDK

- Source: `third_party/genisom_L1_sdk`, a pinned git submodule.
- Runtime protocol: UDP JSON. The NX sends commands to the 3588 dog controller
  at `192.168.234.1:8081` and receives state on local UDP 8080.
- The Python teleop runtime implements this protocol directly and needs no
  package installation on the NX.
- The optional C++ `status_monitor` links the submodule's prebuilt
  `libzsibot.a`; it is a ground-truth diagnostic, not part of daily teleop.
- Initialize it with `git submodule update --init --recursive`.

### AIRBOT Play G2 arm service and Python SDK

These are already installed on the current NX:

- Service: `airbot-arm 5.2.5`, executable `/usr/bin/airbot-arm`, gRPC port
  `50051`.
- Python client: `arm_sdk 5.2.3`, imported as `arm_sdk`.
- Runtime dependencies: `grpcio` and a current protobuf runtime.
- The server performs IK, limits, planning, and the servo stale watchdog. This
  repository does not implement arm IK.
- The service has no systemd unit and must be started manually after the work
  area is confirmed clear.

Local recovery artifacts on the development machine:

```text
/home/lemon/下载/airbot_arm_release/product/aarch64/jammy/airbot-arm_5.2.5_arm64.deb
/home/lemon/下载/dist/aarch64/arm_sdk-5.2.3-py3-none-any.whl
```

To reinstall on a clean NX:

```bash
sudo apt install -y ./airbot-arm_5.2.5_arm64.deb
python3 -m pip install --user ./arm_sdk-5.2.3-py3-none-any.whl
```

The pip resolver may select an older generated-code-compatible protobuf
runtime if left unconstrained. After installation verify imports with:

```bash
python3 -c 'import arm_sdk, grpc, google.protobuf; print(arm_sdk.version(), grpc.__version__, google.protobuf.__version__)'
```

If import fails, install the protobuf/grpcio versions documented in
`docs/airbot-runtime.md` or copy the known-good `~/.local` packages from the
current NX.

### XRoboToolkit PICO input stack

PC-Service and the PICO app provide controller input only. They do not talk to
the dog or arm directly.

- PICO app: `XRoboToolkit-PICO-1.1.1.apk`, installed on the headset.
- NX service: `XRoboToolkit-PC-Service-headless_1.0.0.0_arm64.deb`, installed
  at `/opt/apps/roboticsservice`.
- Python binding: compiled on the NX from the official pybind source. It links
  the `libPXREARobotSDK.so` shipped inside the PC-Service deb.
- Binding build dependencies: pybind source, `nlohmann/json.hpp`, and the
  offline pybind11 wheel. These are copied automatically by the deployment
  script.
- Service ports: PICO app connects to NX TCP `63901`; the Python binding talks
  to localhost TCP `60061`.

Development-machine artifacts:

```text
/home/lemon/ws-motphys/vendor/binaries/XRoboToolkit-PICO-1.1.1.apk
/home/lemon/ws-motphys/vendor/binaries/XRoboToolkit-PC-Service-headless_1.0.0.0_arm64.deb
/home/lemon/ws-motphys/vendor/pybind-repo
/home/lemon/ws-motphys/vendor/include/nlohmann
/home/lemon/ws-motphys/vendor/wheels/aarch64/pybind11-2.13.6-py3-none-any.whl
```

Do not run the pybind repository's `setup_orin.sh`; it downloads a large
PC-Service source tree that the headless deb already provides.

## One-time NX deployment

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

The deploy script requires passwordless sudo for the `robot` user. On a clean
NX, configure it once:

```bash
ssh robot@192.168.234.234
echo 'robot ALL=(ALL) NOPASSWD: ALL' | sudo tee /etc/sudoers.d/robot
sudo chmod 440 /etc/sudoers.d/robot
```

It also requires `cmake`, `g++`, Python 3.10, and `/usr/include/python3.10/Python.h`;
Ubuntu's `build-essential`, `cmake`, and `python3-dev` packages provide these.

Deployment result:

```text
~/ws/pico-L1W                 project source and scripts
/opt/apps/roboticsservice     PC-Service arm64 installation
xrobo-pc-service.service      PC-Service systemd unit
airbot-can1.service           can1 persistence for DISCOVER USB-CAN
~/.local/lib/python3.10/site-packages/xrobotoolkit_sdk*.so
```

After deployment, connect the PICO app to `192.168.234.234`. Do not use
`192.168.234.1`; that address is the 3588 dog controller.

## Real-robot use

The detailed procedure is
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

Keep this session open.

5. Return the arm to its zero joint pose. The teleop runtime locks Cartesian
   orientation to the SDK zero-pose quaternion `(0, 0, 0, 1)`, so starting
   from a nonzero bent pose can make the first Cartesian target fail IK:

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

Input must report `OK`, the dog state must be connected, and the arm state
must be readable before continuing.

7. Start combined hardware teleoperation:

```bash
cd ~/ws/pico-L1W
PYTHONPATH=. python3 -m l1w_teleop \
  --source xrt --command-mode hardware \
  --dog-backend l1w --arm-backend airbot --arm-mode pose \
  --duration 0
```

Operator controls:

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

For the first session on a new deployment, add a bounded duration and lower
dog scales, for example:

```bash
--duration 10 --dog-forward-scale 0.25 \
--dog-lateral-scale 0.15 --dog-rotate-scale 0.25
```

Keep the handheld safety controller available and keep the area clear. These
commands move real hardware.

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
motion requires explicitly selecting hardware command mode and real backends.
Hardware sessions must keep the
handheld safety controller available and the area clear. AIRBOT uses `can1`,
not the NX board CAN `can0`.

Historical design notes are retained in
`docs/archive/ROADMAP-2026-09.md`; current operating procedures in `docs/`
take precedence when information differs.
