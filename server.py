#!/usr/bin/env python3
"""
Whiteboard Studio AI - Máy chủ cục bộ tích hợp Web Frontend
Khởi động máy chủ web tại http://localhost:8000
"""
from __future__ import annotations

import cgi
import datetime
import http.server
import json
import os
import platform
import socketserver
import subprocess
import sys
import threading
import shutil
import urllib.parse
from pathlib import Path

# Đảm bảo UTF-8 trên Windows
if sys.platform.startswith("win"):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PORT = int(os.environ.get("PORT", 8000))
ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
OUTPUT_DIR = ROOT / "output"
UPLOADS_DIR = ROOT / "uploads"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

try:
    from scripts.embedded_hand import ensure_drawing_hand
    ensure_drawing_hand(ROOT / "assets" / "drawing-hand.png")
except Exception as _e:
    pass

ENV_PY = ROOT / ".venv" / ("Scripts" if sys.platform.startswith("win") else "bin") / ("python.exe" if sys.platform.startswith("win") else "python")
PYTHON_EXEC = str(ENV_PY) if ENV_PY.exists() else sys.executable


class StudioHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(url.path)

        if path in ("/", "/index.html"):
            index_file = WEB_DIR / "index.html"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(index_file.read_bytes())
            return

        if path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = {"ok": True, "version": platform.python_version(), "py": PYTHON_EXEC}
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        if path == "/api/ai-config":
            from scripts.ai_service import load_config
            cfg = load_config()
            self.send_json({"ok": True, "config": cfg})
            return

        # Hỗ trợ tải trực tiếp video với Content-Disposition attachment
        if path.startswith("/output/") and path.endswith(".mp4"):
            file_path = ROOT / path.lstrip("/")
            if file_path.exists():
                query = urllib.parse.parse_qs(url.query)
                if "download" in query or "dl" in query:
                    filename = query.get("name", ["whiteboard_video_complete.mp4"])[0]
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                    self.send_header("Content-Length", str(file_path.stat().st_size))
                    self.end_headers()
                    with open(file_path, "rb") as f:
                        shutil.copyfileobj(f, self.wfile, length=64*1024)
                    return

        # Loại bỏ query string ?t=... và unquote để SimpleHTTPRequestHandler tìm đúng file
        self.path = path
        super().do_GET()

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(url.path)

        if path == "/api/save-ai-config":
            self.handle_save_ai_config()
            return

        if path == "/api/generate-script":
            self.handle_generate_script()
            return

        if path == "/api/generate-images":
            self.handle_generate_images()
            return

        if path == "/api/render-custom-project":
            self.handle_render_custom_project()
            return

        if path == "/api/regenerate-scene":
            self.handle_regenerate_scene()
            return

        if path == "/api/upload":
            self.handle_upload()
            return

        if path == "/api/render-stream":
            self.handle_render_stream()
            return

        if path == "/api/render-multi":
            self.handle_render_multi()
            return

        self.send_error(404, "Endpoint not found")

    def handle_upload(self):
        try:
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": self.headers["Content-Type"]}
            )
            if "image" not in form:
                self.send_json({"ok": False, "error": "Không tìm thấy file ảnh tải lên"}, 400)
                return

            fileitem = form["image"]
            orig_filename = Path(fileitem.filename).name if fileitem.filename else "upload.png"
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = UPLOADS_DIR / f"{ts}_{orig_filename}"

            with open(save_path, "wb") as f:
                f.write(fileitem.file.read())

            rel_path = save_path.relative_to(ROOT).as_posix()
            self.send_json({"ok": True, "path": rel_path})
        except Exception as e:
            self.send_json({"ok": False, "error": str(e)}, 500)

    def handle_render_stream(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            req = json.loads(body.decode("utf-8"))

            image_path = ROOT / req.get("image", "")
            if not image_path.exists():
                self.send_json({"ok": False, "error": f"Không tìm thấy ảnh: {image_path}"}, 400)
                return

            total_ms = req.get("total_ms", 8000)
            gaze_sec = req.get("gaze_seconds", 1.2)
            fps = req.get("fps", 24)

            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            render_script = ROOT / "scripts" / "stream_render.py"

            cmd = [
                PYTHON_EXEC,
                str(render_script),
                str(image_path),
                "--out-dir", str(OUTPUT_DIR),
                "--total-ms", str(total_ms),
                "--fps", str(fps),
                "--gaze", str(gaze_sec),
            ]

            res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if res.returncode != 0:
                self.send_json({"ok": False, "error": res.stderr or res.stdout}, 500)
                return

            # Tìm file video vừa tạo
            out_video = None
            for line in res.stdout.splitlines():
                if line.startswith("OUTPUT="):
                    out_video = Path(line.split("=", 1)[1].strip())
                    break

            if not out_video or not out_video.exists():
                # Tìm video mới nhất trong output
                mp4s = sorted(OUTPUT_DIR.glob("stream_*_h264.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
                if mp4s:
                    out_video = mp4s[0]

            if not out_video or not out_video.exists():
                self.send_json({"ok": False, "error": "Render hoàn tất nhưng không tìm thấy file xuất"}, 500)
                return

            video_url = "/" + out_video.relative_to(ROOT).as_posix()
            self.send_json({"ok": True, "video_url": video_url})
        except Exception as e:
            self.send_json({"ok": False, "error": str(e)}, 500)

    def handle_render_multi(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            req = json.loads(body.decode("utf-8"))

            folder = ROOT / req.get("folder", "")
            if not folder.exists() or not folder.is_dir():
                self.send_json({"ok": False, "error": f"Thư mục không tồn tại: {folder}"}, 400)
                return

            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            out_file = OUTPUT_DIR / f"multi_{ts}.mp4"
            build_script = ROOT / "scripts" / "build_video.py"

            cmd = [
                PYTHON_EXEC,
                str(build_script),
                str(folder),
                "-o", str(out_file),
                "--fps", str(req.get("fps", 24)),
            ]

            res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if res.returncode != 0 or not out_file.exists():
                self.send_json({"ok": False, "error": res.stderr or res.stdout}, 500)
                return

            video_url = "/" + out_file.relative_to(ROOT).as_posix()
            self.send_json({"ok": True, "video_url": video_url})
        except Exception as e:
            self.send_json({"ok": False, "error": str(e)}, 500)

    def handle_save_ai_config(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            req = json.loads(body.decode("utf-8"))
            from scripts.ai_service import save_config
            saved = save_config(req)
            self.send_json({"ok": True, "config": saved})
        except Exception as e:
            self.send_json({"ok": False, "error": str(e)}, 500)

    def handle_generate_script(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            req = json.loads(body.decode("utf-8"))

            topic = req.get("topic", "").strip() or "Bí quyết thành công"
            scene_count = int(req.get("scene_count", 2))
            ratio = req.get("ratio", "16:9")
            api_key = req.get("api_key", "").strip()
            provider = req.get("provider", "gemini").strip()

            from scripts.auto_storyboard import generate_script, safe_slug
            scenes = generate_script(topic, scene_count, ratio=ratio, api_key=api_key, provider=provider)

            # Khởi tạo thư mục dự án và gán trước đường dẫn ảnh
            project_dir = ROOT / "assets" / "whiteboard" / f"proj_{safe_slug(topic)}"
            project_dir.mkdir(parents=True, exist_ok=True)

            for sc in scenes:
                idx = sc["sceneIndex"]
                img_path = project_dir / f"scene_{idx:02d}.png"
                sc["imagePath"] = img_path.relative_to(ROOT).as_posix()

            self.send_json({
                "ok": True,
                "scenes": scenes,
                "project_folder": project_dir.relative_to(ROOT).as_posix()
            })
        except Exception as e:
            self.send_json({"ok": False, "error": str(e)}, 500)

    def handle_generate_images(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            req = json.loads(body.decode("utf-8"))

            scenes = req.get("scenes", [])
            ratio = req.get("ratio", "16:9")
            api_key = req.get("api_key", "").strip()
            provider = req.get("provider", "gemini").strip()
            image_provider = req.get("image_provider", "").strip()

            from scripts.auto_storyboard import draw_doodle_scene
            for sc in scenes:
                img_path = ROOT / sc.get("imagePath", "")
                img_path.parent.mkdir(parents=True, exist_ok=True)
                draw_doodle_scene(sc, ratio, img_path, api_key=api_key, provider=provider, image_provider=image_provider)

            self.send_json({"ok": True, "scenes": scenes})
        except Exception as e:
            self.send_json({"ok": False, "error": str(e)}, 500)

    def handle_regenerate_scene(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            req = json.loads(body.decode("utf-8"))

            scene = req.get("scene", {})
            ratio = req.get("ratio", "16:9")
            curr_path = req.get("imagePath", "")
            api_key = req.get("api_key", "").strip()
            provider = req.get("provider", "gemini").strip()
            image_provider = req.get("image_provider", "").strip()

            from scripts.auto_storyboard import draw_doodle_scene, safe_slug
            if curr_path:
                out_path = ROOT / curr_path
            else:
                out_path = ROOT / "assets" / "whiteboard" / f"proj_{safe_slug(scene.get('title', 'scene'))}" / f"scene_{scene.get('sceneIndex', 1):02d}.png"

            out_path.parent.mkdir(parents=True, exist_ok=True)
            draw_doodle_scene(scene, ratio, out_path, api_key=api_key, provider=provider, image_provider=image_provider)
            rel_path = out_path.relative_to(ROOT).as_posix()
            self.send_json({"ok": True, "imagePath": rel_path})
        except Exception as e:
            self.send_json({"ok": False, "error": str(e)}, 500)

    def handle_render_custom_project(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            req = json.loads(body.decode("utf-8"))

            scenes = req.get("scenes", [])
            if not scenes:
                self.send_json({"ok": False, "error": "Danh sách phân cảnh trống"}, 400)
                return

            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            temp_scenes = []

            # 1. Render từng scene đơn lẻ (8 giây mỗi scene)
            render_script = ROOT / "scripts" / "stream_render.py"
            for sc in scenes:
                img_path = ROOT / sc.get("imagePath", "")
                if not img_path.exists():
                    self.send_json({"ok": False, "error": f"Không tìm thấy ảnh: {img_path}"}, 400)
                    return

                scene_out = OUTPUT_DIR / f"temp_{ts}_sc{sc['sceneIndex']}.mp4"
                cmd = [
                    PYTHON_EXEC,
                    str(render_script),
                    str(img_path),
                    "--out-dir", str(OUTPUT_DIR),
                    "--total-ms", str(int(sc.get("durationSec", 8.0) * 1000)),
                    "--fps", "24",
                    "--gaze", "1.2",
                ]
                res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
                
                # Tìm video vừa tạo
                actual_mp4 = None
                for line in res.stdout.splitlines():
                    if line.startswith("OUTPUT="):
                        actual_mp4 = Path(line.split("=", 1)[1].strip())
                        break
                if not actual_mp4 or not actual_mp4.exists():
                    mp4s = sorted(OUTPUT_DIR.glob("stream_*_h264.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
                    if mp4s:
                        actual_mp4 = mp4s[0]

                if actual_mp4 and actual_mp4.exists():
                    actual_mp4.rename(scene_out)
                    temp_scenes.append(scene_out)

            # 2. Ghép tất cả các scene thành video hoàn chỉnh
            if not temp_scenes:
                self.send_json({"ok": False, "error": "Không thể render phân cảnh nào"}, 500)
                return

            final_mp4 = OUTPUT_DIR / f"custom_video_{ts}.mp4"
            merge_script = ROOT / "scripts" / "merge_scenes.py"
            merge_cmd = [
                PYTHON_EXEC,
                str(merge_script),
                *[str(p) for p in temp_scenes],
                "-o", str(final_mp4)
            ]
            res_merge = subprocess.run(merge_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            
            # Xóa các file tạm
            for p in temp_scenes:
                p.unlink(missing_ok=True)

            if not final_mp4.exists():
                self.send_json({"ok": False, "error": "Ghép nối video thất bại"}, 500)
                return

            video_url = "/" + final_mp4.relative_to(ROOT).as_posix()
            self.send_json({"ok": True, "video_url": video_url})
        except Exception as e:
            self.send_json({"ok": False, "error": str(e)}, 500)

    def send_json(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))


def main():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), StudioHandler) as httpd:
        print("=" * 60)
        print(f"🚀 Whiteboard Studio AI Server đang chạy tại:")
        print(f"👉 http://localhost:{PORT}")
        print(f"👉 Mở trình duyệt truy cập: http://localhost:{PORT}")
        print("=" * 60)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nĐang dừng máy chủ...")


if __name__ == "__main__":
    main()
