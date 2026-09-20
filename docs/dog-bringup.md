# L1-W read-only bring-up

## Network layout

The dog controller, not the NX, owns the SDK UDP endpoint:

```text
dog controller / SDK endpoint  192.168.234.1 UDP 8081
dog state stream source        192.168.234.1 (dynamic source port)
runtime receiver               0.0.0.0 UDP 8080
NX compute unit                192.168.234.234
```

The NX is reachable at `192.168.234.234` and currently runs `robot-launch`
with ROS 2 navigation/perception services. It did not bind UDP 8080/8081, so
running the SDK client there later will not conflict with those ports. Use the
dog-controller address (`192.168.234.1`) for `--dog-host`; do not point it at
the NX SSH address.

The Python status backend uses the documented L1-W UDP JSON protocol:

```text
NX/runtime host -> dog 192.168.234.1:8081  heartbeat only
dog -> NX/runtime host UDP 8080             state JSON
```

It does not send `CMD_SDK_CONTROL_RIGHT`, `SetRemote`, stand-up, sit-down, or
emergency-stop. Therefore it cannot move the dog.

Run with mock command dispatch while reading real dog state:

```sh
PYTHONPATH=. python -m l1w_teleop --source xrt --command-mode monitor \
  --dog-backend l1w-status --arm-backend mock
```

The log field is:

```text
dogstate=connected,power,control_mode,motion_mode,vx,vy,yaw_rate,fault_count
```

Do not run the C++ `status_monitor` at the same time because both bind UDP
receive port 8080.

The next hardware step is a separate, explicitly confirmed test that sends
only `CMD_SDK_CONTROL_RIGHT` and zero-speed remote packets, then observes the
returned control mode. Standing and low-speed motion must be later, separate
stages.

Run that first dog-control test:

```sh
PYTHONPATH=. python scripts/l1w/l1w_sdk_zero_test.py --duration 5 \
  --i-understand-this-will-request-dog-sdk-control
```

It sends the SDK control request once, then zero-speed remote packets at 20 Hz.
It does not command stand-up, sit-down, emergency stop, or any nonzero axis.
Success is confirmed by state feedback while the measured speeds remain near
zero. If control mode does not change or the dog reports a fault, stop and
capture the log.

After that succeeds, the stand-up test is separate:

```sh
PYTHONPATH=. python scripts/l1w/l1w_stand_test.py --duration 8 \
  --i-understand-this-will-stand-the-dog
```

The updated test requests SDK control, sends one zero-speed packet, sends
`CMD_STAND_UP` once, then deliberately does not send repeated zero-speed
packets. This compares SDK stand-hold behavior with the handheld controller's
stable standing behavior. After 15 seconds it sends `CMD_EMERGENCY_STOP` once
and reads state for two more seconds. Keep the area clear and keep the
handheld safety controller available during the damping transition.

The handheld remote is processed by `dog_task` through its SBUS input, while
the bottom controller exposes separate `STANDUP` and `RL_BALANCE_STAND`
states. Compare the SDK-side controllers with:

```sh
PYTHONPATH=. python scripts/l1w/l1w_stand_test.py --mode stand-balance \
  --duration 8 --i-understand-this-will-stand-the-dog
```

Direct `--mode balance` from damping was observed not to stand up, so treat
`0x9A` as a controller switch rather than a start-up command. The
`stand-balance` sequence sends `0x7A`, waits for `rl` feedback, then sends
`0x9A`. Use the same surface, duration, and payload when comparing
`--mode stand` and `--mode stand-balance`. Prefer the mode that remains stable
without repeated zero remote packets; do not carry extra payload during this
comparison.

The integrated PICO state uses the same behavior. After left X enters motion,
the L1-W backend requests SDK control, stands with `0x7A`, and switches once
to `0x9A` only after all three command axes and the measured linear/yaw
velocities have stayed stopped for one second. Its packet cadence mirrors the
official remote-control task:

