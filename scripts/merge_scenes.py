#!/usr/bin/env python3
"""
Ghép nối nhiều cảnh: Ghép các video MP4 hoạt hình bảng trắng theo thứ tự thành một video hoàn chỉnh.

Ưu tiên dùng ffmpeg hệ thống để ghép nối không mất dữ liệu (-c copy, không mã hóa lại);
khi kích thước/chuẩn nén các đoạn không đồng nhất hoặc không có ffmpeg, sẽ chuyển sang
dùng PyAV để mã hóa lại từng khung hình và co giãn viền theo kích thước đoạn đầu tiên. Các đoạn lẻ vẫn giữ nguyên.

Cách dùng:
  <ENV_PY> merge_scenes.py --inputs a.mp4 b.mp4 c.mp4 --output final.mp4
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Đảm bảo in tiếng Việt không bị lỗi UnicodeEncodeError trên Windows
if sys.platform.startswith("win"):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _ffmpeg_concat_copy(inputs: list[Path], output: Path) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return False
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        for p in inputs:
            safe_path = p.resolve().as_posix().replace("'", "'\\''")
            f.write(f"file '{safe_path}'\n")
        list_path = Path(f.name)
    try:
        res = subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
             "-i", str(list_path), "-c", "copy", str(output)],
            capture_output=True, text=True,
        )
        if res.returncode == 0 and output.exists() and output.stat().st_size > 0:
            print(f"  ffmpeg ghép nối không mất dữ liệu thành công: {output}")
            return True
        print(f"  [warn] ffmpeg -c copy thất bại, thử mã hóa lại: {res.stderr.strip()[:200]}")
        res = subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
             "-i", str(list_path), "-c:v", "libx264", "-crf", "20",
             "-pix_fmt", "yuv420p", "-vf", "scale='trunc(iw/2)*2':'trunc(ih/2)*2'", str(output)],
            capture_output=True, text=True,
        )
        if res.returncode == 0 and output.exists() and output.stat().st_size > 0:
            print(f"  ffmpeg mã hóa lại và ghép nối thành công: {output}")
            return True
        print(f"  [warn] ffmpeg mã hóa lại cũng thất bại: {res.stderr.strip()[:200]}")
        return False
    except Exception as e:
        print(f"  [warn] Lỗi thực thi ffmpeg: {e}")
        return False
    finally:
        list_path.unlink(missing_ok=True)


def _pyav_concat(inputs: list[Path], output: Path) -> bool:
    try:
        import av
    except ImportError:
        return False
    try:
        first = av.open(str(inputs[0]))
        if not first.streams.video:
            first.close()
            print(f"  [warn] {inputs[0]} không chứa video stream")
            return False
        vs = first.streams.video[0]
        w = getattr(vs, "width", None) or getattr(vs.codec_context, "width", None) or 1280
        h = getattr(vs, "height", None) or getattr(vs.codec_context, "height", None) or 720
        rate = getattr(vs, "average_rate", None) or getattr(vs, "guessed_rate", None) or 30
        first.close()

        out = av.open(str(output), mode="w")
        ostream = out.add_stream("h264", rate=rate)
        ostream.width, ostream.height = w, h
        ostream.pix_fmt = "yuv420p"
        ostream.options = {"crf": "24", "preset": "medium"}

        pts_counter = 0
        for p in inputs:
            cont = av.open(str(p))
            if not cont.streams.video:
                cont.close()
                continue
            for frame in cont.decode(video=0):
                if frame.width != w or frame.height != h:
                    frame = frame.reformat(width=w, height=h)
                frame.pts = pts_counter
                pts_counter += 1
                for pkt in ostream.encode(frame):
                    out.mux(pkt)
            cont.close()

        for pkt in ostream.encode():
            out.mux(pkt)
        out.close()
        print(f"  PyAV ghép nối thành công: {output}")
        return True
    except Exception as e:
        print(f"  [warn] Lỗi ghép nối bằng PyAV: {e}")
        output.unlink(missing_ok=True)
        return False


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Ghép nối các video MP4 hoạt hình bảng trắng theo thứ tự")
    p.add_argument("files", nargs="*", help="Danh sách MP4 theo thứ tự (truyền trực tiếp)")
    p.add_argument("--inputs", "-i", nargs="+", default=None, help="Danh sách MP4 theo thứ tự phát")
    p.add_argument("--output", "-o", required=True, help="Đường dẫn file xuất sau khi ghép")
    args = p.parse_args(argv)

    raw_inputs = args.inputs if args.inputs is not None else args.files
    if not raw_inputs:
        print("[err] Vui lòng cung cấp danh sách file video đầu vào (--inputs hoặc tham số trực tiếp)", file=sys.stderr)
        return 1

    inputs = [Path(x) for x in raw_inputs]
    missing = [str(x) for x in inputs if not x.exists()]
    if missing:
        print(f"[err] Thiếu file đầu vào: {', '.join(missing)}", file=sys.stderr)
        return 1
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    if _ffmpeg_concat_copy(inputs, output) or _pyav_concat(inputs, output):
        print(f"OUTPUT={output.resolve()}")
        return 0
    print("[err] Ghép nối thất bại: Hệ thống không có ffmpeg và PyAV không khả dụng", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
