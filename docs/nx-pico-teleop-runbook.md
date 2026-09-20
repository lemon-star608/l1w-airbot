# NX PICO teleop runbook

This runbook covers daily startup of the already-deployed NX runtime. The
project source is at `~/ws/pico-L1W`, PC-Service is enabled as
`xrobo-pc-service`, and the AIRBOT USB-CAN adapter is persisted as `can1`.

```text
PICO XRoboToolkit app -> NX 192.168.234.234 TCP 63901
NX python binding     -> localhost TCP 60061
NX l1w_teleop         -> 3588 192.168.234.1 UDP 8081
NX l1w_teleop         -> local AIRBOT service TCP 50051
```

## Daily bring-up

Use two or three NX SSH sessions, or equivalent separate `tmux` windows.

1. SSH to the NX and confirm the persistent services:

```bash
ssh robot@192.168.234.234
systemctl is-active airbot-can1 xrobo-pc-service
ip -brief link show can1
pgrep -af RoboticsServiceProcess
```

2. On the headset, open the XRoboToolkit app and connect to
   `192.168.234.234`. Camera streaming is not required for controller
   teleoperation.

3. Start the AIRBOT service in a foreground session with `--no-return`:

```bash
sudo airbot-arm --address 127.0.0.1:50051 -i can1 -t airbot_play_g2 --no-return
```

Keep this session open. `--no-return` prevents the server from commanding a
return-to-zero motion when it exits.

4. Return the arm to zero before Cartesian teleoperation. Hardware mode locks
   orientation to the SDK zero-pose quaternion `(0, 0, 0, 1)`; starting from a
   bent pose can make the first target fail IK:

```bash
export PATH="$HOME/.local/bin:$PATH"
arm-sdk examples run airbot_example_return_zero
```

Wait until the reported joint angles are near zero and the area is clear.

5. In another session, verify both links before real motion:

```bash
cd ~/ws/pico-L1W
PYTHONPATH=. python3 scripts/airbot/airbot_probe.py --host localhost --port 50051
PYTHONPATH=. python3 -m l1w_teleop \
  --source xrt --command-mode monitor \
  --dog-backend l1w-status --arm-backend airbot \
  --rate 50 --duration 0
```

This reads AIRBOT and dog state but does not acquire control or dispatch
motion. Input must remain `OK`, the dog state must be connected, and the arm
state must be readable. Do not run the C++ status monitor at the same time;
both bind UDP receive port 8080.

6. Start combined hardware teleoperation only after both read-only checks, the
   zero-return motion, and the area-clear confirmation are complete:

```bash
cd ~/ws/pico-L1W
PYTHONPATH=. python3 -m l1w_teleop \
  --source xrt --command-mode hardware \
  --dog-backend l1w --arm-backend airbot --arm-mode pose \
  --duration 0
```

The defaults are 50 Hz, locked zero-pose arm orientation, and one-to-one PICO
translation. On the NX, `--arm-host` defaults to localhost and `--dog-host`
defaults to `192.168.234.1`, so neither needs changing.

For a cautious first run, limit duration and use smaller dog scales, for
example `--duration 10 --dog-forward-scale 0.25 --dog-lateral-scale 0.15
--dog-rotate-scale 0.25`.

## Operator sequence

- Left X: stand the dog and enter motion mode.
- Left trigger: dog deadman.
- Left joystick: drive the dog.
- Right grip: arm deadman and Cartesian anchor.
- Right trigger: open the gripper.
- Right B: command dog damping.

Arm and dog commands are time-shared. Engaging the right grip stops and
settles the dog; dog motion can resume after the arm deadman is released.

## Stop order

1. Press right B, release both deadmen, then stop `l1w_teleop` with Ctrl+C.
2. Stop `airbot-arm` with Ctrl+C only after teleoperation has stopped.
3. PC-Service and `can1` can remain running. They do not acquire robot control
   by themselves.

## Service management

PC-Service and CAN interface checks:

```bash
systemctl status xrobo-pc-service --no-pager
journalctl -u xrobo-pc-service -n 100 --no-pager
ss -lntp | grep -E ':(63901|60061)\b'
python3 -c 'import xrobotoolkit_sdk; print(xrobotoolkit_sdk.__file__)'
```

If the service must be restarted:

```bash
sudo systemctl restart xrobo-pc-service
```

`airbot-can1` should normally remain enabled because it only creates the CAN
interface. Use the same interpreter for `xrobotoolkit_sdk`, `arm_sdk`, and
`l1w_teleop`; on the NX this is `/usr/bin/python3.10`.
