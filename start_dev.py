"""
TransAnything 启动脚本
固定端口：后端18030，前端13010
"""

import os
import subprocess
import sys
import time
import signal
import json

# 项目根目录
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(PROJECT_DIR, "backend")
FRONTEND_DIR = os.path.join(PROJECT_DIR, "frontend")

# 固定端口
BACKEND_PORT = 18030
FRONTEND_PORT = 13010

# 子进程列表
processes = []


def find_python():
    """
    自动查找Python可执行文件
    优先查找conda环境中的python

    Returns:
        Python可执行文件路径
    """
    # 1. 通过conda命令查找
    try:
        result = subprocess.run(
            ["conda", "info", "--json"],
            capture_output=True, text=True, timeout=5, shell=True,
        )
        if result.returncode == 0:
            info = json.loads(result.stdout)
            # 检查envs列表
            for env_path in info.get("envs", []):
                python_exe = os.path.join(env_path, "python.exe")
                if os.path.exists(python_exe) and "transanything" in env_path:
                    return python_exe
            # 检查envs_dirs
            for envs_dir in info.get("envs_dirs", []):
                python_exe = os.path.join(envs_dir, "transanything", "python.exe")
                if os.path.exists(python_exe):
                    return python_exe
    except Exception:
        pass

    # 2. 常见conda安装路径
    common_paths = [
        os.path.join("D:", os.sep, "ProgramData", "anaconda3", "envs", "transanything", "python.exe"),
        os.path.join("C:", os.sep, "ProgramData", "anaconda3", "envs", "transanything", "python.exe"),
        os.path.join(os.path.expanduser("~"), "anaconda3", "envs", "transanything", "python.exe"),
        os.path.join(os.path.expanduser("~"), "miniconda3", "envs", "transanything", "python.exe"),
    ]
    for p in common_paths:
        if os.path.exists(p):
            return p

    # 3. 系统Python
    return sys.executable


def start_backend(port):
    """
    启动后端服务

    Args:
        port: 后端端口号
    """
    python_exe = find_python()

    proc = subprocess.Popen(
        [python_exe, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", f"--port={port}"],
        cwd=BACKEND_DIR,
    )
    processes.append(proc)
    print(f"[启动] 后端服务: http://localhost:{port}")


def start_frontend():
    """启动前端开发服务器"""
    # Windows下npm可能不在PATH中，尝试多种方式
    npm_cmd = "npm"
    for candidate in ["npm.cmd", "npm", "npx"]:
        result = subprocess.run(
            ["where", candidate],
            capture_output=True,
            shell=True,
        )
        if result.returncode == 0:
            npm_cmd = candidate
            break

    proc = subprocess.Popen(
        [npm_cmd, "run", "dev"],
        cwd=FRONTEND_DIR,
        shell=True,
    )
    processes.append(proc)
    print(f"[启动] 前端开发服务器: http://localhost:{FRONTEND_PORT}")


def cleanup(signum=None, frame=None):
    """清理所有子进程"""
    print("\n[停止] 正在停止所有服务...")
    for proc in processes:
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        except Exception:
            pass
    sys.exit(0)


def main():
    """主启动流程"""
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    print("=" * 50)
    print("  TransAnything 启动中...")
    print("=" * 50)

    # 1. 启动后端
    start_backend(BACKEND_PORT)

    # 2. 等待后端就绪
    print("[等待] 后端服务启动中...")
    import socket
    max_wait = 30
    for i in range(max_wait):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('127.0.0.1', BACKEND_PORT))
            sock.close()
            if result == 0:
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        print("[警告] 后端服务启动超时，继续启动前端...")

    # 3. 启动前端
    start_frontend()

    print("\n" + "=" * 50)
    print(f"  后端: http://localhost:{BACKEND_PORT}")
    print(f"  前端: http://localhost:{FRONTEND_PORT}")
    print("  按 Ctrl+C 停止所有服务")
    print("=" * 50 + "\n")

    # 4. 等待子进程
    try:
        for proc in processes:
            proc.wait()
    except KeyboardInterrupt:
        cleanup()


if __name__ == "__main__":
    main()
