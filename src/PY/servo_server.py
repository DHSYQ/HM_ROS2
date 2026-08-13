"""舵机后台服务 — 独占 COM7，通过 TCP 对外提供读写接口"""
import json
import socket
import struct
import time
import threading

from shared_serial import get_serial, release_serial

# ── 协议常量 ──
HEADER = 0xFF
INST_READ = 0x02
INST_WRITE = 0x03
ADDR_PRESENT_POSITION = 56
ADDR_GOAL_POSITION = 42
ADDR_TORQUE_ENABLE = 40
ADDR_MOVING = 66

TEACHER_IDS = [11, 12, 13, 14, 15, 16]
STUDENT_IDS = [1, 2, 3, 4, 5, 6]

HOST = '127.0.0.1'
PORT = 9555  # 舵机服务端口

_ser_lock = threading.Lock()  # 串口互斥锁，防止多线程同时读写


def _checksum(packet):
    return (~sum(packet) & 0xFF)


def _read_register(ser, motor_id, address, length, timeout=0.015):
    packet = [motor_id, 4, INST_READ, address, length]
    frame = bytearray([HEADER, HEADER] + packet + [_checksum(packet)])
    ser.reset_input_buffer()
    ser.write(frame)
    ser.flush()
    t0 = time.time()
    buf = bytearray()
    while time.time() - t0 < timeout:
        if ser.in_waiting:
            buf.extend(ser.read(ser.in_waiting))
            while len(buf) >= 6:
                if buf[0] != HEADER or buf[1] != HEADER:
                    buf.pop(0); continue
                if len(buf) < 4: break
                total = 4 + buf[3]
                if len(buf) < total: break
                if _checksum(buf[2:total - 1]) != buf[total - 1]:
                    buf.pop(0); continue
                return bytes(buf[5:total - 1])
        time.sleep(0.0005)
    return None


def _write_register(ser, motor_id, address, data):
    length = len(data)
    packet = [motor_id, length + 3, INST_WRITE, address] + list(data)
    frame = bytearray([HEADER, HEADER] + packet + [_checksum(packet)])
    ser.reset_input_buffer()
    ser.write(frame)
    ser.flush()
    # 读掉状态应答
    t0 = time.time()
    buf = bytearray()
    while time.time() - t0 < 0.02:
        if ser.in_waiting:
            buf.extend(ser.read(ser.in_waiting))
            if len(buf) >= 6 and buf[0] == HEADER and buf[1] == HEADER:
                return buf[4] == 0
        time.sleep(0.0005)
    return False


def angle_to_raw(angle):
    raw = int(round(angle / 360.0 * 4096 + 2048))
    raw = max(-32767, min(32767, raw))
    if raw < 0:
        raw += 65536
    return raw


def raw_to_angle(raw):
    if raw > 32767:
        raw -= 65536
    return (raw - 2048) * 360.0 / 4096.0


def read_angle(ser, motor_id):
    data = _read_register(ser, motor_id, ADDR_PRESENT_POSITION, 2)
    if data is None or len(data) < 2:
        return None
    return raw_to_angle(data[0] | (data[1] << 8))


def read_all(ser, ids):
    with _ser_lock:
        return {mid: read_angle(ser, mid) for mid in ids}


def handle_client(conn, ser):
    """处理一个 TCP 客户端请求"""
    try:
        # 读取 4 字节长度头
        header = conn.recv(4)
        if len(header) < 4:
            return
        msg_len = struct.unpack('>I', header)[0]
        if msg_len > 65536:
            return

        body = b''
        while len(body) < msg_len:
            chunk = conn.recv(msg_len - len(body))
            if not chunk:
                return
            body += chunk

        req = json.loads(body.decode())
        cmd = req.get('cmd', '')

        if cmd == 'read_teacher':
            result = read_all(ser, TEACHER_IDS)
        elif cmd == 'read_student':
            result = read_all(ser, STUDENT_IDS)
        elif cmd == 'read_all':
            result = {
                'teacher': read_all(ser, TEACHER_IDS),
                'student': read_all(ser, STUDENT_IDS),
            }
        elif cmd == 'write_angle':
            mid = req['id']
            angle = req['angle']
            raw = angle_to_raw(angle)
            with _ser_lock:
                _write_register(ser, mid, ADDR_TORQUE_ENABLE, b'\x01')
                _write_register(ser, mid, ADDR_GOAL_POSITION,
                                bytes([raw & 0xFF, (raw >> 8) & 0xFF]))
            result = {'ok': True}
        elif cmd == 'follow':
            # 一次调用完成：读示教端 → 读学生端 → 写需要变的学生端
            # 注意：扭矩已在启动时开启，这里不再重复开
            pairs = req.get('pairs', {})  # {student_id: teacher_id}
            dead_zone = req.get('dead_zone', 0.3)
            with _ser_lock:
                t_angles = {mid: read_angle(ser, mid) for mid in TEACHER_IDS}
                s_angles = {mid: read_angle(ser, mid) for mid in STUDENT_IDS}
                written = []
                for s_id, t_id in pairs.items():
                    s_id = int(s_id); t_id = int(t_id)
                    t_a = t_angles.get(t_id)
                    s_a = s_angles.get(s_id)
                    if t_a is None or s_a is None:
                        continue
                    if abs(t_a - s_a) < dead_zone:
                        continue
                    raw = angle_to_raw(t_a)
                    _write_register(ser, s_id, ADDR_GOAL_POSITION,
                                    bytes([raw & 0xFF, (raw >> 8) & 0xFF]))
                    written.append(s_id)
            result = {'teacher': t_angles, 'student': s_angles, 'written': written}
        elif cmd == 'enable_torque':
            # 一次性给所有学生端开扭矩
            ids = req.get('ids', STUDENT_IDS)
            with _ser_lock:
                for mid in ids:
                    mid = int(mid)
                    _write_register(ser, mid, ADDR_TORQUE_ENABLE, b'\x01')
            result = {'ok': True}
        elif cmd == 'ping':
            result = {'ok': True}
        else:
            result = {'error': f'unknown command: {cmd}'}

        resp = json.dumps(result).encode()
        conn.sendall(struct.pack('>I', len(resp)) + resp)
    except Exception as e:
        try:
            err = json.dumps({'error': str(e)}).encode()
            conn.sendall(struct.pack('>I', len(err)) + err)
        except Exception:
            pass
    finally:
        conn.close()


def main():
    print(f"舵机后台服务启动: {HOST}:{PORT}")
    print(f"  Teacher: {TEACHER_IDS}")
    print(f"  Student: {STUDENT_IDS}")
    print()

    ser = get_serial()
    print(f"  串口 {ser.port} 已连接\n")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(5)
    server.settimeout(1.0)  # 每 1 秒检查一次 Ctrl+C
    print(f"  等待客户端连接... (Ctrl+C 停止)\n")

    try:
        while True:
            try:
                conn, addr = server.accept()
                threading.Thread(target=handle_client, args=(conn, ser), daemon=True).start()
            except socket.timeout:
                continue  # 超时后回到循环顶，检查 KeyboardInterrupt
    except KeyboardInterrupt:
        print("\n停止服务...")
    finally:
        server.close()
        release_serial()
        print("已断开。")


if __name__ == '__main__':
    main()