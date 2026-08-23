"""
清理并重启 Scenara 服务

停止占用 8000 端口的进程并重新启动
"""

import subprocess
import sys
import time

def kill_port_8000():
    """停止占用 8000 端口的进程"""
    print("正在查找占用 8000 端口的进程...")

    try:
        # 查找占用 8000 端口的进程
        result = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True,
            text=True,
        )

        lines = result.stdout.split('\n')
        pids = set()

        for line in lines:
            if ':8000 ' in line and 'LISTENING' in line:
                parts = line.split()
                if parts:
                    pid = parts[-1]
                    if pid.isdigit():
                        pids.add(pid)

        if pids:
            print(f"找到进程: {', '.join(pids)}")
            for pid in pids:
                try:
                    subprocess.run(["taskkill", "/F", "/PID", pid], check=True)
                    print(f"  已停止进程 {pid}")
                except Exception as e:
                    print(f"  停止进程 {pid} 失败: {e}")

            # 等待端口释放
            time.sleep(2)
            print("端口已释放")
        else:
            print("未找到占用 8000 端口的进程")

    except Exception as e:
        print(f"错误: {e}")

if __name__ == "__main__":
    kill_port_8000()

    print("\n" + "="*60)
    print("现在可以运行:")
    print("  python start.py")
    print("="*60)
