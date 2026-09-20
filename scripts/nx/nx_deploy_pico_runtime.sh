#!/usr/bin/env bash
set -euo pipefail

HOST="${1:-robot@192.168.234.234}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENDOR_ROOT="${VENDOR_ROOT:-$(cd "$REPO_ROOT/.." && pwd)/vendor}"
DEB="$VENDOR_ROOT/binaries/XRoboToolkit-PC-Service-headless_1.0.0.0_arm64.deb"
PYBIND="$VENDOR_ROOT/pybind-repo"
WHEELS="$VENDOR_ROOT/wheels/aarch64"

for required in "$DEB" "$PYBIND" "$VENDOR_ROOT/include/nlohmann/json.hpp" \
  "$VENDOR_ROOT/include/nlohmann/json_fwd.hpp" \
  "$WHEELS/pybind11-2.13.6-py3-none-any.whl"; do
  if [ ! -e "$required" ]; then
    echo "Missing deployment input: $required" >&2
    exit 1
  fi
done

ssh "$HOST" 'sudo -n true'
ssh "$HOST" '
set -e
command -v cmake >/dev/null
command -v g++ >/dev/null
command -v python3 >/dev/null
test -f /usr/include/python3.10/Python.h
python3 - <<"PY"
import sys
if sys.version_info[:2] != (3, 10):
    raise SystemExit("NX Python must be 3.10, got " + sys.version.split()[0])
PY
'
ssh "$HOST" 'mkdir -p ~/ws/vendor/wheels ~/ws/pico-L1W'

rsync -az --chmod=Fu=rw,Fg=r,Fo=r "$DEB" "$HOST:/tmp/"
rsync -az --delete \
  --exclude .git/ --exclude build/ --exclude __pycache__/ --exclude .cache/ \
  "$PYBIND"/ "$HOST:~/ws/vendor/pybind-repo/"
rsync -az "$VENDOR_ROOT/include"/ "$HOST:~/ws/vendor/include/"
rsync -az "$WHEELS"/ "$HOST:~/ws/vendor/wheels/"
rsync -az \
  --exclude .git/ --exclude build/ --exclude __pycache__/ --exclude .cache/ \
  --exclude .pytest_cache/ --exclude logs/ --exclude airbot_logs/ \
  "$REPO_ROOT"/ "$HOST:~/ws/pico-L1W/"

# The headless deb's desktop-icon postinst can fail on a robot image. If that
# happens, remove the half-configured dpkg entry and install the payload directly.
if ! ssh "$HOST" 'sudo -n dpkg -i /tmp/XRoboToolkit-PC-Service-headless_1.0.0.0_arm64.deb'; then
  ssh "$HOST" '
set -e
sudo -n dpkg --purge roboticsservice >/dev/null 2>&1 || true
tmp="/tmp/xrobo-pc-service-$(date +%Y%m%d%H%M%S)"
mkdir -p "$tmp"
dpkg-deb -x /tmp/XRoboToolkit-PC-Service-headless_1.0.0.0_arm64.deb "$tmp"
test -x "$tmp/opt/apps/roboticsservice/RoboticsServiceProcess"
sudo -n install -d -m 0755 /opt/apps
sudo -n cp -a "$tmp/opt/apps/roboticsservice" /opt/apps/
test -x /opt/apps/roboticsservice/RoboticsServiceProcess
'
fi

ssh "$HOST" '
set -e
test -x /opt/apps/roboticsservice/RoboticsServiceProcess
sudo -n install -d -m 0755 /usr/local/lib
sudo -n ln -sfn /opt/apps/roboticsservice/SDK/arm64/libPXREARobotSDK.so \
  /usr/local/lib/libPXREARobotSDK.so
sudo -n ldconfig

cd ~/ws/vendor/pybind-repo
mkdir -p lib/aarch64 include/aarch64
cp /opt/apps/roboticsservice/SDK/arm64/libPXREARobotSDK.so lib/aarch64/
cp /opt/apps/roboticsservice/SDK/include/PXREARobotSDK.h include/aarch64/
cp ../include/nlohmann/json.hpp ../include/nlohmann/json_fwd.hpp include/aarch64/
python3 -m pip install --user --no-index --no-deps \
  ../wheels/pybind11-2.13.6-py3-none-any.whl
python3 -m pip uninstall -y xrobotoolkit_sdk >/dev/null 2>&1 || true
cmake -E remove_directory build-nx
cmake -S . -B build-nx -DCMAKE_BUILD_TYPE=Release \
  -Dpybind11_DIR="$(python3 -m pybind11 --cmakedir)" \
  -DPYTHON_EXECUTABLE="$(command -v python3)"
cmake --build build-nx -j2
install -d "$HOME/.local/lib/python3.10/site-packages"
cp build-nx/xrobotoolkit_sdk*.so "$HOME/.local/lib/python3.10/site-packages/"
python3 -c "import xrobotoolkit_sdk; print(xrobotoolkit_sdk.__file__)"
'

"$SCRIPT_DIR/nx_pico_service_setup.sh" "$HOST"