```text
inactive --0x5A--> damping
inactive --0xB3, one zero, 0x7A--> standing
standing --feedback rl--> settling
settling --zero command >=1 s and vx/vy/yaw settled--> balance (one 0x9A)
balance --first nonzero command--> moving (one 0x8A, then remote)
moving --zero command--> settling (one zero remote)
```

The `role="sdk"` remote packets use dog_task's calibrated four-axis order:
`[lateral, forward, rotate, head_angle]`: positive lateral, forward, and rotate
mean right translation, forward motion, and right turn. Head angle remains zero
in this teleop client. This order and sign differ from the public C++
`SetRemote` documentation, which lists `[forward, rotate, lateral, head_angle]`.
Do not send a three-axis joystick payload; malformed nonzero remote packets can
be silently discarded by dog_task.

The backend does not continuously publish zero remote packets in `balance` or
while waiting to re-enter balance. This is intentional: repeated zero packets
were observed to cause small corrective motion, while the validated
`stand-balance` sequence did not.

The first bounded integrated test is:

```sh
PYTHONPATH=. /home/lemon/miniconda3/envs/airbot/bin/python -m l1w_teleop \
  --source xrt --command-mode trace --dog-backend l1w \
  --arm-backend mock --duration 8
```

Keep the handheld safety controller available and verify one complete
enter/exit cycle before enabling any nonzero dog motion.

The no-motion enter/exit cycle and the bounded
`0x8A -> nonzero remote -> zero remote -> 0x9A` cycle have now passed on
hardware. For the first continuous walking session, use `--duration 0`; it
runs until right B commands damping or the operator stops it with Ctrl+C.
Press right B before Ctrl+C whenever practical.

```sh
PYTHONPATH=. /home/lemon/miniconda3/envs/airbot/bin/python -m l1w_teleop \
  --source xrt --command-mode trace --dog-backend l1w \
  --arm-backend mock --duration 0
```

For debugging a nonmoving walk command, add `--print-every 1`. Watch the
`DOGFSM` line, `dog=`, and `dogtx=` fields together. `dog=0` means mapping or
the left-trigger deadman blocked the command; `dogfsm=standing (...)` or
`settling (...)` means the backend is waiting on the named feedback condition;
`dogfsm=moving` with `dog=1:+0.50,...` and increasing
`rx=` means nonzero SDK remote packets are being dispatched. `dogstate` ends
with the current speed level (`low`, `normal`, or `fast`). If the state is
already `moving`, remote packets are increasing, the reported command is
nonzero, but measured speeds remain near zero, test the speed level or dog
controller before changing the PICO mapping scales.

## Combined real-dog and AIRBOT run

Once the dog-only trace mode and AIRBOT hardware mode have both passed, the
combined entry point is `hardware` mode. Start AIRBOT first in one SSH session:

```sh
airbot-arm --no-return -i can1 -t airbot_play_g2 --address 127.0.0.1:50051
```

Then run the combined client from the repository root:

```sh
PYTHONPATH=. /home/lemon/miniconda3/envs/airbot/bin/python -m l1w_teleop \
  --source xrt --command-mode hardware \
  --dog-backend l1w --arm-backend airbot --arm-mode pose \
  --arm-pose-scale 0.5
```

This is deliberately time-shared, not simultaneous motion. Right grip controls
the arm and forces the dog through its stop/settle cycle; only after right grip
is released can the left-trigger deadman and left joystick move the dog. Keep
the handheld safety controller available. In combined mode, right B commands
the dog's normal damping transition and the arm holds its last accepted
Cartesian target while the dog lies down.

## Pending hardware acceptance

1. Define and test behavior for changing fault count. Stale feedback now blocks
   `standing -> settling -> balance`, but faults are still logged rather than
   actively changing the FSM.
2. Repeat routing and UDP-port checks on NX (`192.168.234.1:8081`, local
   receive port 8080), then repoint the PICO app to the NX address.
