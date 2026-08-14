"""Windows 端 — 摄像头 TCP 桥接

读取 USB 摄像头，JPEG 压缩后通过 TCP 发送给 WSL2。

用法:
    python camera_bridge.py [--port 5007] [--camera 0] [--fps 15] [--quality 80]

WSL2 端连接此端口接收图像数据。
"""

import socket
import struct
import argparse
import time
import cv2


def main():
    parser = argparse.ArgumentParser(description="摄像头 TCP 桥接")
    parser.add_argument("--port", type=int, default=5007, help="监听端口 (默认 5007)")
    parser.add_argument("--camera", type=int, default=0, help="摄像头索引 (默认 0)")
    parser.add_argument("--fps", type=int, default=15, help="发送帧率 (默认 15)")
    parser.add_argument("--quality", type=int, default=80, help="JPEG 质量 1-100 (默认 80)")
    args = parser.parse_args()

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print(f"[ERROR] 无法打开摄像头 {args.camera}")
        return

    print(f"[INFO] 摄像头已打开 (索引 {args.camera})")
    print(f"[INFO] 分辨率: {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}")
    print(f"[INFO] TCP 服务端已启动，监听端口 {args.port}，等待 WSL 连接...")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", args.port))
    server.listen(1)

    interval = 1.0 / args.fps

    try:
        while True:
            print(f"[INFO] 等待客户端连接...")
            conn, addr = server.accept()
            print(f"[INFO] 客户端已连接: {addr}")

            try:
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        print("[WARN] 读取帧失败，跳过")
                        time.sleep(0.01)
                        continue

                    # JPEG 压缩
                    _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, args.quality])

                    # 发送: 4 字节长度 + JPEG 数据
                    length = struct.pack(">I", len(jpeg))
                    conn.sendall(length + jpeg.tobytes())

                    time.sleep(interval)
            except (ConnectionResetError, BrokenPipeError):
                print(f"[WARN] 客户端断开: {addr}")
            finally:
                conn.close()
    except KeyboardInterrupt:
        print("\n[INFO] 用户中断")
    finally:
        cap.release()
        server.close()
        print("[INFO] 已退出")


if __name__ == "__main__":
    main()