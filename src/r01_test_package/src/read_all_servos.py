"""极简舵机读取 — 一次读取所有舵机角度，供 MuJoCo 联合仿真调用

用法:
    from read_all_servos import read_all_angles

    angles = read_all_angles()
    # {
    #     'teacher': {11: 12.3, 12: None, 13: -5.1, 14: 30.0, 15: None, 16: -90.0},
    #     'student':  {1:  45.0, 2:  None,  3: 10.2,  4: -20.0, 5:  None,  6: 60.0}
    # }

    # 或者直接取数组 (None → 0):
    t = [angles['teacher'].get(i, 0) or 0 for i in [11,12,13,14,15,16]]
    s = [angles['student'].get(i, 0)  or 0 for i in [1,2,3,4,5,6]]
"""
import time
from shared_serial import get_serial, release_serial

PORT = 'COM7'
BAUDRATE = 1000000
TEACHER_IDS = [11, 12, 13, 14, 15, 16]
STUDENT_IDS = [1, 2, 3, 4, 5, 6]

HEADER = 0xFF
INST_READ = 0x02
ADDR_POS = 56

# ── 全局串口 (懒加载) ──
_ser = None


def _checksum(packet):
    return (~sum(packet) & 0xFF)


def _read_raw(motor_id, timeout=0.05):
    packet = [motor_id, 4, INST_READ, ADDR_POS, 2]
    frame = bytearray([HEADER, HEADER] + packet + [_checksum(packet)])

    _ser.reset_input_buffer()
    _ser.write(frame)
    _ser.flush()

    t0 = time.time()
    buf = bytearray()
    while time.time() - t0 < timeout:
        if _ser.in_waiting:
            buf.extend(_ser.read(_ser.in_waiting))
            while len(buf) >= 6:
                if buf[0] != HEADER or buf[1] != HEADER:
                    buf.pop(0); continue
                if len(buf) < 4: break
                total = 4 + buf[3]
                if len(buf) < total: break
                if _checksum(buf[2:total - 1]) != buf[total - 1]:
                    buf.pop(0); continue
                data = bytes(buf[5:total - 1])
                return data[0] | (data[1] << 8)
    return None


def _raw_to_angle(raw):
    if raw is None:
        return None
    if raw > 32767:
        raw -= 65536
    return (raw - 2048) * 360.0 / 4096.0


def read_all_angles():
    """一次读取所有舵机，返回 {teacher: {id: angle}, student: {id: angle}}"""
    global _ser
    if _ser is None or not _ser.is_open:
        _ser = get_serial(PORT, BAUDRATE)

    teacher = {mid: _raw_to_angle(_read_raw(mid)) for mid in TEACHER_IDS}
    student = {mid: _raw_to_angle(_read_raw(mid)) for mid in STUDENT_IDS}
    return {'teacher': teacher, 'student': student}


def close():
    release_serial()


# ── 直接运行测试 ──
if __name__ == '__main__':
    try:
        while True:
            a = read_all_angles()
            print("T:", " ".join(f"{a['teacher'][i]:+6.2f}" if a['teacher'][i] is not None else "  --- " for i in TEACHER_IDS),
                  "| S:", " ".join(f"{a['student'][i]:+6.2f}" if a['student'][i] is not None else "  --- " for i in STUDENT_IDS))
            time.sleep(0.02)
    except KeyboardInterrupt:
        close()
        print("\n已断开。")