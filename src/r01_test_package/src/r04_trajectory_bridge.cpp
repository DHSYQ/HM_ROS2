/** 轨迹桥接节点 — 一个节点搞定全部
 *
 * 1. 发布 /joint_states（默认全零，move_group 需要）
 * 2. 监听 /hm_robot_arm_controller/follow_joint_trajectory
 * 3. 弧度→角度，发布到 /joint_command → 舵机
 */
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <control_msgs/action/follow_joint_trajectory.hpp>
#include <sensor_msgs/msg/joint_state.hpp>
#include <std_msgs/msg/float64_multi_array.hpp>
#include <thread>
#include <chrono>

using FollowJointTrajectory = control_msgs::action::FollowJointTrajectory;
using GoalHandle = rclcpp_action::ServerGoalHandle<FollowJointTrajectory>;

class TrajectoryBridgeNode : public rclcpp::Node {
public:
  TrajectoryBridgeNode() : Node("trajectory_bridge_node") {
    // 1. 发布默认 /joint_states，让 move_group 能通过轨迹验证
    joint_pub_ = this->create_publisher<sensor_msgs::msg::JointState>(
      "/joint_states", 10);
    publish_joint_state();

    joint_timer_ = this->create_wall_timer(
      std::chrono::milliseconds(100),
      std::bind(&TrajectoryBridgeNode::publish_joint_state, this));

    // 2. 发布 /joint_command
    cmd_pub_ = this->create_publisher<std_msgs::msg::Float64MultiArray>(
      "/joint_command", 10);

    // 3. 监听 /hm_robot_arm_controller/follow_joint_trajectory
    action_server_ = rclcpp_action::create_server<FollowJointTrajectory>(
      this, "/hm_robot_arm_controller/follow_joint_trajectory",
      std::bind(&TrajectoryBridgeNode::handle_goal, this,
                std::placeholders::_1, std::placeholders::_2),
      std::bind(&TrajectoryBridgeNode::handle_cancel, this,
                std::placeholders::_1),
      std::bind(&TrajectoryBridgeNode::handle_accepted, this,
                std::placeholders::_1));

    RCLCPP_INFO(get_logger(), "桥接节点已就绪: /joint_states(10Hz) + /hm_robot_arm_controller/follow_joint_trajectory → /joint_command");
  }

private:
  void publish_joint_state() {
    auto msg = sensor_msgs::msg::JointState();
    msg.header.stamp = this->now();
    for (int i = 1; i <= 6; i++) {
      msg.name.push_back("joint_" + std::to_string(i));
      msg.position.push_back(last_positions_[i - 1]);
    }
    joint_pub_->publish(msg);
  }

  rclcpp_action::GoalResponse handle_goal(
    const rclcpp_action::GoalUUID &,
    std::shared_ptr<const FollowJointTrajectory::Goal> goal) {
    const auto & traj = goal->trajectory;
    RCLCPP_INFO(get_logger(), "收到轨迹: %zu 点 x %zu 关节",
                traj.points.size(), traj.joint_names.size());
    return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
  }

  rclcpp_action::CancelResponse handle_cancel(const std::shared_ptr<GoalHandle>) {
    return rclcpp_action::CancelResponse::ACCEPT;
  }

  void handle_accepted(const std::shared_ptr<GoalHandle> goal_handle) {
    std::thread{std::bind(&TrajectoryBridgeNode::execute, this, goal_handle)}.detach();
  }

  void execute(const std::shared_ptr<GoalHandle> goal_handle) {
    const auto & traj = goal_handle->get_goal()->trajectory;
    auto result = std::make_shared<FollowJointTrajectory::Result>();

    for (size_t i = 0; i < traj.points.size(); i++) {
      if (goal_handle->is_canceling()) {
        result->error_code = FollowJointTrajectory::Result::INVALID_GOAL;
        goal_handle->canceled(result);
        return;
      }

      auto cmd = std_msgs::msg::Float64MultiArray();
      for (size_t j = 0; j < traj.points[i].positions.size(); j++) {
        double deg = traj.points[i].positions[j] * 180.0 / M_PI;
        cmd.data.push_back(deg);
        last_positions_[j] = traj.points[i].positions[j];  // 记录弧度值
      }
      cmd_pub_->publish(cmd);

      if (i < traj.points.size() - 1) {
        auto t1 = rclcpp::Duration(traj.points[i].time_from_start);
        auto t2 = rclcpp::Duration(traj.points[i + 1].time_from_start);
        auto dt = (t2 - t1).nanoseconds();
        if (dt > 0) std::this_thread::sleep_for(std::chrono::nanoseconds(dt));
      }
    }

    result->error_code = FollowJointTrajectory::Result::SUCCESSFUL;
    goal_handle->succeed(result);
    RCLCPP_INFO(get_logger(), "轨迹执行完成");
  }

  rclcpp_action::Server<FollowJointTrajectory>::SharedPtr action_server_;
  rclcpp::Publisher<sensor_msgs::msg::JointState>::SharedPtr joint_pub_;
  rclcpp::Publisher<std_msgs::msg::Float64MultiArray>::SharedPtr cmd_pub_;
  rclcpp::TimerBase::SharedPtr joint_timer_;
  double last_positions_[6] = {0, 0, 0, 0, 0, 0};
};

int main(int argc, char ** argv) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<TrajectoryBridgeNode>());
  rclcpp::shutdown();
  return 0;
}