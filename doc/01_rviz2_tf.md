# 01 — RViz2 可视化：TF 与 /joint_states 的关系

## 为什么 URDF 定义了关节，但 RViz2 中看不到 TF？

**核心原因：`robot_state_publisher` 无法为可动关节发布 TF，除非收到 `/joint_states` 数据。**

```
URDF 定义了什么？
  ├─ 关节结构：谁连谁、旋转轴、限位角度
  ├─ 固定关节（type="fixed"）→ 不需要 /joint_states，直接发布 TF
  └─ 可动关节（type="revolute"）→ 必须知道当前角度值才能算 TF

robot_state_publisher 的工作流程：
  1. 读取 /robot_description 中的 URDF
  2. 订阅 /joint_states 话题
  3. 固定关节 → 直接发布 TF
  4. 可动关节 → 等 /joint_states 提供角度值 → 计算并发布 TF

如果没有 /joint_states，可动关节的 TF 永远不会发布！
```

## 测试时 — 使用 joint_state_publisher_gui

没有真实舵机数据时，用 `joint_state_publisher_gui` 作为 `/joint_states` 的临时数据源：

```
joint_state_publisher_gui
  ├─ 读取 URDF 中的非固定关节
  ├─ 弹出 GUI 滑块，手动调节角度
  └─ 发布 /joint_states

robot_state_publisher ← 订阅 /joint_states ← 有数据了 → 发布所有关节的 TF
```

## 实际运行时 — 使用 r02_servo_bridge_node

真实舵机数据到位后，`r02_servo_bridge_node` 替代 `joint_state_publisher_gui`：

```
r02_servo_bridge_node
  ├─ 从 Windows 读取舵机角度
  └─ 发布 /joint_states（真实数据）

robot_state_publisher ← 订阅 /joint_states（真实数据）→ 发布实时 TF
```

## 启动命令

```bash
# 测试（GUI 手动调节）
ros2 launch r01_test_package rviz_display.launch.py

# 实际运行（舵机数据）
# Windows: python servo_server.py + python servo_bridge.py
# WSL2:   ros2 run r01_test_package r02_servo_bridge_node
```

## 常见问题

| 现象 | 原因 | 解决 |
|------|------|------|
| RViz2 显示 "No transform from [base_link] to [link_xxx]" | 没有 `/joint_states` 数据 | 启动 `joint_state_publisher_gui` 或 `r02_servo_bridge_node` |
| 只有 gripper_tip 有 TF | gripper_tip_joint 是固定关节，不需要 `/joint_states` | 正常现象，说明问题在 `/joint_states` 缺失 |
| STL 模型加载失败 "Unable to open file" | mesh 路径缺少 `file://` 前缀 | 使用 `file://` 前缀或 `package://` 格式 |
| 找不到 `genkiarm_description` 包 | install 目录残留旧构建 | 清理旧 build/install 后重新编译 |
| TF 能看到，但看不到 STL 模型 | RViz2 中选错了 Display 插件 | 应使用 **RobotModel**（非 MotionPlanning），Description Topic 设为 `/robot_description` |
| RobotModel 选 file 有模型，选 topic 没有 | 选错了插件（MotionPlanning 需要 SRDF 会报错） | 改用 RobotModel 插件，topic 方式即可正常加载 |

## 踩坑记录

### 1. STL mesh 路径问题

如果file能显示stl但是topic不显示，先选file然后切换会topic就可以了

最初使用绝对路径 `/home/syq/Desktop/YD/meshes/AAA.stl`，RViz2 报 "Unable to open file"。需加 `file://` 前缀：

```xml
<!-- 错误 -->
<mesh filename="/home/syq/Desktop/YD/meshes/AAA.stl"/>

<!-- 正确 -->
<mesh filename="file:///home/syq/Desktop/YD/meshes/AAA.stl"/>
```

最终方案：将 meshes 和 URDF 放入包内，使用 `package://` 格式：

```xml
<mesh filename="package://r01_test_package/meshes/AAA.stl"/>
```

### 2. URDF 应放入包内

URDF 文件放在包外（`/home/syq/Desktop/YD/urdf/`）虽然能用绝对路径读取，但不够规范。标准做法是放入包内 `src/r01_test_package/urdf/`，通过 `get_package_share_directory` 查找。

### 3. 可动关节需要 /joint_states

`robot_state_publisher` 只能为固定关节（`type="fixed"`）直接发布 TF。`joint_1`~`joint_6` 都是 `revolute` 类型，必须收到 `/joint_states` 中的角度值后才能计算 TF。

### 4. RViz2 插件选择

RViz2 的 **RobotModel** 和 **MotionPlanning** 是两个不同的 Display 插件：
- **RobotModel**：只需要 `/robot_description`，用于可视化
- **MotionPlanning**：需要 `robot_description_semantic`（SRDF），用于 MoveIt2 运动规划

选错成 MotionPlanning 会导致 SRDF 解析失败，看不到模型。