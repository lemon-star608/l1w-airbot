# PICO 4 input setup

This guide connects the PICO controllers to the read-only Python monitor. It
does not connect the dog or arm, acquire control, or send a motion command.

## Current program

On Ubuntu 20.04 and Ubuntu 22.04:

```bash
cd ~/ws-motphys/l1w-airbot
PYTHONPATH=. python3 -m l1w_teleop --source mock --rate 50
```

Use `Ctrl+C` to stop. The output contains left/right pose, grip, trigger, and
joystick. The dog/arm columns currently count mock safe-state calls only.

## What runs on the robot

```text
PICO 4 Ultra + XRoboToolkit APK
  -> Wi-Fi -> NX Ubuntu 22.04
  -> XRoboToolkit PC-Service
  -> xrobotoolkit_sdk Python binding
  -> python3 -m l1w_teleop --source xrt
```

The Python process pulls controller state from the official pybind binding.
The PICO does not talk to the dog or AIRBOT SDK directly.

## Prepare the headset

1. Charge both controllers and pair them in the PICO settings.
2. Put the headset and NX on the same 5 GHz Wi-Fi network. If the dog hotspot
   is the only network, connect the NX to that hotspot and use the address the
   NX receives on that network.
3. Find the NX address:

```bash
hostname -I
ip addr show
```

4. Install `XRoboToolkit-PICO-1.1.1.apk` on the headset. The APK is in
   `~/ws-motphys/vendor/binaries/` on the development machine. Use the SDK29
   variant only if the normal APK fails to start.
5. Open the app on the headset, enter the NX IP, and use controller input.
   Camera streaming is not needed for this task.

## Install PC-Service on NX

The robot NX uses the ARM64 headless package. Deploy it with the checked-in
one-time script, which also builds the ARM64 Python binding and installs the
systemd service:

```bash
./scripts/nx/nx_deploy_pico_runtime.sh robot@192.168.234.234
```

See `docs/nx-pico-teleop-runbook.md` for service checks and the full daily
bring-up procedure. Keep a foreground `tmux` run only when debugging a service
failure.

For a no-sudo trial on this development machine:

```bash
mkdir -p /tmp/roboticsservice-extract
dpkg-deb -x ~/ws-motphys/vendor/binaries/XRoboToolkit_PC_Service_1.0.0_ubuntu_22.04_amd64.deb \
  /tmp/roboticsservice-extract
DIR=/tmp/roboticsservice-extract/opt/apps/roboticsservice
LD_LIBRARY_PATH=$DIR:$DIR/lib:$DIR/SDK/x64 \
QT_PLUGIN_PATH=$DIR/plugins/ QT_QML_PATH=$DIR/qml/ \
$DIR/RoboticsServiceProcess
```

PC-Service listens on TCP 63901 for the PICO client and localhost TCP 60061
for the Python binding. UDP 29888 is used for local discovery.

Check that the process is alive:

```bash
pgrep -af RoboticsServiceProcess
```

## Build the Python binding on NX

Ubuntu 22.04's system Python is 3.10. Use the same Python environment for the
build and for `l1w_teleop`.

```bash
sudo apt install -y build-essential python3-dev python3-pip
cd ~/ws-motphys/vendor/pybind-repo
mkdir -p lib/aarch64 include/aarch64
cp /opt/apps/roboticsservice/SDK/arm64/libPXREARobotSDK.so lib/aarch64/
cp /opt/apps/roboticsservice/SDK/include/PXREARobotSDK.h include/aarch64/
cp -r ../include/nlohmann include/aarch64/nlohmann
python3 -m pip install pybind11
python3 -m pip uninstall -y xrobotoolkit_sdk
python3 setup.py install
```

On this development machine, the binding was built into the `airbot` conda
environment with:

```bash
cd ~/ws-motphys/vendor/pybind-repo
mkdir -p lib/x64 include/x64
cp /tmp/roboticsservice-extract/opt/apps/roboticsservice/SDK/x64/libPXREARobotSDK.so lib/x64/
cp /tmp/roboticsservice-extract/opt/apps/roboticsservice/SDK/include/PXREARobotSDK.h include/x64/
cp -r ../include/nlohmann include/x64/nlohmann
ln -sfn x64/libPXREARobotSDK.so lib/libPXREARobotSDK.so
cmake -S . -B /tmp/xrt-pybind-build \
  -Dpybind11_DIR=$HOME/miniconda3/envs/airbot/lib/python3.10/site-packages/pybind11/share/cmake/pybind11 \
  -DPYTHON_EXECUTABLE=$HOME/miniconda3/envs/airbot/bin/python \
  -DCMAKE_BUILD_TYPE=Release
cmake --build /tmp/xrt-pybind-build -j2
cp /tmp/xrt-pybind-build/xrobotoolkit_sdk*.so \
  $HOME/miniconda3/envs/airbot/lib/python3.10/site-packages/
```

Do not run `setup_orin.sh`; it downloads a large PC-Service source tree that
the headless package already provides.

Verify the import:

```bash
python3 - <<'PY'
import xrobotoolkit_sdk as xrt
print("xrobotoolkit_sdk import OK")
PY
```

## Run the real controller monitor

With PC-Service still running:

```bash
cd ~/ws-motphys/l1w-airbot
PYTHONPATH=. python3 -m l1w_teleop --source xrt --rate 50 --duration 0
```

Expected observations:

- both controller poses change when the controllers move;
- left/right joystick values change;
- grips and triggers sweep from 0.00 to 1.00;
- moving a controller out of tracking range or putting the headset to sleep
  eventually reports `STALE`.

The current stale detector uses the SDK timestamp plus a check that every input
value is bit-identical. Once real hardware is available, log a full disconnect
test before trusting the timeout value. A practical first value is 250-500 ms;
this repository defaults to 300 ms.
