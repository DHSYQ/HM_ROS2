# 00 — 数据链路：Windows ↔ WSL2 舵机桥接

## 整体架构

```
┌──────────────────────────────────────────────────┐        ┌────────────────────────────────────┐
│              Windows (主机)                       │        │         WSL2 Ubuntu (虚拟机)          │
│                                                  │  TCP   │                                    │
│  servo_server.py    (唯一操作 COM7，端口 :9555)    │        │                                    │
│       ↑                                          │        │                                    │
│  servo_bridge.py    (读写合一，通过 servo_client)  │        │  r02_servo_bridge_node.cpp          │
│    ├─ :5005 ──── 读取角度 ────────────────→       │        │    ↓ 发布 /joint_states             │
│    └─ :5006 ←─── 接收命令 ────────────────        │        │  r03_servo_cmd_node.cpp             │
│                                                  │        │    ↑ 订阅 /joint_command            │
└──────────────────────────────────────────────────┘        └────────────────────────────────────┘
```

## 端口总览

| 端口 | 用途 | 方向 |
|------|------|------|
| 9555 | `servo_server.py` 内部 API | Windows 内部 |
| 5005 | 读取舵机角度 | Windows → WSL2 |
| 5006 | 发送舵机命令 | WSL2 → Windows |

## 启动顺序

### Windows 端

```powershell
# 终端1 — 舵机服务（唯一操作 COM7 的程序）
python servo_server.py

# 终端2 — 桥接服务（读写合一）
python servo_bridge.py
```

### WSL2 端

```bash
# 终端1 — 读取角度，发布 /joint_states
ros2 run r01_test_package r02_servo_bridge_node

# 终端2 — 发送命令，订阅 /joint_command
ros2 run r01_test_package r03_servo_cmd_node
```

## 读取链路（Windows → WSL2）

```
舵机 COM7 → servo_server.py → servo_client → servo_bridge.py(:5005) ─TCP→ r02_servo_bridge_node → /joint_states
```

1. `servo_server.py` 通过串口读取舵机角度
2. `servo_bridge.py` 通过 `servo_client.read_student()` 获取角度
3. 打包成 JSON：`{"timestamp": 1.23, "angles": {"1": 45.0, "2": -30.0, ...}}`
4. 协议格式：`[4字节长度前缀] + [JSON 数据]`
5. `r02_servo_bridge_node` 接收后发布到 `/joint_states`（`sensor_msgs/JointState`）

## 命令链路（WSL2 → Windows）

```
/joint_command → r03_servo_cmd_node ─TCP→ servo_bridge.py(:5006) → servo_client.write_angle() → servo_server.py → COM7 → 舵机
```

1. 其他 ROS2 节点发布 `std_msgs/Float64MultiArray` 到 `/joint_command`（6 个角度值，单位：度）
2. `r03_servo_cmd_node` 收到后打包 JSON：`{"cmd": "write_angles", "angles": [45, -30, ...]}`
3. 通过 TCP `:5006` 发给 Windows
4. `servo_bridge.py` 调用 `servo_client.write_angle(id, angle)` 写入舵机

### 测试命令

```bash
ros2 topic pub /joint_command std_msgs/msg/Float64MultiArray "{data: [45.0, -30.0, 10.0, 0.0, -20.0, 60.0]}"
```

## 文件清单

| 文件 | 位置 | 说明 |
|------|------|------|
| `servo_server.py` | Windows | 独占 COM7，提供 TCP API (:9555) |
| `servo_client.py` | Windows | 封装 TCP 通信，供其他脚本调用 |
| `servo_bridge.py` | Windows | 读写合一桥接，:5005 读 + :5006 写 |
| `r02_servo_bridge_node.cpp` | WSL | 连接 :5005，发布 /joint_states |
| `r03_servo_cmd_node.cpp` | WSL | 订阅 /joint_command，转发到 :5006 |

## TCP 协议

每条消息 = `[4字节长度前缀（大端序）] + [JSON 数据]`

## 通信频率

- 读取：约 50Hz（`time.sleep(0.02)`）
- 命令：按需触发（订阅到消息即发送）

## 故障排查

| 现象 | 原因 | 解决 |
|------|------|------|
| `Connection refused` | Windows 端没启动，或 IP 不对 | 先启动 Python，确认 IP 是 `172.28.208.1` |
| 连接成功但没数据 | 串口没读到舵机 | 检查 COM7 和舵机供电 |
| 数据偶尔为 None | 舵机偶尔无响应 | 正常现象，代码已处理 |
| COM7 冲突 | 多个程序打开同一串口 | 只用 `servo_server.py` 操作串口 |