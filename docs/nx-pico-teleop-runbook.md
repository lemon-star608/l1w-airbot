# NX PICO teleop deployment and runbook

This runbook moves the already-tested development-machine PICO stack onto the
robot NX. The dog control endpoint remains the 3588 at `192.168.234.1`; only
the PICO input source and AIRBOT client move to the NX.

```text
PICO XRoboToolkit app -> NX 192.168.234.234 TCP 63901
NX python binding     -> localhost TCP 60061
NX l1w_teleop         -> 3588 192.168.234.1 UDP 8081
NX l1w_teleop         -> local AIRBOT service TCP 50051
```

## One-time deployment

The NX must be reachable from the development machine. Run from the repository
root:

```bash
./scripts/nx/nx_deploy_pico_runtime.sh robot@192.168.234.234
```

The script checks that NX has `cmake`, `g++`, Python 3.10, and the Python
development header before copying files. The NX image already built the L1-W
C++ tools, so these should be present.

The script copies the arm64 PC-Service deb, the pybind source, the offline
`pybind11` wheel, and this project to the NX. It installs PC-Service, builds
`xrobotoolkit_sdk` for NX Python 3.10, links `libPXREARobotSDK.so` through
`/usr/local/lib`, and enables `xrobo-pc-service.service`.

If package installation reports a failed maintainer script, the script falls
back to extracting the same arm64 payload under `/opt/apps/roboticsservice`.
The normal deb has no declared package dependencies; the common failure is its
desktop-icon postinst. Do not use `--force-postinst`: it is not a dpkg force
option.

Expected deployment checks:

```bash
ssh robot@192.168.234.234
systemctl status xrobo-pc-service --no-pager
pgrep -af RoboticsServiceProcess
ss -lntp | grep -E ':(63901|60061)\b'
python3 -c 'import xrobotoolkit_sdk; print(xrobotoolkit_sdk.__file__)'
```

The SL CAN persistence installed earlier is independent:

```bash
systemctl status airbot-can1 --no-pager
ip -brief link show can1
```

## First PICO connection

1. Keep the headset and NX on the same network. On the robot hotspot this is
   the dog network; the NX address is normally `192.168.234.234`.
2. Install `XRoboToolkit-PICO-1.1.1.apk` on PICO if it is not installed.
3. Open the app, enter `192.168.234.234`, and connect. Camera streaming is not
   required for controller teleoperation.
4. Verify controller data without enabling either robot:

```bash
cd ~/ws/pico-L1W
PYTHONPATH=. python3 -m l1w_teleop --source xrt --command-mode monitor \
  --rate 50 --duration 0
```

Move both controllers, grips, triggers, joysticks, and buttons. The printed
input state must remain `OK`; removing tracking or sleeping the headset must
eventually report `STALE`.

## Daily bring-up

Use three NX SSH sessions, or equivalent separate `tmux` windows.

1. Confirm the CAN and PICO services:

```bash
systemctl is-active airbot-can1 xrobo-pc-service
ip -brief link show can1
pgrep -af RoboticsServiceProcess
```

2. Start the AIRBOT service in the foreground with `--no-return`:

```bash
sudo airbot-arm --address 127.0.0.1:50051 -i can1 -t airbot_play_g2 --no-return
```

Keep this session open. `--no-return` prevents the server from commanding a
return-to-zero motion when it exits.

3. In another session, verify both links before real motion:

```bash
cd ~/ws/pico-L1W
PYTHONPATH=. python3 scripts/airbot/airbot_probe.py --host localhost --port 50051
PYTHONPATH=. python3 -m l1w_teleop --source xrt --command-mode monitor \
  --dog-backend l1w-status --arm-backend airbot --rate 50 --duration 0
```

This reads AIRBOT and dog state but does not acquire control or dispatch
motion. Do not run the C++ status monitor at the same time; both bind UDP
receive port 8080.

4. Return the arm to zero before Cartesian teleoperation. Hardware mode locks
   orientation to the SDK zero-pose quaternion `(0, 0, 0, 1)`; starting from a
   bent pose can make the first target fail IK:

```bash
export PATH="$HOME/.local/bin:$PATH"
arm-sdk examples run airbot_example_return_zero
```

5. Start combined hardware teleoperation only after both read-only checks, the
   zero-return motion, and the area-clear confirmation are complete:

```bash
cd ~/ws/pico-L1W
PYTHONPATH=. python3 -m l1w_teleop \
  --source xrt --command-mode hardware \
  --dog-backend l1w --arm-backend airbot --arm-mode pose \
  --duration 0
```

This is the same command already validated on the development machine. The
defaults are 50 Hz, zero-pose arm orientation, and one-to-one PICO translation.
On the NX, `--arm-host` defaults to localhost and `--dog-host` defaults to
`192.168.234.1`, so neither needs changing.

Operator sequence: left X stands the dog and enters motion mode; left trigger
is the dog deadman; left joystick drives it; right grip is the arm deadman and
anchors Cartesian tracking; right trigger opens the gripper. Arm and dog
commands are time-shared: engaging the right grip stops and settles the dog.
Right B commands dog damping.

For the first NX run, consider limiting duration and starting with smaller dog
scales, for example `--duration 10 --dog-forward-scale 0.25
--dog-lateral-scale 0.15 --dog-rotate-scale 0.25`.

## Stop order

1. Press right B, release both deadmen, then stop `l1w_teleop` with Ctrl+C.
2. Stop `airbot-arm` with Ctrl+C only after teleoperation has stopped.
3. PC-Service and `can1` can remain running. They do not acquire robot control
   by themselves.

For a full shutdown:

```bash
sudo systemctl stop xrobo-pc-service
```

`airbot-can1` should normally remain enabled because it only creates the CAN
interface.

## NX service management

```bash
sudo systemctl restart xrobo-pc-service
journalctl -u xrobo-pc-service -n 100 --no-pager
sudo systemctl daemon-reload
```

If a rebuilt `xrobotoolkit_sdk` or AIRBOT Python package is installed with
`--user`, ensure the same interpreter is used for tests and teleoperation. On
NX this is `/usr/bin/python3.10`; avoid mixing it with a Conda environment.
