"""Windows 端舵机桥接 — 读写合一，通过 servo_client 与 servo_server 通信

替代原来的 servo_tcp_server.py + command_tcp_server.py，避免 COM7 冲突。

用法:
    # 先启动 servo_server.py（唯一操作 COM7 的程序）
    python servo_server.py

    # 再启动桥接（读写合一）
    python servo_bridge.py

端口:
    :5005 → WSL2 读取舵机角度
    :5006 → WSL2 发送舵机命令
"""
import socket
import json
import struct
import time
import threading
from servo_client import read_student, write_angle, enable_torque, ping

READ_PORT = 5005
CMD_PORT = 5006
SERVO_IDS = [1, 2, 3, 4, 5, 6]


def read_angles():
    """通过 servo_client 读取学生端角度"""
    result = read_student()
    if result is None or 'error' in result:
        return {str(i): None for i in SERVO_IDS}
    return {str(i): result.get(str(i), result.get(i)) for i in SERVO_IDS}


def handle_command(data):
    """处理写舵机命令"""
    angles = data.get('angles', [])
    results = {}
    for i, angle in enumerate(angles):
        if i >= len(SERVO_IDS):
            break
        motor_id = SERVO_IDS[i]
        if angle is not None:
            resp = write_angle(motor_id, angle)
            results[str(motor_id)] = resp
        else:
            results[str(motor_id)] = {'skipped': True}
    return {'ok': True, 'results': results}


def run_read_server():
    """读取线程 — 监听 :5005，持续发送舵机角度"""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', READ_PORT))
    server.listen(1)
    print(f"[读取] 监听端口 {READ_PORT}，等待 WSL 连接...")

    while True:
        conn, addr = server.accept()
        print(f"[读取] 客户端已连接: {addr}")
        try:
            while True:
                angles = read_angles()
                data = {'timestamp': time.time(), 'angles': angles}
                msg = json.dumps(data).encode('utf-8')
                conn.sendall(struct.pack('!I', len(msg)) + msg)
                time.sleep(0.02)
        except (ConnectionResetError, BrokenPipeError):
            print(f"[读取] 客户端断开: {addr}")
        finally:
            conn.close()


def run_cmd_server():
    """命令线程 — 监听 :5006，接收命令并写入舵机"""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', CMD_PORT))
    server.listen(1)
    print(f"[命令] 监听端口 {CMD_PORT}，等待 WSL 连接...")

    while True:
        conn, addr = server.accept()
        print(f"[命令] 客户端已连接: {addr}")
        try:
            while True:
                header = conn.recv(4)
                if len(header) < 4:
                    break
                msg_len = struct.unpack('!I', header)[0]

                body = b''
                while len(body) < msg_len:
                    chunk = conn.recv(msg_len - len(body))
                    if not chunk:
                        break
                    body += chunk

                if len(body) < msg_len:
                    break

                data = json.loads(body.decode('utf-8'))
                result = handle_command(data)

                resp = json.dumps(result).encode('utf-8')
                conn.sendall(struct.pack('!I', len(resp)) + resp)
        except (ConnectionResetError, BrokenPipeError):
            print(f"[命令] 客户端断开: {addr}")
        finally:
            conn.close()


def main():
    if not ping():
        print("[ERROR] servo_server.py 未运行！请先启动: python servo_server.py")
        return

    print("[INFO] 启动舵机扭矩...")
    enable_torque()
    time.sleep(0.5)

    print("[INFO] 桥接服务启动中...")
    t1 = threading.Thread(target=run_read_server, daemon=True)
    t2 = threading.Thread(target=run_cmd_server, daemon=True)
    t1.start()
    t2.start()

    print("[INFO] 桥接服务已就绪（读取 :5005 | 命令 :5006）")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[INFO] 已关闭。")


if __name__ == '__main__':
    main()