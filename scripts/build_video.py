#!/usr/bin/env python3
"""
Tự động hóa toàn trình: Render và ghép tất cả các phân cảnh thành 1 video hoàn chỉnh chỉ với 1 lệnh duy nhất.

Cách dùng:
  python scripts/build_video.py <thư_mục_chứa_các_cảnh> -o <video_hoan_chinh.mp4>
  python scripts/build_video.py examples -o output/video_tong_hop.mp4 --fps 24 --cap-long-edge 720
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

if sys.platform.startswith("win"):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_SCRIPT_DIR = Path(__file__).resolve().parent
_ENV_PY = _SCRIPT_DIR.parent / ".venv" / ("Scripts" if sys.platform.startswith("win") else "bin") / ("python.exe" if sys.platform.startswith("win") else "python")
PYTHON_EXEC = str(_ENV_PY) if _ENV_PY.exists() else sys.executable


def find_scene_pairs(folder: Path) -> list[tuple[Path, Path]]:
    """Tìm tất cả các cặp file (scene-*.png, scene-*.annotation.json) được sắp xếp theo thứ tự."""
    png_files = sorted(folder.glob("*.png"))
    pairs: list[tuple[Path, Path]] = []

    for png in png_files:
        if png.name.startswith("preview") or png.name.endswith("-preview.png"):
            continue
        # Tìm file annotation json tương ứng
        json_candidates = [
            png.with_suffix(".annotation.json"),
            png.with_name(png.stem + ".json"),
        ]
        ann = next((c for c in json_candidates if c.exists()), None)
        if ann:
            pairs.append((png, ann))

    return pairs


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Một lệnh tự động hóa toàn bộ quy trình: Render từng cảnh và tự ghép thành video hoàn chỉnh"
    )
    parser.add_argument("scene_dir", help="Thư mục chứa các ảnh và file annotation (ví dụ: examples hoặc assets/whiteboard/du-an-1)")
    parser.add_argument("-o", "--output", default="output/video_hoan_chinh.mp4", help="Đường dẫn file video thành phẩm xuất ra")
    parser.add_argument("--fps", type=int, default=24, help="Số khung hình/giây (mặc định: 24)")
    parser.add_argument("--cap-long-edge", type=int, default=720, help="Giới hạn cạnh dài pixel (mặc định: 720 để render nhanh và nhẹ)")
    parser.add_argument("--keep-scenes", action="store_true", help="Giữ lại các file video scene đơn lẻ sau khi ghép xong")
    args = parser.parse_args(argv)

    scene_folder = Path(args.scene_dir)
    if not scene_folder.exists() or not scene_folder.is_dir():
        print(f"[err] Thư mục không tồn tại: {scene_folder}", file=sys.stderr)
        return 1

    pairs = find_scene_pairs(scene_folder)
    if not pairs:
        print(f"[err] Không tìm thấy cặp ảnh PNG và annotation JSON nào trong: {scene_folder}", file=sys.stderr)
        return 1

    out_final = Path(args.output).resolve()
    out_final.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = out_final.parent / "_temp_scenes"
    temp_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("🎬 TỰ ĐỘNG HÓA TẠO VIDEO BẢNG TRẮNG HOÀN CHỈNH")
    print("=" * 60)
    print(f"📁 Thư mục nguồn : {scene_folder}")
    print(f"🎯 Video đầu ra  : {out_final}")
    print(f"🎞️  Tìm thấy     : {len(pairs)} phân cảnh kịch bản:")
    for i, (png, ann) in enumerate(pairs, start=1):
        print(f"   [{i}] {png.name} + {ann.name}")
    print("-" * 60)

    scene_videos: list[Path] = []
    render_script = _SCRIPT_DIR / "render_stream_whiteboard.py"
    merge_script = _SCRIPT_DIR / "merge_scenes.py"

    # Bước 1: Render từng phân cảnh
    for idx, (png, ann) in enumerate(pairs, start=1):
        scene_mp4 = temp_dir / f"scene_{idx:02d}.mp4"
        print(f"\n▶ Đang render phân cảnh {idx}/{len(pairs)}: {png.stem}...")

        cmd = [
            PYTHON_EXEC,
            str(render_script),
            str(png),
            str(ann),
            str(scene_mp4),
            "--fps", str(args.fps),
            "--cap-long-edge", str(args.cap_long_edge),
        ]

        res = subprocess.run(cmd)
        if res.returncode != 0 or not scene_mp4.exists():
            print(f"[err] Lỗi khi render cảnh {idx}: {png.name}", file=sys.stderr)
            return 1
        scene_videos.append(scene_mp4)

    # Bước 2: Tự động ghép nối các phân cảnh
    print("\n" + "-" * 60)
    print(f"🔗 Đang ghép nối {len(scene_videos)} phân cảnh thành video hoàn chỉnh...")
    merge_cmd = [
        PYTHON_EXEC,
        str(merge_script),
        *[str(v) for v in scene_videos],
        "-o", str(out_final),
    ]

    res_merge = subprocess.run(merge_cmd)
    if res_merge.returncode != 0 or not out_final.exists():
        print(f"[err] Ghép video thất bại!", file=sys.stderr)
        return 1

    # Dọn dẹp các video tạm nếu không giữ lại
    if not args.keep_scenes:
        for sv in scene_videos:
            sv.unlink(missing_ok=True)
        try:
            temp_dir.rmdir()
        except OSError:
            pass

    size_mb = out_final.stat().st_size / (1024 * 1024)
    print("\n" + "=" * 60)
    print(f"✅ HOÀN TẤT! Video thành phẩm đã sẵn sàng:")
    print(f"👉 File : {out_final}")
    print(f"📊 Size : {size_mb:.2f} MB")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
