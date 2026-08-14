/** WSL2 端 — 摄像头桥接节点
 *
 * 从 Windows 接收 JPEG 图像，解码后发布 /camera/image。
 *
 * 用法:
 *   ros2 run r01_test_package r05_camera_bridge_node
 *
 * 查看:
 *   ros2 run rqt_image_view rqt_image_view /camera/image
 */

#include <chrono>
#include <memory>
#include <string>
#include <vector>
#include <cstring>
#include <arpa/inet.h>
#include <unistd.h>
#include <sys/socket.h>

#include "rclcpp/rclcpp.hpp"
#include "sensor_msgs/msg/image.hpp"
#include <opencv2/opencv.hpp>
#include <cv_bridge/cv_bridge.hpp>

using namespace std::chrono_literals;

class CameraBridgeNode : public rclcpp::Node {
public:
  CameraBridgeNode() : Node("camera_bridge_node") {
    this->declare_parameter("host", "172.28.208.1");
    this->declare_parameter("port", 5007);

    image_pub_ = this->create_publisher<sensor_msgs::msg::Image>("/camera/image", 10);

    // 连接线程
    connect_thread_ = std::thread(&CameraBridgeNode::connect_loop, this);
  }

  ~CameraBridgeNode() override {
    running_ = false;
    if (connect_thread_.joinable()) connect_thread_.join();
    if (sock_ >= 0) close(sock_);
  }

private:
  void connect_loop() {
    std::string host = this->get_parameter("host").as_string();
    int port = this->get_parameter("port").as_int();

    while (running_ && rclcpp::ok()) {
      if (!try_connect(host, port)) {
        RCLCPP_INFO_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
          "等待连接 %s:%d ...", host.c_str(), port);
        std::this_thread::sleep_for(2s);
        continue;
      }

      RCLCPP_INFO(this->get_logger(), "已连接到摄像头服务 %s:%d", host.c_str(), port);
      receive_loop();
      close(sock_);
      sock_ = -1;
      RCLCPP_WARN(this->get_logger(), "连接断开，3 秒后重连...");
      std::this_thread::sleep_for(3s);
    }
  }

  bool try_connect(const std::string & host, int port) {
    sock_ = socket(AF_INET, SOCK_STREAM, 0);
    if (sock_ < 0) return false;

    struct timeval tv;
    tv.tv_sec = 3;
    tv.tv_usec = 0;
    setsockopt(sock_, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    setsockopt(sock_, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));

    struct sockaddr_in addr;
    std::memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);

    if (inet_pton(AF_INET, host.c_str(), &addr.sin_addr) <= 0) {
      close(sock_); sock_ = -1;
      return false;
    }

    if (connect(sock_, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
      close(sock_); sock_ = -1;
      return false;
    }

    return true;
  }

  void receive_loop() {
    while (running_ && rclcpp::ok()) {
      // 读取 4 字节长度前缀
      uint32_t len = 0;
      int ret = recv_all(&len, 4);
      if (ret <= 0) break;

      len = ntohl(len);
      if (len == 0 || len > 10 * 1024 * 1024) {  // 最大 10MB
        RCLCPP_WARN(this->get_logger(), "无效的图像长度: %u", len);
        continue;
      }

      // 读取 JPEG 数据
      std::vector<uint8_t> buffer(len);
      ret = recv_all(buffer.data(), len);
      if (ret <= 0) break;

      // 解码 JPEG
      cv::Mat frame = cv::imdecode(buffer, cv::IMREAD_COLOR);
      if (frame.empty()) {
        RCLCPP_WARN(this->get_logger(), "JPEG 解码失败");
        continue;
      }

      // 发布图像
      auto msg = cv_bridge::CvImage(
        std_msgs::msg::Header(), "bgr8", frame).toImageMsg();
      msg->header.stamp = this->now();
      msg->header.frame_id = "camera_frame";
      image_pub_->publish(*msg);
    }
  }

  int recv_all(void *buf, size_t len) {
    size_t received = 0;
    while (received < len) {
      int ret = recv(sock_, (char *)buf + received, len - received, 0);
      if (ret <= 0) return ret;
      received += ret;
    }
    return received;
  }

  rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr image_pub_;
  std::thread connect_thread_;
  int sock_ = -1;
  bool running_ = true;
};

int main(int argc, char ** argv) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<CameraBridgeNode>());
  rclcpp::shutdown();
  return 0;
}