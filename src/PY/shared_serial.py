"""共享串口模块 — 所有脚本共用同一个 COM 口，避免冲突 + 自动重试"""
import time
from serial import Serial, SerialException

_PORT = 'COM7'
_BAUDRATE = 1000000
_ser = None
_ref_count = 0


def get_serial(port=None, baudrate=None):
    """获取共享串口对象。如果已打开则复用，否则创建。
       多个脚本/模块可以同时调用，不会产生冲突。
       如果端口被占用，自动重试几次。
    """
    global _ser, _ref_count, _PORT, _BAUDRATE

    if port is not None:
        _PORT = port
    if baudrate is not None:
        _BAUDRATE = baudrate

    if _ser is not None and _ser.is_open:
        _ref_count += 1
        return _ser

    # 自动重试：上一个脚本退出后 Windows 可能需要一点时间释放 COM 口
    for attempt in range(5):
        try:
            _ser = Serial(port=_PORT, baudrate=_BAUDRATE, timeout=0.1)
            _ref_count = 1
            return _ser
        except SerialException as e:
            if attempt < 4:
                print(f"  串口 {_PORT} 被占用，重试 {attempt+2}/5...")
                time.sleep(0.5)
            else:
                raise e

    return _ser


def release_serial():
    """释放一次引用。引用计数归零时才真正关闭串口。"""
    global _ser, _ref_count

    if _ref_count > 0:
        _ref_count -= 1

    if _ref_count == 0 and _ser is not None and _ser.is_open:
        _ser.close()
        _ser = None


def close_all():
    """强制关闭串口（无视引用计数）"""
    global _ser, _ref_count
    if _ser is not None and _ser.is_open:
        _ser.close()
        _ser = None
    _ref_count = 0