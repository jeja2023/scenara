"""Windows 平台动态加载 NVIDIA CUDA / cuDNN 运行时动态库支持。"""
from __future__ import annotations

import glob
import os
import site
import sys


def setup_nvidia_dll_directories() -> list[str]:
    """在 Windows 平台自动将 Python 环境中安装的 NVIDIA CUDA 12 / cuDNN 9 wheel 库路径

    注册到 Windows DLL 搜索目录和进程 PATH 中，确保 ONNX Runtime 及 C++ 扩展能正确加载
    CUDAExecutionProvider。
    """
    if sys.platform != "win32":
        return []

    added_dirs: list[str] = []
    search_roots: list[str] = []

    # 1. 收集 site-packages 根路径
    if hasattr(site, "getsitepackages"):
        try:
            site_packages = site.getsitepackages()
            if isinstance(site_packages, list):
                search_roots.extend([p for p in site_packages if isinstance(p, str)])

        except Exception:
            pass

    if hasattr(site, "getusersitepackages"):
        try:
            user_site = site.getusersitepackages()
            if isinstance(user_site, str):
                search_roots.append(user_site)
        except Exception:
            pass

    venv_site = os.path.join(sys.prefix, "Lib", "site-packages")
    if venv_site not in search_roots:
        search_roots.append(venv_site)


    # 2. 扫描所有 nvidia/*/bin 目录
    for root in search_roots:
        if not os.path.isdir(root):
            continue
        for bin_dir in glob.glob(os.path.join(root, "nvidia", "*", "bin")):
            if os.path.isdir(bin_dir) and bin_dir not in added_dirs:
                added_dirs.append(bin_dir)

    # 3. 扫描系统 CUDA 安装目录（例如 C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.*\bin）
    for cuda_root in glob.glob(r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v*\bin"):
        if os.path.isdir(cuda_root) and cuda_root not in added_dirs:
            added_dirs.append(cuda_root)

    if added_dirs:
        for directory in added_dirs:
            try:
                os.add_dll_directory(directory)
            except Exception:
                pass
        # 将目录追加到进程 PATH 前端，保证 C++ LoadLibrary 解析传递依赖
        os.environ["PATH"] = ";".join(added_dirs) + ";" + os.environ.get("PATH", "")

    return added_dirs


# 模块导入时自动执行初始化
setup_nvidia_dll_directories()
