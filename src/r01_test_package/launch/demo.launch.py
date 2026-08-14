from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from moveit_configs_utils import MoveItConfigsBuilder
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    moveit_config = MoveItConfigsBuilder("hm_robot", package_name="r01_test_package").to_moveit_configs()

    # MoveGroup 节点 (使用真实控制器，非 fake)
    move_group_node = Node(
        package="moveit_ros_move_group",
        executable="move_group",
        output="screen",
        parameters=[moveit_config.to_dict()],
    )

    # RViz2 节点 (加载 MotionPlanning 配置)
    rviz_config = os.path.join(
        get_package_share_directory("r01_test_package"),
        "config", "moveit.rviz")
    rviz_node = Node(
        package="rviz2",
        executable="rviz2",
        output="log",
        arguments=["-d", rviz_config],
        parameters=[
            moveit_config.robot_description,
            moveit_config.robot_description_semantic,
            moveit_config.robot_description_kinematics,
            moveit_config.joint_limits,
        ],
    )

    # 轨迹桥接节点 (发布 /joint_states + 监听 /execute_trajectory → /joint_command)
    bridge_node = Node(
        package="r01_test_package",
        executable="r04_trajectory_bridge",
        output="screen",
    )

    # robot_state_publisher (/joint_states → TF)
    robot_state_pub = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        output="screen",
        parameters=[moveit_config.robot_description],
    )

    # 舵机命令节点 (/joint_command → TCP → Windows → 舵机)
    cmd_node = Node(
        package="r01_test_package",
        executable="r03_servo_cmd_node",
        output="screen",
        parameters=[{
            "host": "172.28.208.1",
            "port": 5006,
        }],
    )

    return LaunchDescription([
        move_group_node,
        rviz_node,
        bridge_node,
        robot_state_pub,
        cmd_node,
    ])