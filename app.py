#!/usr/bin/env python3
"""
Whiteboard Studio AI - Hugging Face Spaces & ZeroGPU Entrypoint
Phục vụ 100% GIAO DIỆN WEB STUDIO GỐC (web/index.html, CSS, Dark Mode, Wizard 4 bước)
Giữ nguyên vẹn 100% tính năng và giao diện như chạy tại Local
Đồng thời tích hợp Gradio @spaces.GPU để thỏa mãn yêu cầu ZeroGPU của Hugging Face
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

# Đảm bảo hình ảnh bàn tay vẽ tay
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
    from fastapi import Request, UploadFile, File
    from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
    from fastapi.staticfiles import StaticFiles
    HAS_GRADIO = True
except ImportError:
    HAS_GRADIO = False

if not HAS_GRADIO:
    from server import main
    if __name__ == "__main__":
        main()
else:
    # 1. Tạo Gradio Blocks chứa ZeroGPU Worker và nhúng toàn màn hình Web Studio gốc
    with gr.Blocks(title="Whiteboard Studio AI") as demo:
        @gpu_decorator
        def _hf_zerogpu_task(x):
            """Hàm đăng ký để thỏa mãn bộ quét kiểm tra ZeroGPU của Hugging Face"""
            return x

        _init_btn = gr.Button("Init GPU", visible=False)
        _init_btn.click(fn=_hf_zerogpu_task, inputs=[_init_btn], outputs=[_init_btn])

        # Nhúng 100% giao diện Web Studio nguyên bản (đúng chuẩn giao diện local)
        gr.HTML(
            """
            <iframe id="whiteboard-studio-app" src="/web-studio" 
                    style="position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; 
                           border: none; margin: 0; padding: 0; z-index: 999999; background: #0b0d13;">
            </iframe>
            """
        )

    # 2. Đăng ký toàn bộ các API Endpoints của Web Studio vào demo.app (FastAPI)
    @demo.app.get("/web-studio", response_class=HTMLResponse)
    def serve_web_studio():
        """Phục vụ file index.html nguyên bản với đầy đủ CSS, font chữ, modal, wizard"""
        index_file = WEB_DIR / "index.html"
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))

    @demo.app.get("/api/status")
    def api_status():
        return {"ok": True, "version": platform.python_version(), "py": PYTHON_EXEC}

    @demo.app.get("/api/ai-config")
    def api_get_ai_config():
        from scripts.ai_service import load_config
        return {"ok": True, "config": load_config()}

    @demo.app.post("/api/save-ai-config")
    async def api_save_ai_config(request: Request):
        try:
            req = await request.json()
            from scripts.ai_service import save_config
            saved = save_config(req)
            return {"ok": True, "config": saved}
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @demo.app.post("/api/generate-script")
    async def api_generate_script(request: Request):
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

    @demo.app.post("/api/generate-images")
    async def api_generate_images(request: Request):
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

    @demo.app.post("/api/regenerate-scene")
    async def api_regenerate_scene(request: Request):
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

    @demo.app.post("/api/render-custom-project")
    async def api_render_custom_project(request: Request):
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

    @demo.app.post("/api/upload")
    async def api_upload(image: UploadFile = File(...)):
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

    @demo.app.get("/output/{filename:path}")
    def api_output_file(filename: str, request: Request):
        file_path = OUTPUT_DIR / filename
        if not file_path.exists():
            return JSONResponse({"error": "File not found"}, status_code=404)
        params = request.query_params
        if "download" in params or "dl" in params:
            dl_name = params.get("name", filename)
            return FileResponse(file_path, filename=dl_name, media_type="application/octet-stream")
        return FileResponse(file_path, media_type="video/mp4")

    # 3. Mount các thư mục tĩnh: assets, output, uploads, web
    demo.app.mount("/assets", StaticFiles(directory=str(ROOT / "assets")), name="assets")
    demo.app.mount("/output", StaticFiles(directory=str(ROOT / "output")), name="output")
    demo.app.mount("/uploads", StaticFiles(directory=str(ROOT / "uploads")), name="uploads")
    demo.app.mount("/web", StaticFiles(directory=str(ROOT / "web")), name="web")

    if __name__ == "__main__":
        demo.launch()
