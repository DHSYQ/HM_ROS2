cmake_minimum_required(VERSION 3.8)
project(r01_test_package)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(nlohmann_json REQUIRED)

# r01_test_node (原有)
add_executable(r01_test_node src/r01_test_node.cpp)
target_include_directories(r01_test_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include/${PROJECT_NAME}>)
target_compile_features(r01_test_node PUBLIC c_std_99 cxx_std_17)

# r02_servo_bridge_node (TCP 桥接节点)
add_executable(r02_servo_bridge_node src/r02_servo_bridge_node.cpp)
target_include_directories(r02_servo_bridge_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include/${PROJECT_NAME}>)
ament_target_dependencies(r02_servo_bridge_node
  rclcpp
  sensor_msgs
  nlohmann_json)
target_compile_features(r02_servo_bridge_node PUBLIC cxx_std_17)

# r03_servo_cmd_node (舵机命令节点)
add_executable(r03_servo_cmd_node src/r03_servo_cmd_node.cpp)
target_include_directories(r03_servo_cmd_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include/${PROJECT_NAME}>)
ament_target_dependencies(r03_servo_cmd_node
  rclcpp
  std_msgs)
target_compile_features(r03_servo_cmd_node PUBLIC cxx_std_17)

install(TARGETS r01_test_node r02_servo_bridge_node r03_servo_cmd_node
  DESTINATION lib/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  set(ament_cmake_copyright_FOUND TRUE)
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()