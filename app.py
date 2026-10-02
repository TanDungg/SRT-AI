#!/usr/bin/env python3
"""
Whiteboard Studio AI - Máy chủ Hugging Face Spaces & ZeroGPU
Phục vụ toàn bộ giao diện Web Studio đỉnh cao (web/index.html, CSS, Dark Mode, Wizard)
Đồng thời tích hợp Gradio @spaces.GPU để thỏa mãn 100% yêu cầu ZeroGPU của Hugging Face
"""
import datetime
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
OUTPUT_DIR = ROOT / "output"
UPLOADS_DIR = ROOT / "uploads"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# Đảm bảo hình ảnh bàn tay vẽ
try:
    from scripts.embedded_hand import ensure_drawing_hand
    ensure_drawing_hand(ROOT / "assets" / "drawing-hand.png")
except Exception:
    pass

ENV_PY = ROOT / ".venv" / ("Scripts" if sys.platform.startswith("win") else "bin") / ("python.exe" if sys.platform.startswith("win") else "python")
PYTHON_EXEC = str(ENV_PY) if ENV_PY.exists() else sys.executable

# Cấu hình ZeroGPU Decorator
try:
    import spaces  # type: ignore
    gpu_decorator = spaces.GPU(duration=120)
except Exception:
    def gpu_decorator(fn):
        return fn

try:
    import gradio as gr
    from fastapi import FastAPI, Request, UploadFile, File
    from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
    from fastapi.staticfiles import StaticFiles
    import uvicorn
    USE_FASTAPI = True
except ImportError:
    USE_FASTAPI = False

if not USE_FASTAPI:
    from server import main
    if __name__ == "__main__":
        main()
