"""Windows 端 TCP 服务端 — 读取 1-6 号舵机角度，通过 TCP 发送给 WSL 中的 ROS2 节点

用法（在 Windows 上运行）:
    python servo_tcp_server.py
    # 默认监听 0.0.0.0:5005，WSL2 通过 Windows IP 连接
"""
import socket
import json
import time
import struct
from shared_serial import get_serial, release_serial

PORT = 'COM7'
BAUDRATE = 1000000
TCP_PORT = 5005
SERVO_IDS = [1, 2, 3, 4, 5, 6]

HEADER = 0xFF
INST_READ = 0x02
ADDR_POS = 56


def _checksum(packet):
    return (~sum(packet) & 0xFF)


def read_servo_angles(ser):
    """读取 1-6 号舵机，返回 {id: angle_deg, ...}"""
    result = {}
    for motor_id in SERVO_IDS:
        packet = [motor_id, 4, INST_READ, ADDR_POS, 2]
        frame = bytearray([HEADER, HEADER] + packet + [_checksum(packet)])

        ser.reset_input_buffer()
        ser.write(frame)
        ser.flush()

        t0 = time.time()
        buf = bytearray()
        raw = None
        while time.time() - t0 < 0.05:
            if ser.in_waiting:
                buf.extend(ser.read(ser.in_waiting))
                while len(buf) >= 6:
                    if buf[0] != HEADER or buf[1] != HEADER:
                        buf.pop(0)
                        continue
                    if len(buf) < 4:
                        break
                    total = 4 + buf[3]
                    if len(buf) < total:
                        break
                    if _checksum(buf[2:total - 1]) != buf[total - 1]:
                        buf.pop(0)
                        continue
                    data = bytes(buf[5:total - 1])
                    raw = data[0] | (data[1] << 8)
                    buf = buf[total:]
                    break

        if raw is not None:
            if raw > 32767:
                raw -= 65536
            angle = (raw - 2048) * 360.0 / 4096.0
            result[motor_id] = round(angle, 2)
        else:
            result[motor_id] = None

    return result


def main():
    print(f"[INFO] 打开串口 {PORT}...")
    ser = get_serial(PORT, BAUDRATE)
    print(f"[INFO] 串口已打开")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', TCP_PORT))
    server.listen(1)
    print(f"[INFO] TCP 服务端已启动，监听端口 {TCP_PORT}，等待 WSL 连接...")

    try:
        while True:
            conn, addr = server.accept()
            print(f"[INFO] 客户端已连接: {addr}")
            try:
                while True:
                    # 读取舵机角度
                    angles = read_servo_angles(ser)

                    # 构造 JSON 消息
                    data = {
                        'timestamp': time.time(),
                        'angles': angles
                    }
                    msg = json.dumps(data).encode('utf-8')

                    # 发送: 4 字节长度 + 数据
                    conn.sendall(struct.pack('!I', len(msg)) + msg)

                    time.sleep(0.02)  # 50Hz
            except (ConnectionResetError, BrokenPipeError):
                print(f"[WARN] 客户端断开: {addr}")
            finally:
                conn.close()
    except KeyboardInterrupt:
        print("\n[INFO] 正在关闭...")
    finally:
        server.close()
        release_serial()
        print("[INFO] 已关闭。")


if __name__ == '__main__':
    main()