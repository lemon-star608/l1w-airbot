# PICO L1-W + AIRBOT 遥操作

English documentation is in [`README.md`](README.md).

本项目运行在 GENISOM L1-W 机器狗机内的 NX 计算单元上。它使用 PICO 4 Ultra
手柄作为输入源，通过 GENISOM L1-W SDK 的 UDP 入口控制机器狗，并通过官方
AIRBOT gRPC 服务控制 AIRBOT Play G2 机械臂。

## 系统架构

```text
PICO XRoboToolkit App -> NX 192.168.234.234 TCP 63901
NX PC-Service         -> xrobotoolkit_sdk localhost TCP 60061
NX l1w_teleop         -> 狗控制器 / 3588 192.168.234.1 UDP 8081
NX l1w_teleop         -> 本机 AIRBOT 服务 TCP 50051
NX can1               -> DISCOVER USB-CAN -> AIRBOT 机械臂
```

NX 地址是 `robot@192.168.234.234`。3588 狗控制器地址是 `192.168.234.1`。
不要把狗控制命令指向 NX 自身。

## 软件组成

项目使用三套相互独立的 SDK。它们的安装位置和职责不要混淆。

### GENISOM L1-W 机器狗 SDK

- 源码位置：`third_party/genisom_L1_sdk`，是固定版本的 git submodule。
- 运行协议：UDP JSON。NX 向 3588 狗控制器的 `192.168.234.1:8081` 发送命令，
  并在本地 UDP 8080 接收状态。
- Python 遥操作程序直接实现该协议，不需要在 NX 上额外安装 GENISOM 软件包。
- 可选的 C++ `status_monitor` 链接 submodule 中的预编译 `libzsibot.a`。它只是
  对照诊断工具，不属于日常遥操作链路。
- 初始化命令：

```bash
git submodule update --init --recursive
```

### AIRBOT Play G2 服务端与 Python SDK

当前 NX 上已经安装：

- 服务端：`airbot-arm 5.2.5`，可执行文件 `/usr/bin/airbot-arm`，gRPC 端口
  `50051`。
- Python 客户端：`arm_sdk 5.2.3`，Python 导入名是 `arm_sdk`。
- 运行依赖：`grpcio` 和兼容的 protobuf 运行时。
- IK、限位、规划和 servo 指令超时保护都在 AIRBOT 服务端完成。本仓库不实现
  机械臂 IK。
- AIRBOT 服务没有 systemd unit，必须在确认现场安全后手动启动。

开发机上的恢复包位置：

```text
/home/lemon/下载/airbot_arm_release/product/aarch64/jammy/airbot-arm_5.2.5_arm64.deb
/home/lemon/下载/dist/aarch64/arm_sdk-5.2.3-py3-none-any.whl
```

在全新 NX 上重装：

```bash
sudo apt install -y ./airbot-arm_5.2.5_arm64.deb
python3 -m pip install --user ./arm_sdk-5.2.3-py3-none-any.whl
```

安装后验证导入：

```bash
python3 -c 'import arm_sdk, grpc, google.protobuf; print(arm_sdk.version(), grpc.__version__, google.protobuf.__version__)'
```

如果导入失败，按 `docs/airbot-runtime.md` 中的版本要求安装兼容的
`grpcio`/`protobuf`，或从当前可用 NX 复制 `~/.local` 下已经验证过的包。

### XRoboToolkit PICO 输入链路

PC-Service 和 PICO App 只提供手柄输入，不直接控制狗或机械臂。

- PICO App：`XRoboToolkit-PICO-1.1.1.apk`，安装在头显上。
- NX 服务：`XRoboToolkit-PC-Service-headless_1.0.0.0_arm64.deb`，安装到
  `/opt/apps/roboticsservice`。
- Python binding：在 NX 上使用官方 pybind 源码编译。它链接 PC-Service deb
  内置的 `libPXREARobotSDK.so`。
- 编译依赖：pybind 源码、`nlohmann/json.hpp`、离线 pybind11 wheel。部署脚本
  会自动复制这些依赖。
- 端口：PICO App 连接 NX TCP `63901`；Python binding 连接 localhost TCP
  `60061`。

开发机上的产物位置：

```text
/home/lemon/ws-motphys/vendor/binaries/XRoboToolkit-PICO-1.1.1.apk
/home/lemon/ws-motphys/vendor/binaries/XRoboToolkit-PC-Service-headless_1.0.0.0_arm64.deb
/home/lemon/ws-motphys/vendor/pybind-repo
/home/lemon/ws-motphys/vendor/include/nlohmann
/home/lemon/ws-motphys/vendor/wheels/aarch64/pybind11-2.13.6-py3-none-any.whl
```

不要运行 pybind 仓库的 `setup_orin.sh`。它会下载庞大的 PC-Service 源码树；
headless deb 已经提供所需的 SDK 库和头文件。

## NX 一次性部署

在开发机上执行：

```bash
./scripts/nx/nx_deploy_pico_runtime.sh robot@192.168.234.234
```

脚本会安装 arm64 PC-Service，为 NX Python 3.10 编译 `xrobotoolkit_sdk`，并启用
`xrobo-pc-service`。AIRBOT CAN 持久化单独执行：

```bash
./scripts/nx/nx_airbot_can_setup.sh robot@192.168.234.234
```