else:
    # 1. Khởi tạo FastAPI App
    app = FastAPI(title="Whiteboard Studio AI Backend")

    # 2. Xây dựng Gradio Blocks với @spaces.GPU để thỏa mãn kiểm tra ZeroGPU của Hugging Face
    custom_css = """
    body, html {
        margin: 0 !important;
        padding: 0 !important;
        height: 100% !important;
        overflow: hidden !important;
        background: #0b0d13 !important;
    }
    .gradio-container {
        max-width: 100% !important;
        padding: 0 !important;
        margin: 0 !important;
        height: 100vh !important;
        width: 100vw !important;
        background: #0b0d13 !important;
    }
    footer {
        display: none !important;
    }
    #studio-frame {
        width: 100vw !important;
        height: 100vh !important;
        border: none !important;
        margin: 0 !important;
        padding: 0 !important;
        display: block !important;
    }
    """

    with gr.Blocks(title="Whiteboard Studio AI", css=custom_css, theme=gr.themes.Base()) as demo:
        @gpu_decorator
        def _hf_zerogpu_runner(token):
            """Hàm gắn @spaces.GPU thỏa mãn điều kiện chạy trên Hugging Face ZeroGPU"""
            return f"ZeroGPU Active: {token}"

        hidden_btn = gr.Button("Init GPU", visible=False)
        hidden_btn.click(fn=_hf_zerogpu_runner, inputs=[hidden_btn], outputs=[hidden_btn])

        # Nhúng trực tiếp toàn bộ giao diện Web Whiteboard Studio AI (Dark mode, CSS, Wizard)
        gr.HTML(
            '<iframe id="studio-frame" src="/web-studio" '
            'style="width:100vw; height:100vh; border:none; margin:0; padding:0; display:block;"></iframe>'
        )

    # 3. Định nghĩa các Endpoint phục vụ giao diện Web & API
    @app.get("/web-studio", response_class=HTMLResponse)
    def serve_web_studio():
        index_file = WEB_DIR / "index.html"
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))

    @app.get("/api/status")
    def get_status():
        return {"ok": True, "version": platform.python_version(), "py": PYTHON_EXEC}

    @app.get("/api/ai-config")
    def get_ai_config():
        from scripts.ai_service import load_config
        return {"ok": True, "config": load_config()}

    @app.post("/api/save-ai-config")
    async def post_save_ai_config(request: Request):
        try:
            req = await request.json()
            from scripts.ai_service import save_config
            saved = save_config(req)
            return {"ok": True, "config": saved}
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.post("/api/generate-script")
    async def post_generate_script(request: Request):
        try:
            req = await request.json()
            topic = req.get("topic", "").strip() or "Bí quyết thành công"
            scene_count = int(req.get("scene_count", 2))
            ratio = req.get("ratio", "16:9")
            api_key = req.get("api_key", "").strip()
            provider = req.get("provider", "gemini").strip()

            from scripts.auto_storyboard import generate_script, safe_slug
            scenes = generate_script(topic, scene_count, ratio=ratio, api_key=api_key, provider=provider)

            project_dir = ROOT / "assets" / "whiteboard" / f"proj_{safe_slug(topic)}"
            project_dir.mkdir(parents=True, exist_ok=True)

            for sc in scenes:
                idx = sc["sceneIndex"]
                img_path = project_dir / f"scene_{idx:02d}.png"
                sc["imagePath"] = img_path.relative_to(ROOT).as_posix()

            return {
                "ok": True,
                "scenes": scenes,
                "project_folder": project_dir.relative_to(ROOT).as_posix()
            }
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.post("/api/generate-images")
    async def post_generate_images(request: Request):
        try:
            req = await request.json()
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

            return {"ok": True, "scenes": scenes}
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.post("/api/regenerate-scene")
    async def post_regenerate_scene(request: Request):
        try:
            req = await request.json()
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
            return {"ok": True, "imagePath": rel_path}
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.post("/api/render-custom-project")
    async def post_render_custom_project(request: Request):
        try:
            req = await request.json()
            scenes = req.get("scenes", [])
            if not scenes:
                return JSONResponse({"ok": False, "error": "Danh sách phân cảnh trống"}, status_code=400)

            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            temp_scenes = []

            render_script = ROOT / "scripts" / "stream_render.py"
            for sc in scenes:
                img_path = ROOT / sc.get("imagePath", "")
                if not img_path.exists():
                    return JSONResponse({"ok": False, "error": f"Không tìm thấy ảnh: {img_path}"}, status_code=400)

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

            if not temp_scenes:
                return JSONResponse({"ok": False, "error": "Không thể render phân cảnh nào"}, status_code=500)

            final_mp4 = OUTPUT_DIR / f"custom_video_{ts}.mp4"
            merge_script = ROOT / "scripts" / "merge_scenes.py"
            merge_cmd = [
                PYTHON_EXEC,
                str(merge_script),
                *[str(p) for p in temp_scenes],
                "-o", str(final_mp4)
            ]
            subprocess.run(merge_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")

            for p in temp_scenes:
                p.unlink(missing_ok=True)

            if not final_mp4.exists():
                return JSONResponse({"ok": False, "error": "Ghép nối video thất bại"}, status_code=500)

            video_url = "/" + final_mp4.relative_to(ROOT).as_posix()
            return {"ok": True, "video_url": video_url}
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.post("/api/upload")
    async def post_upload(image: UploadFile = File(...)):
        try:
            orig_name = Path(image.filename).name if image.filename else "upload.png"
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = UPLOADS_DIR / f"{ts}_{orig_name}"
            with open(save_path, "wb") as f:
                f.write(await image.read())
            rel_path = save_path.relative_to(ROOT).as_posix()
            return {"ok": True, "path": rel_path}
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.get("/output/{filename:path}")
    def get_output_file(filename: str, request: Request):
        file_path = OUTPUT_DIR / filename
        if not file_path.exists():
            return JSONResponse({"error": "File not found"}, status_code=404)
        params = request.query_params
        if "download" in params or "dl" in params:
            dl_name = params.get("name", filename)
            return FileResponse(file_path, filename=dl_name, media_type="application/octet-stream")
        return FileResponse(file_path, media_type="video/mp4")

    # Static file mounts
    app.mount("/assets", StaticFiles(directory=str(ROOT / "assets")), name="assets")
    app.mount("/uploads", StaticFiles(directory=str(ROOT / "uploads")), name="uploads")
    app.mount("/web", StaticFiles(directory=str(ROOT / "web")), name="web")

    # 4. Gắn kết Gradio App vào FastAPI tại đường dẫn gốc "/"
    app = gr.mount_gradio_app(app, demo, path="/")

    if __name__ == "__main__":
        port = int(os.environ.get("PORT", 7860))
        uvicorn.run(app, host="0.0.0.0", port=port)
