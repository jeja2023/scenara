#!/usr/bin/env python3
"""Scenara 模型自动下载与校验脚本。

自动下载 Scenara 全领域（人像、OCR、姿态、人脸）生产与进阶模型文件至 models/ 目录，
支持国内镜像加速、进度条显示与自动解压。
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
MODELS_DIR = ROOT_DIR / "models"

# 统一模型清单（支持 GitHub 加速与百度官方直链）
MODEL_SPECS = [
    {
        "domain": "portrait",
        "name": "yolov8n.onnx (人体检测模型)",
        "target_file": MODELS_DIR / "yolov8n.onnx",
        "url": "https://ghproxy.net/https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8n.onnx",
        "backup_url": "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8n.onnx",
        "is_archive": False,
    },
    {
        "domain": "portrait",
        "name": "yolov8n-pose.pt (人体姿态关键点权重)",
        "target_file": MODELS_DIR / "yolov8n-pose.pt",
        "url": "https://ghproxy.net/https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n-pose.pt",
        "backup_url": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n-pose.pt",
        "is_archive": False,
    },
    {
        "domain": "ocr",
        "name": "ch_PP-OCRv4_det (PaddleOCR 文本检测模型)",
        "target_file": MODELS_DIR / "ocr" / "ch_PP-OCRv4_det_infer" / "inference.pdmodel",
        "target_dir": MODELS_DIR / "ocr",
        "url": "https://paddleocr.bj.bcebos.com/PP-OCRv4/chinese/ch_PP-OCRv4_det_infer.tar",
        "is_archive": True,
    },
    {
        "domain": "ocr",
        "name": "ch_PP-OCRv4_rec (PaddleOCR 文本识别模型)",
        "target_file": MODELS_DIR / "ocr" / "ch_PP-OCRv4_rec_infer" / "inference.pdmodel",
        "target_dir": MODELS_DIR / "ocr",
        "url": "https://paddleocr.bj.bcebos.com/PP-OCRv4/chinese/ch_PP-OCRv4_rec_infer.tar",
        "is_archive": True,
    },
    {
        "domain": "ocr",
        "name": "ch_ppocr_mobile_v2.0_cls (方向分类器模型)",
        "target_file": MODELS_DIR / "ocr" / "ch_ppocr_mobile_v2.0_cls_infer" / "inference.pdmodel",
        "target_dir": MODELS_DIR / "ocr",
        "url": "https://paddleocr.bj.bcebos.com/dygraph_v2.0/ch/ch_ppocr_mobile_v2.0_cls_infer.tar",
        "is_archive": True,
    },
]


def _download_file(url: str, dest_path: Path, desc: str) -> bool:
    """下载单个文件并显示进度。"""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = dest_path.with_suffix(dest_path.suffix + ".download")

    print(f"[*] 正在下载 {desc} ...")
    print(f"    源地址: {url}")

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as response, temp_path.open("wb") as out_file:
            total_size = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            block_size = 1024 * 1024  # 1MB 缓冲

            while True:
                buffer = response.read(block_size)
                if not buffer:
                    break
                downloaded += len(buffer)
                out_file.write(buffer)
                if total_size > 0:
                    percent = downloaded / total_size * 100
                    mb_down = downloaded / (1024 * 1024)
                    mb_total = total_size / (1024 * 1024)
                    sys.stdout.write(f"\r    进度: [{percent:5.1f}%] {mb_down:6.1f}MB / {mb_total:6.1f}MB")
                else:
                    mb_down = downloaded / (1024 * 1024)
                    sys.stdout.write(f"\r    已下载: {mb_down:6.1f}MB")
                sys.stdout.flush()

        print("\n    [+] 下载完成！")
        if temp_path.exists():
            shutil.move(str(temp_path), str(dest_path))
        return True
    except Exception as exc:
        print(f"\n    [-] 下载失败: {exc}")
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        return False


def _extract_tar(archive_path: Path, extract_dir: Path) -> bool:
    """解压 tar 归档文件。"""
    print(f"[*] 正在解压 {archive_path.name} 到 {extract_dir} ...")
    try:
        with tarfile.open(archive_path, "r:*") as tar:
            tar.extractall(path=extract_dir)
        print("    [+] 解压完成！")
        archive_path.unlink(missing_ok=True)
        return True
    except Exception as exc:
        print(f"    [-] 解压失败: {exc}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="下载 Scenara 生产与各领域模型文件")
    parser.add_argument(
        "--domain",
        choices=["all", "portrait", "ocr", "fashion", "behavior"],
        default="all",
        help="指定下载的模型领域（默认 all）",
    )
    parser.add_argument("--force", action="store_true", help="强制重新下载已有模型")
    args = parser.parse_args()

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    (MODELS_DIR / "ocr").mkdir(parents=True, exist_ok=True)
    (MODELS_DIR / "behavior").mkdir(parents=True, exist_ok=True)
    (MODELS_DIR / "fashion").mkdir(parents=True, exist_ok=True)

    print("=" * 65)
    print("[*] Scenara 模型自动准备工具")
    print(f"    目标存储目录: {MODELS_DIR}")
    print("=" * 65)

    success_count = 0
    total_count = 0

    for spec in MODEL_SPECS:
        if args.domain != "all" and spec["domain"] != args.domain:
            continue

        total_count += 1
        target_file: Path = spec["target_file"]

        # 检查是否已存在
        if target_file.exists() and not args.force:
            size_mb = target_file.stat().st_size / (1024 * 1024)
            print(f"[+] [已存在] {spec['name']} ({size_mb:.2f}MB) -> {target_file.relative_to(ROOT_DIR)}")
            success_count += 1
            continue

        url = spec["url"]
        if spec.get("is_archive"):
            tar_name = Path(url).name
            tar_path = spec["target_dir"] / tar_name
            ok = _download_file(url, tar_path, spec["name"])
            if not ok and "backup_url" in spec:
                print("    [!] 尝试备用源地址...")
                ok = _download_file(spec["backup_url"], tar_path, spec["name"])
            if ok:
                if _extract_tar(tar_path, spec["target_dir"]):
                    success_count += 1
        else:
            ok = _download_file(url, target_file, spec["name"])
            if not ok and "backup_url" in spec:
                print("    [!] 尝试备用源地址...")
                ok = _download_file(spec["backup_url"], target_file, spec["name"])
            if ok:
                success_count += 1

    print("\n" + "=" * 65)
    print(f"[+] 准备完成！共计 {success_count}/{total_count} 个模型文件已就绪。")
    print("=" * 65)
    return 0 if success_count == total_count else 1


if __name__ == "__main__":
    sys.exit(main())
