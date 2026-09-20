# AIRBOT read-only bring-up

The AIRBOT adapter is intentionally split into read-only and motion paths.

- `AirbotArmClient.get_end_pose()` only reads the official SDK state.
- `scripts/airbot/airbot_probe.py` never calls `acquire_control`.
- `enable_control()` is a separate method; every motion method raises before it
  is explicitly called.
- The first control version uses `Controller.servo_control`, Cartesian pose
  targets, and a clamped gripper target. It does not apply an additional
  client-side motor-speed cap; the AIRBOT service retains its configured
  limits.

Run the read-only probe on the machine connected to the arm service:

```sh
cd ~/ws-motphys/l1w-airbot
PYTHONPATH=. python scripts/airbot/airbot_probe.py --host localhost --port 50051
```

The first hardware-control test should only acquire control, hold the current
pose, and release/close the client:

```sh
PYTHONPATH=. python scripts/airbot/airbot_hold_test.py --duration 5 \
  --i-understand-this-will-energize-the-arm
```

The script uses servo mode and repeatedly holds the pose read immediately
before control is enabled. It does not follow the PICO or return to zero.
Cartesian tracking and return-zero should be separate tests after this one.

This robot uses a G2 gripper. Its SDK travel range is `0.0` to `0.072` meters;
the adapter clamps every gripper target to that range. The arm service may
report firmware gripper type `NULL` and print a validation warning. That
warning is harmless for G2 because the adapter has already applied the G2
limit before sending the command.

## Optional ready-pose helper

Hardware teleoperation can start from the zero pose; the runtime does not
require a joint-pose gate. For a manually controlled, more comfortable bent
starting pose, use:

```sh
PYTHONPATH=. python scripts/airbot/airbot_ready_pose_test.py --duration 6 \
  --i-understand-this-will-move-the-airbot
```

The target joint pose is `(0, -0.45, 0.85, -0.75, -0.5, 0)` radians. This step
is optional and is not a precondition for PICO tracking. Keep people and
fixtures clear while the arm moves.

## PICO tracking run

Hardware teleoperation uses the real PICO, pose mode, and AIRBOT only; the dog
remains a mock. Translation and orientation follow the controller one-to-one
from the grip anchor, matching the official XRoboToolkit sample. There is no
local translation workspace clamp, rotation clamp, or Cartesian target slew
limiter; those limits are left to the AIRBOT controller. Return-zero is
and return-zero is disabled. The run continues until Ctrl+C/SIGTERM by default;
pass `--duration N` only when an explicit finite test window is wanted. The
client only sends `move_end_pose` after the target has moved by at least 1 mm,
which keeps the SDK from repeatedly re-solving an essentially unchanged
Cartesian target.

```sh
PYTHONPATH=. python -m l1w_teleop --source xrt --command-mode hardware \
  --arm-backend airbot --arm-mode pose
```

The defaults are 50 Hz, locked end orientation, and one-to-one scale. If a
direction is wrong or tracking is too aggressive, temporarily reduce only
`--arm-pose-scale`; restoring this flag to `1.0` returns to one-to-one mapping.

```sh
PYTHONPATH=. python -m l1w_teleop --source xrt --command-mode hardware \
  --arm-backend airbot --arm-mode pose --arm-pose-scale 0.5
```

The log prints commanded `arm p=...`, measured `armcur=...`, and
`tracking_error`. Use one axis at a time. If command and measurement agree but
the robot feels wrong, tune the mapping; if command and measurement diverge,
the AIRBOT servo/controller needs tuning instead.

Pose mode also maps relative right-controller orientation. The controller
quaternion is transformed from XRoboToolkit's VR frame, converted to a relative
rotation from the grip anchor, and applied one-to-one to the AIRBOT
end-effector orientation. Releasing right grip resets the orientation anchor
just as it resets the translation anchor.

Orientation tracking can be enabled during debugging with
`--no-lock-arm-orientation`. Locked orientation holds the
SDK return-zero end orientation and maps the controller only to target
position. Releasing and re-engaging the grip re-anchors translation only; the
locked orientation does not change. A fixed horizontal-gripper quaternion at
the exact zero-pose branch was tested and rejected by the controller IK; do
not restore it unless the arm is already in a non-singular bent pose.

Procedure: put the headset on and confirm the input is `OK`, press left X to
enter motion mode, then press right grip to anchor and track. Release right
grip to hold. Right B returns to damping and only disables commands; it does
not invoke any dog backend in hardware arm mode.
