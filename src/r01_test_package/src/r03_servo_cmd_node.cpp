/** WSL 端 ROS2 命令节点 — 订阅 /joint_command，转发到 Windows 控制舵机
 *
 * 用法:
 *   ros2 run r01_test_package r03_servo_cmd_node
 *
 * 测试:
 *   ros2 topic pub /joint_command std_msgs/msg/Float64MultiArray "{data: [45.0, -30.0, 10.0, 0.0, -20.0, 60.0]}"
 */
#include <chrono>
#include <memory>
#include <string>
#include <cstring>
#include <sstream>
#include <arpa/inet.h>
#include <unistd.h>
#include <sys/socket.h>

#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/float64_multi_array.hpp"

using namespace std::chrono_literals;

class ServoCmdNode : public rclcpp::Node {
public:
  ServoCmdNode() : Node("servo_cmd_node") {
    this->declare_parameter("host", "172.28.208.1");
    this->declare_parameter("port", 5006);

    // 订阅 /joint_command
    cmd_sub_ = this->create_subscription<std_msgs::msg::Float64MultiArray>(
      "/joint_command", 10,
      std::bind(&ServoCmdNode::on_command, this, std::placeholders::_1));

    // 连接 Windows 命令服务
    std::string host = this->get_parameter("host").as_string();
    int port = this->get_parameter("port").as_int();
    RCLCPP_INFO(this->get_logger(), "正在连接命令服务 %s:%d ...", host.c_str(), port);

    if (!connect_to_server(host, port)) {
      RCLCPP_ERROR(this->get_logger(), "无法连接命令服务，请确认 command_tcp_server.py 已启动");
      rclcpp::shutdown();
      return;
    }
    RCLCPP_INFO(this->get_logger(), "已连接到命令服务，等待 /joint_command 指令...");
  }

  ~ServoCmdNode() override {
    if (sock_ >= 0) close(sock_);
  }

private:
  bool connect_to_server(const std::string & host, int port) {
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

    return true;
  }

  void on_command(const std_msgs::msg::Float64MultiArray::SharedPtr msg) {
    if (sock_ < 0) {
      RCLCPP_WARN(this->get_logger(), "未连接，无法发送命令");
      return;
    }

    // 构造 JSON
    std::ostringstream json;
    json << "{\"cmd\":\"write_angles\",\"angles\":[";
    for (size_t i = 0; i < msg->data.size(); i++) {
      if (i > 0) json << ",";
      json << msg->data[i];
    }
    json << "]}";
    std::string body = json.str();

    std::string angles_str;
    for (size_t i = 0; i < msg->data.size() && i < 6; i++) {
      if (i > 0) angles_str += ", ";
      angles_str += std::to_string(static_cast<int>(msg->data[i]));
    }
    RCLCPP_INFO(this->get_logger(), "发送命令: [%s]", angles_str.c_str());

    // 发送: 4 字节长度 + JSON
    uint32_t len = htonl(body.size());
    if (send(sock_, &len, 4, 0) < 0) {
      RCLCPP_ERROR(this->get_logger(), "发送失败");
      reconnect();
      return;
    }
    send(sock_, body.c_str(), body.size(), 0);
  }

  void reconnect() {
    close(sock_); sock_ = -1;
    std::string host = this->get_parameter("host").as_string();
    int port = this->get_parameter("port").as_int();
    if (connect_to_server(host, port)) {
      RCLCPP_INFO(this->get_logger(), "重连成功");
    }
  }

  rclcpp::Subscription<std_msgs::msg::Float64MultiArray>::SharedPtr cmd_sub_;
  int sock_ = -1;
};

int main(int argc, char ** argv) {
  rclcpp::init(argc, argv);
  auto node = std::make_shared<ServoCmdNode>();
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}