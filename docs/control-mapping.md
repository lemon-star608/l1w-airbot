# PICO to robot command mapping

This revision adds the mapping and safety layers only. The executable defaults
to `--command-mode monitor`: it reads PICO input and computes commands, but does
not dispatch them to a robot client. `--command-mode trace` dispatches to mock
clients only.

## Input mapping

Dog:

- The global state machine starts in `damping` mode. Left X enters motion mode
  and commands the dog to stand. Right B exits motion mode and commands the dog
  to enter damping. Right A remains reserved by the XRoboToolkit app.
- Left trigger is the dog deadman. Values at or above `0.5` enable motion.
- Continuous dog commands are generated only in motion mode.
- Left joystick Y maps to forward/backward. PICO reports negative Y when the
  stick is pushed forward, so the mapping negates it.
- Left joystick X maps to lateral motion. It is negated because positive L1-W
  lateral means left while positive PICO X means right.
- Right joystick X maps to rotation. It is negated so pushing left commands a
  left turn.
- Releasing the left trigger zeroes all dog motion axes.
- The L1-W control backend stands with `0x7A`, then waits until the forward,
  lateral, and rotation commands are all zero for one second and the reported
  linear/yaw velocities have settled before switching once to `0x9A` balance
  stand. Repeating zero packets is intentionally suppressed afterward. The
  first nonzero command sends `0x8A` once, then immediately sends continuous
  four-axis SDK remote packets (the fourth head-angle axis stays zero); when
  the command returns to zero, the
  backend sends one zero remote packet, waits for it to settle, and sends
  `0x9A` once more.

Arm:

- Right grip is the arm deadman. Values at or above `0.5` enable motion.
- In `pose` mode, the default, right-controller pose is used as a relative
  6DoF source. On grip engagement the controller pose and current arm end pose
  are anchored together; subsequent movement sends a relative Cartesian target.
- Translation and orientation are mapped one-to-one from the grip anchor. The
  controller-to-AIRBOT frame rotation follows the official XRoboToolkit
  sample. There is no local translation clamp, rotation clamp, or Cartesian
  target rate limiter; workspace limits are left to the AIRBOT controller.
- In `joystick` mode, right joystick Y/X map to end-effector X/Y velocity.
- While right grip is engaged, right trigger maps linearly to gripper opening
  from `0` to `0.072`. The gripper starts at and holds `0.036` when no target
  has been set. Releasing the grip sends arm hold, clears the pose anchor, and
  keeps the last gripper target.
- Both pose and joystick arm modes are enabled only in global motion mode.
- In motion mode, pressing the right joystick click commands arm return-zero
  once per press. It is ignored while right grip is held, which prevents an
  accidental home motion during pose teleoperation.

The mapping uses a `0.12` joystick deadzone and rescales the remaining travel.
Initial output limits are deliberately conservative:

- dog forward: `0.50`
- dog lateral: `0.30`
- dog rotation: `0.50`
- arm Cartesian target rate: one-to-one controller tracking with no local slew

Dog values are dimensionless L1-W remote-axis commands, not SI velocities.
The three dog-axis scales can be overridden per run with
`--dog-forward-scale`, `--dog-lateral-scale`, and `--dog-rotate-scale`
(each from 0 through 1). Keep the official sample value `0.5` as the initial
walk-test setting unless hardware feedback shows that packets are being
accepted and the dog remains stationary.

## Safety gating

Commands are disabled when any of these is true:

1. The process has not passed its startup hold, two seconds by default.
2. PICO input is stale beyond `--stale-after`.
3. The corresponding deadman is released.
4. Input contains a non-finite number; the input monitor replaces it with zero.

On shutdown, trace and future hardware modes send the safe dog zero command and
arm hold command. Monitor mode intentionally never opens a hardware client.

## Run

Read-only:

```sh
PYTHONPATH=. python3 -m l1w_teleop --source xrt --command-mode monitor
```

Mock dispatch and printed command trace:

```sh
PYTHONPATH=. python3 -m l1w_teleop --source xrt --command-mode trace
```

The default arm backend is mock. To observe the real AIRBOT service without
acquiring control or sending a command:

```sh
PYTHONPATH=. python3 -m l1w_teleop --source xrt --command-mode monitor \
  --arm-backend airbot --arm-host localhost --arm-port 50051
```

Joystick-only arm debugging:

```sh
PYTHONPATH=. python3 -m l1w_teleop --source xrt --command-mode trace \
  --arm-mode joystick
```

Before enabling a hardware adapter, verify with the PICO in hand: left trigger
release, right grip release, left joystick deadzone, right joystick deadzone,
and the displayed command signs.
