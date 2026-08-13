# 02 — MoveIt2 运动规划配置

## 一、概述

MoveIt2 是 ROS2 的运动规划框架，配合 RViz2 MotionPlanning 插件可在可视化界面中拖拽末端执行器，自动规划轨迹并控制机械臂。

## 二、架构说明

```
RViz2 MotionPlanning 插件
        │
        ▼
   move_group 节点
   (运动规划核心)
        │
        ▼
   /arm_controller/follow_joint_trajectory
        │
        ▼
   桥接节点 (待实现)  ← 将 MoveIt 轨迹转为 /joint_command
        │
        ▼
   r03_servo_cmd_node → TCP → servo_bridge.py → 舵机
```

## 三、配置流程

### 3.1 安装依赖

```bash
sudo apt install ros-jazzy-moveit-setup-assistant
sudo apt install ros-jazzy-moveit ros-jazzy-moveit-visual-tools
```

### 3.2 启动 Setup Assistant

```bash
# 确保 X11 转发可用
echo $DISPLAY
# 如果为空，设置：
export DISPLAY=$(cat /etc/resolv.conf | grep nameserver | awk '{print $2}'):0.0

ros2 run moveit_setup_assistant moveit_setup_assistant
```

### 3.3 GUI 配置步骤

| 步骤 | 操作 | 说明 |
|------|------|------|
| **Start** | 加载 URDF 文件 | 选择 `install/r01_test_package/share/r01_test_package/urdf/hm_robot.urdf` |
| **Self-Collisions** | 点击 "Generate Collision Matrix" | 自动生成碰撞检测矩阵 |
| **Virtual Joints** | 跳过 | 桌面机械臂底座固定，不需要 |
| **Planning Groups** | Add Group → Kinematic Chain | Group Name: `hm_robot_arm`，链: `base_link` → `gripper_tip`，求解器: `kdl_kinematics_plugin/KDLKinematicsPlugin` |
| **Robot Poses** | Add Pose → `home` | 所有关节值 0，作为归零位姿 |
| **End Effectors** | Add End Effector → `gripper` | Parent Link: `link_gripper`, Group: `hm_robot_arm` |
| **Passive Joints** | 跳过 | 无被动关节 |
| **ros2_control** | 跳过 | 使用 TCP 桥接，不走 ros2_control |
| **ROS2 Controllers** | Add Controller | 选 `joint_trajectory_controller/JointTrajectoryController`，勾选 joint_1~joint_6 |
| **MoveIt Controllers** | Auto Add | 自动生成 arm_controller |
| **3D Perception** | 跳过 | 无深度相机 |
| **Launch Files** | 全部勾选 | 生成 demo、move_group、rviz 等 launch 文件 |
| **Author** | 填写邮箱 | 随便填 |
| **Configuration Files** | 全选后 Generate | 保存到 `src/r01_test_package/` |

### 3.4 生成后合并 CMakeLists.txt 和 package.xml

Setup Assistant 会覆盖 `CMakeLists.txt` 和 `package.xml`，需要先备份再合并：

```bash
cp src/r01_test_package/CMakeLists.txt src/r01_test_package/CMakeLists.txt.bak
cp src/r01_test_package/package.xml src/r01_test_package/package.xml.bak
```

生成后需要把备份中的节点编译规则（r01~r03）和依赖（rclcpp, sensor_msgs, std_msgs, nlohmann_json）合并回新文件。

### 3.5 删除不需要的 xacro 文件

生成的文件中包含 `hm_robot.urdf.xacro` 和 `hm_robot.ros2_control.xacro`，它们引用了 ros2_control 框架。由于使用 TCP 桥接，不需要这些：

```bash
rm src/r01_test_package/config/hm_robot.urdf.xacro
rm src/r01_test_package/config/hm_robot.ros2_control.xacro
```

### 3.6 编译和启动

```bash
colcon build --packages-select r01_test_package
source install/setup.bash
ros2 launch r01_test_package demo.launch.py
```

## 四、踩坑记录

| 问题 | 原因 | 解决 |
|------|------|------|
| SRDF 无法自动加载 | Setup Assistant 不在同一目录查找 SRDF | 在 GUI 中手动配置，无需预先写 SRDF |
| 生成失败 "Failed to generate" | 取消了 `package.xml` 和 `CMakeLists.txt` 勾选 | 必须勾选这两个文件，生成后再手工合并 |
| "The chosen package location already exists" | 目录中缺少 `.setup_assistant` 标记 | `touch .setup_assistant` 后重试 |在pkg路径下新建
| CMakeLists.txt 被覆盖 | Setup Assistant 生成时覆盖了现有文件 | 生成前备份，生成后合并 |
| 启动后 STL 加载失败 | 残留的 xacro 文件引用了 ros2_control 旧路径 | 删除 `hm_robot.urdf.xacro` 和 `hm_robot.ros2_control.xacro` |
| 拖拽机械臂不动 | 未删除 xacro 导致 ros2_control 加载失败 | 同上，删除后重新编译启动 |

## 五、关键配置文件

| 文件 | 作用 |
|------|------|
| `config/hm_robot.srdf` | 规划组定义、碰撞矩阵、末端执行器 |
| `config/kinematics.yaml` | 运动学求解器配置 (KDL) |
| `config/joint_limits.yaml` | 关节速度和加速度限制 |
| `config/moveit_controllers.yaml` | 控制器配置 (arm_controller) |
| `config/initial_positions.yaml` | 初始位姿 |
| `launch/demo.launch.py` | 一键启动 move_group + RViz |

## 六、下一步

当前 MoveIt2 使用 **Fake Controller** 模式，规划的运动只在 RViz 中显示，不会实际驱动舵机。

要实现真实控制，需要编写一个 **桥接节点**：
- 订阅 MoveIt 输出的 `/arm_controller/follow_joint_trajectory` action
- 将轨迹点转换为 `/joint_command` 话题消息
- `r03_servo_cmd_node` 收到后通过 TCP 发送给舵机