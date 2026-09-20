# PICO L1-W + AIRBOT 遥操作

English documentation is in [`README.md`](README.md).

本项目运行在 GENISOM L1-W 机器狗机内的 NX 计算单元上。PICO 4 Ultra 手柄
作为输入源，通过 GENISOM L1-W UDP 协议控制机器狗，并通过官方 AIRBOT gRPC
服务控制 AIRBOT Play G2 机械臂。

## 系统架构

```text
PICO XRoboToolkit App -> NX 192.168.234.234 TCP 63901
NX PC-Service         -> xrobotoolkit_sdk localhost TCP 60061
NX l1w_teleop         -> 3588 狗控制器 192.168.234.1 UDP 8081
NX l1w_teleop         -> 本机 AIRBOT 服务 TCP 50051
NX can1               -> DISCOVER USB-CAN -> AIRBOT 机械臂
```

NX 地址是 `robot@192.168.234.234`。3588 狗控制器地址是 `192.168.234.1`，
不要把狗控制命令指向 NX 自身。PICO App 必须连接 `192.168.234.234`，不要填
`192.168.234.1`。

项目源码已经部署在 NX 的 `~/ws/pico-L1W`。PC-Service 和 AIRBOT CAN 接口是
持久化 systemd 服务；AIRBOT gRPC 服务保持手动启动，由操作者先确认现场安全
再给机械臂上电控制。

## 需要的 SDK

NX 运行环境已经安装并配置好以下互相独立的软件栈：

| 软件栈 | 安装位置 | 用途 | 参考链接 |
| --- | --- | --- | --- |
| GENISOM L1-W SDK | 本仓库固定版本 submodule | 狗 UDP 协议、状态解析和可选 C++ 诊断 | [zsibot/genisom_L1_sdk](https://github.com/zsibot/genisom_L1_sdk) |
| AIRBOT Play 服务端和 Python SDK | NX | 机械臂 gRPC 服务、IK、限位、规划和 Python 客户端 | [AIRBOT 文档](https://docs.discover-robotics.com) |
| XRoboToolkit PC-Service | NX `/opt/apps/roboticsservice` | PICO 输入传输 | [X-Robotics/XRoboToolkit-PC-Service](https://github.com/X-Robotics/XRoboToolkit-PC-Service) |
| XRoboToolkit Python binding | NX Python 3.10 用户包 | 读取手柄状态 | [X-Robotics/XRoboToolkit-PC-Service-Pybind](https://github.com/X-Robotics/XRoboToolkit-PC-Service-Pybind) |
| XRoboToolkit PICO App | PICO 头显 | 手柄输入和连接界面 | [XR-Robotics/XRoboToolkit-Unity-Client-Quest](https://github.com/XR-Robotics/XRoboToolkit-Unity-Client-Quest) |

当前部署版本为 `airbot-arm 5.2.5`、`arm-sdk 5.2.3`、XRoboToolkit PICO App
`1.1.1`。`xrobotoolkit_sdk`、`arm_sdk` 和 `l1w_teleop` 必须使用同一个 Python
环境；NX 上是系统 Python 3.10。

L1-W SDK 以 git submodule 形式包含在仓库中。开发机上需要构建可选 C++ 诊断
工具时初始化：

```bash
git submodule update --init --recursive
```

## 每次启动流程

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

`--no-return` 用于避免服务退出时自动命令机械臂回零。

5. 每次遥操作前都先把机械臂回零位。硬件模式会把笛卡尔姿态锁定为 SDK 零位
   四元数 `(0, 0, 0, 1)`；如果机械臂从弯曲位姿启动，第一条命令可能无 IK 解：

```bash
export PATH="$HOME/.local/bin:$PATH"
arm-sdk examples run airbot_example_return_zero
```

这一步会让机械臂真实运动。请清空人员和障碍物，并等关节读数接近零后再继续。

6. 在另一个 NX 会话中执行只读检查：

```bash
cd ~/ws/pico-L1W
PYTHONPATH=. python3 scripts/airbot/airbot_probe.py --host localhost --port 50051
PYTHONPATH=. python3 -m l1w_teleop \
  --source xrt --command-mode monitor \
  --dog-backend l1w-status --arm-backend airbot \
  --rate 50 --duration 0
```

必须确认 PICO 输入显示 `OK`，狗状态 connected，机械臂状态可读，然后才能继续。

7. 启动狗和机械臂联合硬件遥操作：

```bash
cd ~/ws/pico-L1W
PYTHONPATH=. python3 -m l1w_teleop \
  --source xrt --command-mode hardware \
  --dog-backend l1w --arm-backend airbot --arm-mode pose \
  --duration 0
```

默认值为 50 Hz、锁定零位姿态、PICO 平移一比一映射。NX 上 `--arm-host` 默认
localhost，`--dog-host` 默认 `192.168.234.1`。

## 操作和停止顺序

- 左手 X：机器狗站立并进入运动模式。
- 左扳机：机器狗 deadman。
- 左摇杆：控制机器狗；松开左扳机后狗速度归零。
- 右握把：机械臂 deadman 和笛卡尔位置锚点。
- 右扳机：控制夹爪张开。
- 右手 B：机器狗进入 damping。
- Ctrl+C：先按右手 B 并松开两个 deadman，再停止 `l1w_teleop`。

机械臂和机器狗是分时控制。按住右握把时，狗会先停止并稳定；只有松开机械臂
deadman 后，左扳机和左摇杆才能继续控制狗。停止顺序是先停 `l1w_teleop`，
再停 `airbot-arm`。

早期测试可以限制时长并降低狗速度，例如：

```bash
--duration 10 --dog-forward-scale 0.25 \
--dog-lateral-scale 0.15 --dog-rotate-scale 0.25
```

保持手持安全遥控器可用，并清空运动区域。上述命令会控制真实硬件。

## 仓库结构

- `l1w_teleop/`：Python 遥操作运行时，包含输入映射和安全逻辑。
- `src/status_monitor.cpp`：基于官方 GENISOM 预编译 SDK 的 C++ 对照读数工具。
  它绑定 UDP 8080，不能和 Python 狗客户端同时运行。
- `scripts/airbot/`：AIRBOT 只读探测和显式确认的硬件测试。
- `scripts/l1w/`：显式确认的 L1-W 零速和站立测试。
- `tests/python/`：单元测试和运行时测试。
- `docs/`：操作手册和命令映射。
- `docs/archive/`：历史设计文档和已废弃的硬件记录。
- `third_party/genisom_L1_sdk`：官方 SDK submodule。

## 开发

构建可选 C++ 对照工具：

```bash
git submodule update --init --recursive
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
```

运行 Python 测试：

```bash
PYTHONPATH=. python3 -m unittest discover -s tests/python -t . -v
```

## 安全边界

程序默认是 monitor 模式，不会分发控制命令。真实运动必须显式选择 hardware
模式和真实后端。硬件测试时保持手持安全遥控器可用，并确保运动区域无人和
障碍物。AIRBOT 使用 `can1`，不使用 NX 板载 CAN `can0`。
