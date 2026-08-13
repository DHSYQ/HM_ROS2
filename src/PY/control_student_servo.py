"""控制学生端舵机转动到指定角度 — 通过 servo_server 通信"""
import time
from servo_client import read_student, write_angle, ping

# ── 配置 ──────────────────────────────────────────
STUDENT_IDS = [1, 2, 3, 4, 5, 6]


def move_to_angle(motor_id, angle, timeout=5.0):
    """设置目标角度，轮询等待运动完成，返回最终角度"""
    write_angle(motor_id, angle)

    t0 = time.time()
    while time.time() - t0 < timeout:
        result = read_student()
        if result is None or 'error' in result:
            continue
        current = result.get(str(motor_id), result.get(motor_id))
        if current is None:
            continue
        # 检查是否到达（误差 < 0.2° 认为到位）
        if abs(current - angle) < 0.3:
            return current
        time.sleep(0.01)
    # 超时
    result = read_student()
    if result and 'error' not in result:
        return result.get(str(motor_id), result.get(motor_id))
    return None


# ── 命令行交互 ────────────────────────────────────
if __name__ == '__main__':
    if not ping():
        print("错误: 舵机服务器未运行！请先启动: python servo_server.py")
        exit(1)

    print(f"学生端舵机控制  |  ID: {STUDENT_IDS}")
    print("命令:  <ID> <角度>  如 1 45  (ID 1 转到 45°)")
    print("       read          读取所有角度")
    print("       q             退出\n")

    try:
        while True:
            cmd = input("> ").strip().split()
            if not cmd:
                continue

            if cmd[0] == 'q':
                break

            elif cmd[0] == 'read':
                result = read_student()
                if result is None or 'error' in result:
                    print(f"  读取失败: {result}")
                    continue
                for mid in STUDENT_IDS:
                    a = result.get(str(mid), result.get(mid))
                    if a is not None:
                        print(f"  ID {mid:2d}: {a:+7.2f}°")
                    else:
                        print(f"  ID {mid:2d}: 超时")

            else:
                if len(cmd) < 2:
                    print("  用法: <ID> <角度>  如 1 45")
                    continue
                mid = int(cmd[0])
                angle = float(cmd[1])
                print(f"  ID {mid} → {angle:+.1f}°  ...", end=" ", flush=True)
                final = move_to_angle(mid, angle)
                print(f"到达: {final:+.2f}°" if final is not None else "超时")

    except KeyboardInterrupt:
        pass
    print("已退出。")