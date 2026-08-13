"""加载 hm_robot.urdf，启动 joint_state_publisher_gui + robot_state_publisher + rviz2"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    pkg_share = get_package_share_directory('r01_test_package')
    urdf_path = os.path.join(pkg_share, 'urdf', 'hm_robot.urdf')

    with open(urdf_path, 'r') as f:
        robot_description = f.read()

    joint_state_publisher_gui = Node(
        package='joint_state_publisher_gui',
        executable='joint_state_publisher_gui',
        name='joint_state_publisher_gui',
        output='screen',
    )

    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        parameters=[{
            'robot_description': ParameterValue(robot_description, value_type=str),
        }],
        output='screen',
    )

    rviz2 = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        arguments=['-d', os.path.join(pkg_share, 'config', 'rviz_display.rviz')],
        output='screen',
    )

    return LaunchDescription([
        joint_state_publisher_gui,
        robot_state_publisher,
        rviz2,
    ])