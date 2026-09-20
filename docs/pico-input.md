# PICO 4 input

This document describes the deployed PICO input path. It does not describe
package installation or build the input stack.

```text
PICO 4 Ultra + XRoboToolkit app
  -> Wi-Fi -> NX 192.168.234.234 TCP 63901
  -> XRoboToolkit PC-Service
  -> xrobotoolkit_sdk Python binding
  -> python3 -m l1w_teleop --source xrt
```

The Python process pulls controller state from the official pybind binding.
The PICO does not talk to the dog or AIRBOT SDK directly.

## Connect the headset

1. Charge both controllers and pair them in the PICO settings.
2. Keep the headset and NX on the same network. On the robot hotspot this is
   the dog network; the NX address is `192.168.234.234`.
3. Open the XRoboToolkit app, enter `192.168.234.234`, and connect. Camera
   streaming is not needed for teleoperation.

PC-Service listens on TCP 63901 for the PICO client and localhost TCP 60061
for the Python binding. UDP 29888 is used for local discovery.

## Verify controller input

On the NX:

```bash
cd ~/ws/pico-L1W
PYTHONPATH=. python3 -m l1w_teleop \
  --source xrt --command-mode monitor \
  --rate 50 --duration 0
```

Expected observations:

- both controller poses change when the controllers move;
- left/right joystick values change;
- grips and triggers sweep from 0.00 to 1.00;
- moving a controller out of tracking range or putting the headset to sleep
  eventually reports `STALE`.

The stale detector uses the SDK timestamp plus a check that every input value
is bit-identical. The practical timeout is 250-500 ms; this repository uses
300 ms.
