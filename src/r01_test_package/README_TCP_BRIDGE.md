# 舵机 TCP 桥接链路说明

## 整体架构

```
 ┌─────────────────────────────────┐        ┌──────────────────────────────┐
 │         Windows (主机)           │        │       WSL2 Ubuntu (虚拟机)     │
 │                                 │  TCP   │                              │
 │  servo_tcp_server.py            │ ◄───── │  r02_servo_bridge_node.cpp   │
 │    ↓ 读串口 COM7                │  :5005 │    ↓ 发布 /joint_states       │
 │  1-6 号舵机角度                  │        │    ROS2 生态消费               │
 └─────────────────────────────────┘        └──────────────────────────────┘
```

## 为什么需要 TCP 桥接？

- 舵机通过串口 `COM7` 连接在 **Windows** 上
- ROS2 开发环境在 **WSL2 Ubuntu** 里
- WSL2 有自己的虚拟网卡，不能直接访问 Windows 的硬件
- 所以通过 **TCP 网络通信** 把数据从 Windows 传到 WSL2

## 链路分步解析

### 第 1 步：Windows 端读取舵机

`servo_tcp_server.py` 做的事：

1. 打开串口 `COM7`，波特率 `1000000`
2. 循环向 1-6 号舵机发送读取指令（协议：`FF FF ID 04 02 38 02 checksum`）
3. 收到舵机返回的原始值，换算成角度（度）

这一步和原来的 `read_all_servos.py` 完全一样。

### 第 2 步：Windows 端作为 TCP 服务端

`servo_tcp_server.py` 额外做的事：

```python
server = socket.socket()          # ① 创建一个 TCP 套接字
server.bind(('0.0.0.0', 5005))    # ② 绑定到本机所有网卡的 5005 端口
server.listen(1)                  # ③ 开始监听，等待客户端连接
conn, addr = server.accept()      # ④ 阻塞等待，直到 WSL 连上来
```

`0.0.0.0` 表示监听所有网络接口，包括 WSL 虚拟网卡 `172.28.208.1`。

### 第 3 步：数据打包发送

每 20ms（50Hz）循环一次：

```python
angles = read_servo_angles(ser)                    # 读舵机角度

data = {'timestamp': time.time(), 'angles': angles} # 包装成字典
msg = json.dumps(data).encode('utf-8')              # 转成 JSON 字符串 → 字节

conn.sendall(struct.pack('!I', len(msg)) + msg)     # 发送：4字节长度 + JSON数据
```

**协议格式**：每条消息 = `[4字节长度前缀] + [JSON 数据]`

| 字节位置 | 内容 | 说明 |
|---------|------|------|
| 0-3 | 消息长度（大端序） | 4 字节无符号整数，表示后面 JSON 的字节数 |
| 4-末尾 | JSON 字符串 | 例如 `{"timestamp":1.23,"angles":{"1":45.0,"2":-30.0,...}}` |

为什么要 4 字节长度前缀？因为 TCP 是流式传输，数据会粘在一起，接收方需要知道每条消息的边界。

### 第 4 步：WSL2 端连接并接收

`r02_servo_bridge_node.cpp` 做的事：

```cpp
sock_ = socket(AF_INET, SOCK_STREAM, 0);            // ① 创建 TCP 套接字
connect(sock_, addr, sizeof(addr));                  // ② 连接 Windows 的 172.28.208.1:5005
```

连接成功后，用定时器每 20ms 触发一次接收：

```cpp
// ③ 先读 4 字节，得到消息长度
recv(sock_, &msg_len, 4, MSG_WAITALL);
msg_len = ntohl(msg_len);  // 网络字节序 → 主机字节序

// ④ 再读 msg_len 字节，得到 JSON
recv(sock_, &buffer[0], msg_len, MSG_WAITALL);

// ⑤ 解析 JSON，提取角度值
auto j = json::parse(buffer);
auto angles = j["angles"];

// ⑥ 发布到 ROS2 话题
joint_pub_->publish(msg);
```

### 第 5 步：ROS2 话题发布

发布到 `/joint_states` 话题，消息格式 `sensor_msgs/JointState`：

```yaml
header:
  stamp: 当前时间戳
name:   ["joint_1", "joint_2", "joint_3", "joint_4", "joint_5", "joint_6"]
position: [0.785, -0.523, 0.174, 0.0, -0.349, 1.047]  # 弧度
```

## 端口说明

`5005` 不是固定端口，只是选了一个不会被占用的。两端必须一致：

| 位置 | 设置方式 |
|------|---------|
| Python 端 | `servo_tcp_server.py` 第 15 行 `TCP_PORT = 5005` |
| C++ 端 | 默认 `5005`，运行时可覆盖 `-p port:=其他端口` |

## 通信频率

- Python 端：`time.sleep(0.02)` → 约 50Hz
- C++ 端：`declare_parameter("rate", 50.0)` → 约 50Hz

两端频率应保持一致，否则可能出现数据积压或空读。

## 故障排查

| 现象 | 原因 | 解决 |
|------|------|------|
| `Connection refused` | Windows 端没启动，或 IP 不对 | 先启动 Python，确认 IP 是 `172.28.208.1` |
| 连接成功但没数据 | 串口没读到舵机 | 检查 COM7 和舵机供电 |
| 数据偶尔为 None | 舵机偶尔无响应 | 正常现象，代码已处理 |
| 编译报错 `nlohmann/json.hpp` | 缺少 JSON 库 | `sudo apt install nlohmann-json3-dev` |