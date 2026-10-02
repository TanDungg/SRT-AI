#!/usr/bin/env python3
"""
Hoạt hình vẽ tay nét liền - Kịch bản khởi tạo môi trường

Nhiệm vụ:
  1. Tạo môi trường ảo Python cô lập trong thư mục dự án (tái sử dụng nếu đã tồn tại)
  2. Kiểm tra các thư viện bên thứ ba cần thiết
  3. Tự động cài đặt các thư viện còn thiếu
  4. In ra ENV_PY=<đường dẫn python> ở dòng cuối để các script khác sử dụng

Cách dùng:
  python prepare_env.py          # Tạo môi trường + cài thư viện, in ra ENV_PY
  python prepare_env.py --check  # Chỉ kiểm tra, thoát với mã lỗi nếu thiếu
"""
from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path

# Đảm bảo in tiếng Việt không bị lỗi UnicodeEncodeError trên Windows
if sys.platform.startswith("win"):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Thư mục gốc = script cha 2 cấp
SKILL_ROOT = Path(__file__).resolve().parent.parent
VENV_ROOT = SKILL_ROOT / ".venv"

# Tên import trong code -> Tên gói cài qua pip
DEPS: dict[str, str] = {
    "cv2": "opencv-python",
    "numpy": "numpy",
    "av": "av",  # PyAV: Mã hóa H.264 qua pip, không cần cài ffmpeg hệ thống
    "PIL": "Pillow",  # render_annotation_preview.py vẽ nhãn xem trước
    "huggingface_hub": "huggingface_hub",  # Tích hợp sinh ảnh qua Hugging Face FLUX
}


def interpreter_path() -> Path:
    """Đường dẫn thực thi Python trong môi trường ảo (đa nền tảng)."""
    if sys.platform.startswith("win"):
        return VENV_ROOT / "Scripts" / "python.exe"
    return VENV_ROOT / "bin" / "python"


def ensure_venv(check_only: bool) -> Path:
    py = interpreter_path()
    if VENV_ROOT.exists() and py.exists():
        print(f"[ok] Tái sử dụng môi trường ảo hiện có: {VENV_ROOT}")
        return py

    if check_only:
        print(f"[err] Môi trường ảo chưa được tạo: {VENV_ROOT}")
        sys.exit(1)

    print(f"[..] Đang tạo môi trường ảo: {VENV_ROOT}")
    venv.create(str(VENV_ROOT), with_pip=True)
    print("[ok] Môi trường ảo đã sẵn sàng")
    return py


def can_import(py: Path, import_name: str) -> bool:
    probe = subprocess.run(
        [str(py), "-c", f"import {import_name}"],
        capture_output=True,
    )
    return probe.returncode == 0


def install(py: Path, packages: list[str]) -> bool:
    if not packages:
        return True
    print(f"[..] Đang cài đặt thư viện: {', '.join(packages)}")
    res = subprocess.run(
        [str(py), "-m", "pip", "install", "--quiet", *packages],
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        print(f"[err] Cài đặt thất bại:\n{res.stderr}")
        return False
    print("[ok] Cài đặt thư viện hoàn tất")
    return True


def main() -> None:
    check_only = "--check" in sys.argv

    py = ensure_venv(check_only)

    missing: list[str] = []
    for import_name, pip_name in DEPS.items():
        if can_import(py, import_name):
            print(f"[ok] {pip_name}")
        else:
            print(f"[miss] {pip_name}")
            missing.append(pip_name)

    if missing:
        if check_only:
            print(f"\nThiếu {len(missing)} thư viện: {', '.join(missing)}")
            sys.exit(1)
        if not install(py, missing):
            sys.exit(1)

    # Dòng cuối: quy ước in ra để bên gọi bắt được
    print(f"\nENV_PY={py}")


if __name__ == "__main__":
    main()
