# 03 — MoveIt2 拖拽控制实体机械臂

## 一、目标

在 RViz2 中拖拽机械臂末端小球 → Plan & Execute → 实体舵机跟随运动。

## 二、最终数据链路

```
RViz2 MotionPlanning 插件
  │  拖拽小球 + Plan & Execute
  ▼
move_group 节点
  │  规划轨迹 → /hm_robot_arm_controller/follow_joint_trajectory
  ▼
r04_trajectory_bridge  (一个节点搞定全部)
  │  ① 发布 /joint_states（10Hz，默认全零，move_group 需要）
  │  ② 监听 /hm_robot_arm_controller/follow_joint_trajectory action
  │  ③ 弧度→角度，逐点发布到 /joint_command
  ▼
r03_servo_cmd_node
  │  TCP :5006 → Windows
  ▼
servo_bridge.py → servo_server.py → COM7 → 舵机
```

## 三、最终启动的节点

| 节点 | 作用 |
|------|------|
| `move_group` | MoveIt2 运动规划核心 |
| `rviz2` | 拖拽交互界面 |
| `r04_trajectory_bridge` | 发布 /joint_states + 轨迹转 /joint_command |
| `robot_state_publisher` | /joint_states → TF |
| `r03_servo_cmd_node` | /joint_command → TCP → 舵机 |

## 四、迭代过程与踩坑

### 坑 1：move_group 拒绝执行（CONTROL_FAILED）

**现象：**
```
[move_group]: Didn't receive robot state (joint angles) with recent timestamp
[move_group]: Failed to validate trajectory: couldn't receive full current joint state within 1s
[move_group]: CONTROL_FAILED
```

**原因：** move_group 执行轨迹前需要验证当前关节状态是否匹配轨迹起点。它从 `/joint_states` 获取状态，但 `r02_servo_bridge_node` 没有正常发布 `/joint_states`（可能因为 Windows 端未启动导致连接失败而崩溃）。

**解决：** 把 `/joint_states` 发布直接放进 `r04_trajectory_bridge` 节点。启动时发布全零默认状态，执行中更新为最后命令位置。这样无论 Windows 端是否在线，move_group 都能正常工作。

关键代码：
```cpp
// 每 100ms 发布一次 /joint_states
joint_timer_ = this->create_wall_timer(
  std::chrono::milliseconds(100),
  std::bind(&TrajectoryBridgeNode::publish_joint_state, this));
```

### 坑 2：action 名字对不上

**现象：**
```
[move_group]: Action client not connected to action server: hm_robot_arm_controller/follow_joint_trajectory
[move_group]: Failed to send trajectory to controller
```

**原因：** `moveit_controllers.yaml` 中 controller 名是 `hm_robot_arm_controller`，action namespace 是 `follow_joint_trajectory`，所以 move_group 发送到 `/hm_robot_arm_controller/follow_joint_trajectory`。但桥接节点监听的是 `/execute_trajectory`。

**解决：** action 名字改为 `/hm_robot_arm_controller/follow_joint_trajectory`，action 类型使用 `control_msgs::action::FollowJointTrajectory`（不是 `moveit_msgs::action::ExecuteTrajectory`）。

```cpp
action_server_ = rclcpp_action::create_server<FollowJointTrajectory>(
  this, "/hm_robot_arm_controller/follow_joint_trajectory", ...);
```

### 坑 3：CMakeLists.txt 依赖混乱

**现象：** 编译报 `fatal error: control_msgs/action/follow_joint_trajectory.hpp: No such file or directory`，或 `ament_target_dependencies() the passed package name 'control_msgs' was not found before`。

**原因：** `CMakeLists.txt` 中 `find_package` 和 `ament_target_dependencies` 不一致——前者用了 `moveit_msgs`，后者用了 `control_msgs`，或者反过来。

**解决：** 两者必须一致：

```cmake
# find_package
find_package(control_msgs REQUIRED)

# ament_target_dependencies
ament_target_dependencies(r04_trajectory_bridge
  rclcpp
  rclcpp_action
  std_msgs
  sensor_msgs
  control_msgs)
```

### 坑 4：joint_limits 速度/加速度缩放太小

**现象：** 轨迹执行非常慢，或者超时失败。

**原因：** `joint_limits.yaml` 中 `default_velocity_scaling_factor: 0.1` 和 `default_acceleration_scaling_factor: 0.1` 导致轨迹被稀释 10 倍。

**解决：** 调大到 1.0：

```yaml
default_velocity_scaling_factor: 1.0
default_acceleration_scaling_factor: 1.0
```

### 坑 5：execution_duration_monitoring 超时

**现象：** 轨迹执行到一半报超时。

**原因：** `moveit_controllers.yaml` 中 `execution_duration_monitoring: true`（默认），move_group 要求在预期时间内完成执行，桥接节点逐点 sleep 可能超时。

**解决：** 关闭时长监控：

```yaml
hm_robot_arm_controller:
  type: FollowJointTrajectory
  action_ns: follow_joint_trajectory
  default: true
  execution_duration_monitoring: false
  joints:
    - joint_1
    - joint_2
    - joint_3
    - joint_4
    - joint_5
    - joint_6
```

## 五、启动步骤

```bash
# 1. Windows 端
python servo_server.py
python servo_bridge.py

# 2. WSL2 端
colcon build --packages-select r01_test_package && source install/setup.bash
ros2 launch r01_test_package demo.launch.py

# 3. RViz2 中
#    MotionPlanning 面板 → 拖拽小球 → Plan & Execute
```

## 六、关键文件

| 文件 | 作用 |
|------|------|
| `src/r04_trajectory_bridge.cpp` | 桥接节点：/joint_states + action → /joint_command |
| `config/moveit_controllers.yaml` | 控制器配置：名称、action namespace、关节列表 |
| `config/joint_limits.yaml` | 速度/加速度缩放因子 |
| `launch/demo.launch.py` | 一键启动所有节点 |

## 七、设计原则

**最简原则：** 一个节点只做一件事，但桥接节点做了三件事（/joint_states + action 监听 + /joint_command 发布），因为这三件事高度耦合——都是为了让 move_group 和舵机之间能通信。如果拆成三个节点，需要额外的状态同步，反而更复杂。