部署脚本要求 `robot` 用户可以免密 sudo。全新 NX 上先配置一次：

```bash
ssh robot@192.168.234.234
echo 'robot ALL=(ALL) NOPASSWD: ALL' | sudo tee /etc/sudoers.d/robot
sudo chmod 440 /etc/sudoers.d/robot
```

NX 还需要 `cmake`、`g++`、Python 3.10 和
`/usr/include/python3.10/Python.h`。Ubuntu 的 `build-essential`、`cmake`、
`python3-dev` 可以提供这些依赖。

部署结果：

```text
~/ws/pico-L1W                 项目源码和脚本
/opt/apps/roboticsservice     PC-Service arm64 安装目录
xrobo-pc-service.service      PC-Service systemd 服务
airbot-can1.service           DISCOVER USB-CAN 的 can1 持久化服务
~/.local/lib/python3.10/site-packages/xrobotoolkit_sdk*.so
```

部署完成后，PICO App 填 `192.168.234.234`。不要填 `192.168.234.1`，
那是 3588 狗控制器。

## 真机使用

详细流程见 [`docs/nx-pico-teleop-runbook.md`](docs/nx-pico-teleop-runbook.md)。
以下是核心步骤。

1. SSH 到 NX：

```bash
ssh robot@192.168.234.234
```

2. 确认持久化服务和 CAN 接口：

```bash
systemctl is-active airbot-can1 xrobo-pc-service
ip -brief link show can1
pgrep -af RoboticsServiceProcess
```

3. 戴上头显，打开 XRoboToolkit App，连接 `192.168.234.234`。

4. 在一个保持打开的 NX 会话中启动 AIRBOT 服务：

```bash
sudo airbot-arm --address 127.0.0.1:50051 -i can1 -t airbot_play_g2 --no-return
```

5. 在另一个 NX 会话中执行只读检查：

```bash
cd ~/ws/pico-L1W
PYTHONPATH=. python3 scripts/airbot/airbot_probe.py --host localhost --port 50051
PYTHONPATH=. python3 -m l1w_teleop \
  --source xrt --command-mode monitor \
  --dog-backend l1w-status --arm-backend airbot \
  --rate 50 --duration 0
```

必须确认 PICO 输入显示 `OK`，狗状态 connected，机械臂状态可读，然后才能继续。

6. 启动狗和机械臂联合硬件遥操作：

```bash
cd ~/ws/pico-L1W
PYTHONPATH=. python3 -m l1w_teleop \
  --source xrt --command-mode hardware \
  --dog-backend l1w --arm-backend airbot --arm-mode pose \
  --duration 0
```

操作方式：

- 左手 X：机器狗站立并进入运动模式。
- 左扳机：机器狗 deadman。
- 左摇杆：控制机器狗；松开左扳机后狗速度归零。
- 右握把：机械臂 deadman 和笛卡尔位置锚点。
- 右扳机：控制夹爪张开。
- 右手 B：机器狗进入 damping。
- Ctrl+C：先按右手 B 并松开两个 deadman，再停止 `l1w_teleop`。

机械臂和机器狗是分时控制，不允许同时运动。按住右握把时，狗会先停止并稳定；
只有松开机械臂 deadman 后，左扳机和左摇杆才能继续控制狗。停止顺序是先停
`l1w_teleop`，再停 `airbot-arm`。

新部署后的第一次真机测试建议加时间限制并降低狗速度：

```bash
--duration 10 --dog-forward-scale 0.25 \
--dog-lateral-scale 0.15 --dog-rotate-scale 0.25
```

保持手持安全遥控器可用，并清空运动区域。上述命令会控制真实硬件。

## 仓库结构

- `l1w_teleop/`：Python 遥操作运行时，包含输入映射和安全逻辑。
- `src/status_monitor.cpp`：基于官方 GENISOM 预编译 SDK 的 C++ 对照读数工具。
  它绑定 UDP 8080，不能和 Python 狗客户端同时运行。
- `scripts/nx/`：NX 一次性部署和持久化服务配置。
- `scripts/airbot/`：AIRBOT 只读探测和显式确认的硬件测试。
- `scripts/l1w/`：显式确认的 L1-W 零速和站立测试。
- `tests/python/`：单元测试和运行时测试。
- `docs/`：操作手册和命令映射。
- `docs/archive/`：历史设计文档和已废弃的硬件记录。
- `third_party/genisom_L1_sdk`：官方 SDK submodule。

## 开发

构建 C++ 对照工具：

```bash
git submodule update --init --recursive
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
```

运行 Python 测试：

```bash
PYTHONPATH=. python3 -m unittest discover -s tests/python -t . -v
```

`xrobotoolkit_sdk`、`arm_sdk` 和 `l1w_teleop` 必须使用同一个 Python 环境。
NX 上是 `/usr/bin/python3.10`，不要和 Conda 环境混用。

## 安全边界

程序默认是 monitor 模式，不会分发控制命令。真实运动必须显式选择 hardware
模式和真实后端。硬件测试时保持手持安全遥控器可用，并确保运动区域无人和障碍物。AIRBOT 使用
`can1`，不使用 NX 板载 CAN `can0`。

历史设计记录在 `docs/archive/ROADMAP-2026-09.md`。当前操作流程以 `docs/`
中的文档为准。
