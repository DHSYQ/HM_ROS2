"""舵机客户端 — 通过 TCP 与 servo_server 通信，无需直接操作串口"""
import json
import socket
import struct

HOST = '127.0.0.1'
PORT = 9555


def _request(cmd, **kwargs):
    """发送请求，返回 JSON 结果"""
    req = {'cmd': cmd, **kwargs}
    body = json.dumps(req).encode()

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2.0)
    try:
        s.connect((HOST, PORT))
        s.sendall(struct.pack('>I', len(body)) + body)

        header = s.recv(4)
        if len(header) < 4:
            return None
        msg_len = struct.unpack('>I', header)[0]

        resp = b''
        while len(resp) < msg_len:
            chunk = s.recv(msg_len - len(resp))
            if not chunk:
                break
            resp += chunk
        return json.loads(resp.decode())
    except Exception as e:
        return {'error': str(e)}
    finally:
        s.close()


def read_teacher():
    """读取示教端 (ID 11-16) 角度 → {11: 12.3, 12: None, ...}"""
    return _request('read_teacher')


def read_student():
    """读取学生端 (ID 1-6) 角度 → {1: 45.0, 2: None, ...}"""
    return _request('read_student')


def read_all():
    """读取全部角度 → {'teacher': {...}, 'student': {...}}"""
    return _request('read_all')


def write_angle(motor_id, angle):
    """设置舵机角度 (°)"""
    return _request('write_angle', id=motor_id, angle=angle)


def follow(pairs, dead_zone=0.3):
    """一次调用完成：读示教 + 读学生 + 写差异
    pairs: {student_id: teacher_id}  如 {1: 11, 2: 12, ...}
    dead_zone: 死区 (°)
    返回: {'teacher': {...}, 'student': {...}, 'written': [1, 3, ...]}
    """
    return _request('follow', pairs=pairs, dead_zone=dead_zone)


def enable_torque(ids=None):
    """启动学生端舵机扭矩 (一次性)"""
    return _request('enable_torque', ids=ids or [1, 2, 3, 4, 5, 6])


def ping():
    """检查服务器是否在线"""
    r = _request('ping')
    return r is not None and r.get('ok') is True