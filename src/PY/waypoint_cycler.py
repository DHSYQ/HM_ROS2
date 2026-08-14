#!/usr/bin/env python3
"""
多点位循环运动节点 (waypoint_cycler)

功能: 按预设关节角度序列循环发布 /joint_command
      数据链路: waypoint_cycler → /joint_command → r03_servo_cmd_node → TCP → 舵机

用法:
    # 确保 ROS2 环境已 source
    python3 waypoint_cycler.py

    # 或指定循环间隔（秒）
    python3 waypoint_cycler.py --interval 5.0

    # 指定循环次数（0 = 无限循环）
    python3 waypoint_cycler.py --loops 3
"""

import argparse
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float64MultiArray

# ── 预设点位配置 (关节角度，单位：度，顺序: joint_1 ~ joint_6) ──
# 修改此列表即可自定义循环点位
WAYPOINTS = [
    [0.0,   0.0,   0.0,   0.0,   0.0,   0.0],   # 点位 1: Home
    [30.0, -20.0,  15.0,  10.0, -10.0,  20.0],   # 点位 2
    [-20.0, 15.0, -10.0,  30.0,   5.0, -15.0],   # 点位 3
    [15.0, -30.0,  25.0, -15.0,   0.0,  10.0],   # 点位 4
]


class WaypointCycler(Node):
    def __init__(self, interval: float = 3.0, max_loops: int = 0):
        super().__init__('waypoint_cycler')
        self.pub = self.create_publisher(Float64MultiArray, '/joint_command', 10)
        self.interval = interval
        self.max_loops = max_loops
        self.current_idx = 0
        self.loop_count = 0

        self.timer = self.create_timer(interval, self.cycle_waypoints)
        self.get_logger().info(
            f'循环运动节点已启动 | {len(WAYPOINTS)} 个点位 | '
            f'间隔 {interval}s | 循环次数: {"无限" if max_loops == 0 else max_loops}'
        )

    def cycle_waypoints(self):
        # 检查循环次数限制
        if self.max_loops > 0 and self.loop_count >= self.max_loops:
            self.get_logger().info(f'已完成 {self.max_loops} 次循环，停止')
            self.timer.cancel()
            return

        waypoint = WAYPOINTS[self.current_idx]
        msg = Float64MultiArray()
        msg.data = [float(v) for v in waypoint]
        self.pub.publish(msg)

        self.get_logger().info(
            f'[循环 {self.loop_count + 1}] '
            f'点位 {self.current_idx + 1}/{len(WAYPOINTS)}: '
            f'{["{:.1f}".format(v) for v in waypoint]}'
        )

        self.current_idx += 1
        if self.current_idx >= len(WAYPOINTS):
            self.current_idx = 0
            self.loop_count += 1


def main():
    parser = argparse.ArgumentParser(description='多点位循环运动节点')
    parser.add_argument('--interval', type=float, default=3.0,
                        help='每个点位停留时间（秒），默认 3.0')
    parser.add_argument('--loops', type=int, default=0,
                        help='循环次数（0 = 无限），默认 0')
    args = parser.parse_args()

    rclpy.init()
    node = WaypointCycler(interval=args.interval, max_loops=args.loops)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('用户中断')
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()