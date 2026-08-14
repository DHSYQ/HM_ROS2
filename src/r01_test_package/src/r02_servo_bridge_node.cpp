/** WSL 端 ROS2 桥接节点 — 连接 Windows TCP 服务端，接收舵机角度并发布 /joint_states
 *
 * 用法:
 *   ros2 run r01_test_package r02_servo_bridge_node --ros-args -p host:=<Windows_IP>
 *
 * 默认连接 172.28.208.1:5005
 */
#include <chrono>
#include <memory>
#include <string>
#include <cstring>
#include <arpa/inet.h>
#include <unistd.h>
#include <sys/socket.h>

#include "rclcpp/rclcpp.hpp"
#include "sensor_msgs/msg/joint_state.hpp"
#include "nlohmann/json.hpp"

using namespace std::chrono_literals;

class ServoBridgeNode : public rclcpp::Node {
public:
  ServoBridgeNode() : Node("servo_bridge_node") {
    this->declare_parameter("host", "172.28.208.1");
    this->declare_parameter("port", 5005);
    this->declare_parameter("rate", 50.0);

    joint_pub_ = this->create_publisher<sensor_msgs::msg::JointState>("/joint_states", 10);

    // 尝试连接，失败不崩溃，发布默认关节状态
    if (!connect_to_server()) {
      RCLCPP_WARN(this->get_logger(),
        "无法连接 Windows 服务端，将发布默认关节状态（全零）。"
        "请先启动 Windows 端: python servo_server.py && python servo_bridge.py");
    }

    // 定时器
    double rate = this->get_parameter("rate").as_double();
    auto period = std::chrono::duration<double>(1.0 / rate);
    timer_ = this->create_wall_timer(period,
      std::bind(&ServoBridgeNode::receive_and_publish, this));

    RCLCPP_INFO(this->get_logger(), "舵机桥接节点已启动");
  }

  ~ServoBridgeNode() override {
    if (sock_ >= 0) close(sock_);
  }

private:
  bool connect_to_server() {
    std::string host = this->get_parameter("host").as_string();
    int port = this->get_parameter("port").as_int();

    sock_ = socket(AF_INET, SOCK_STREAM, 0);
    if (sock_ < 0) {
      RCLCPP_ERROR(this->get_logger(), "创建 socket 失败");
      return false;
    }

    struct timeval tv;
    tv.tv_sec = 2;
    tv.tv_usec = 0;
    setsockopt(sock_, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

    struct sockaddr_in addr;
    std::memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);

    if (inet_pton(AF_INET, host.c_str(), &addr.sin_addr) <= 0) {
      RCLCPP_ERROR(this->get_logger(), "无效的 IP: %s", host.c_str());
      close(sock_); sock_ = -1;
      return false;
    }

    if (connect(sock_, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
      RCLCPP_ERROR(this->get_logger(), "连接失败: %s", strerror(errno));
      close(sock_); sock_ = -1;
      return false;
    }

    RCLCPP_INFO(this->get_logger(), "已连接到 Windows 服务端 %s:%d", host.c_str(), port);
    connected_ = true;
    return true;
  }

  void publish_default_state() {
    auto msg = sensor_msgs::msg::JointState();
    msg.header.stamp = this->now();
    for (int i = 1; i <= 6; i++) {
      msg.name.push_back("joint_" + std::to_string(i));
      msg.position.push_back(0.0);
    }
    joint_pub_->publish(msg);
  }

  void receive_and_publish() {
    if (!connected_) {
      // 未连接时发布默认状态，保证 move_group 能正常工作
      publish_default_state();
      // 尝试重连
      reconnect();
      return;
    }

    uint32_t msg_len = 0;
    int n = recv(sock_, &msg_len, 4, MSG_WAITALL);
    if (n <= 0) {
      RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                           "接收数据失败，尝试重连...");
      connected_ = false;
      close(sock_); sock_ = -1;
      return;
    }
    msg_len = ntohl(msg_len);

    std::string buffer(msg_len, '\0');
    n = recv(sock_, &buffer[0], msg_len, MSG_WAITALL);
    if (n <= 0) {
      RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                           "接收消息体失败");
      return;
    }

    try {
      auto j = nlohmann::json::parse(buffer);
      auto angles = j["angles"];

      auto msg = sensor_msgs::msg::JointState();
      msg.header.stamp = this->now();

      for (int id = 1; id <= 6; id++) {
        std::string key = std::to_string(id);
        if (angles.contains(key) && !angles[key].is_null()) {
          msg.name.push_back("joint_" + key);
          msg.position.push_back(angles[key].get<double>() * M_PI / 180.0);
        }
      }

      if (!msg.name.empty()) {
        joint_pub_->publish(msg);
      }
    } catch (const std::exception & e) {
      RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                           "JSON 解析失败: %s", e.what());
    }
  }

  void reconnect() {
    std::string host = this->get_parameter("host").as_string();
    int port = this->get_parameter("port").as_int();
    // 每 2 秒尝试一次重连
    auto now = this->now().seconds();
    if (now - last_reconnect_attempt_ < 2.0) return;
    last_reconnect_attempt_ = now;

    RCLCPP_INFO(this->get_logger(), "尝试重连 %s:%d ...", host.c_str(), port);
    if (connect_to_server()) {
      RCLCPP_INFO(this->get_logger(), "重连成功");
    }
  }

  rclcpp::Publisher<sensor_msgs::msg::JointState>::SharedPtr joint_pub_;
  rclcpp::TimerBase::SharedPtr timer_;
  int sock_ = -1;
  bool connected_ = false;
  double last_reconnect_attempt_ = 0.0;
};

int main(int argc, char ** argv) {
  rclcpp::init(argc, argv);
  auto node = std::make_shared<ServoBridgeNode>();
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}