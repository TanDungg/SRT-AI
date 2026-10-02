#!/usr/bin/env python3
"""
Whiteboard Studio AI - Giao diện Hugging Face Spaces & ZeroGPU
Giao diện Dark Mode Glassmorphism cao cấp đồng bộ với Web Studio
Hỗ trợ đầy đủ môi trường ZeroGPU của Hugging Face
"""
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
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
    HAS_GRADIO = True
except ImportError:
    HAS_GRADIO = False

if not HAS_GRADIO:
    from server import main
    if __name__ == "__main__":
        main()
else:
    from scripts.auto_storyboard import generate_script, safe_slug, draw_doodle_scene

    @gpu_decorator
    def generate_whiteboard_animation(
        topic: str,
        srt_file,
        scene_count: int,
        ratio: str,
        provider: str,
        api_key: str,
        progress=gr.Progress(track_tqdm=True)
    ):
        """Hàm chính xử lý tạo video hoạt hình bảng trắng có gắn @spaces.GPU cho ZeroGPU"""
        try:
            input_text = ""
            if srt_file is not None:
                srt_path = getattr(srt_file, "name", str(srt_file))
                try:
                    with open(srt_path, "r", encoding="utf-8", errors="replace") as f:
                        input_text = f.read()
                except Exception:
                    input_text = ""

            effective_topic = topic.strip()
            if not effective_topic and input_text:
                effective_topic = "Nội dung theo phụ đề SRT"
            elif not effective_topic:
                effective_topic = "5 thói quen giúp bạn làm việc hiệu quả"

            progress(0.1, desc="⚡ Đang phân tích kịch bản và chia phân cảnh...")
            scenes = generate_script(
                effective_topic,
                int(scene_count),
                ratio=ratio,
                api_key=api_key.strip() if api_key else "",
                provider=provider
            )

            progress(0.3, desc="🎨 Đang phác thảo tranh vẽ doodle bảng trắng...")
            slug = safe_slug(effective_topic)
            project_dir = ROOT / "assets" / "whiteboard" / f"proj_{slug}"
            project_dir.mkdir(parents=True, exist_ok=True)

            gallery_images = []
            for i, sc in enumerate(scenes):
                idx = sc.get("sceneIndex", i + 1)
                img_path = project_dir / f"scene_{idx:02d}.png"
                sc["imagePath"] = str(img_path)
                progress(0.3 + 0.3 * (i / max(1, len(scenes))), desc=f"🎨 Đang vẽ phân cảnh {i + 1}/{len(scenes)}...")
                draw_doodle_scene(
                    sc,
                    ratio,
                    img_path,
                    api_key=api_key.strip() if api_key else "",
                    provider=provider,
                    image_provider=provider
                )
                if img_path.exists():
                    gallery_images.append(str(img_path))

            progress(0.65, desc="✍️ Đang render hiệu ứng bàn tay lướt vẽ...")
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            render_script = ROOT / "scripts" / "stream_render.py"
            temp_scenes = []

            for i, sc in enumerate(scenes):
                img_p = Path(sc["imagePath"])
                if not img_p.exists():
                    continue
                scene_out = OUTPUT_DIR / f"temp_{ts}_sc{sc.get('sceneIndex', i+1)}.mp4"
                cmd = [
                    PYTHON_EXEC,
                    str(render_script),
                    str(img_p),
                    "--out-dir", str(OUTPUT_DIR),
                    "--total-ms", str(int(sc.get("durationSec", 8.0) * 1000)),
                    "--fps", "24",
                    "--gaze", "1.2",
                ]
                res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
                
                out_video = None
                for line in res.stdout.splitlines():
                    if line.startswith("OUTPUT="):
                        out_video = Path(line.split("=", 1)[1].strip())
                        break
                if not out_video or not out_video.exists():
                    mp4s = sorted(OUTPUT_DIR.glob("stream_*_h264.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
                    if mp4s:
                        out_video = mp4s[0]

                if out_video and out_video.exists():
                    out_video.rename(scene_out)
                    temp_scenes.append(scene_out)

            if not temp_scenes:
                return None, gallery_images, "⚠️ Không thể render phân cảnh nào."

            progress(0.9, desc="🎬 Đang ghép nối toàn bộ video hoạt hình MP4...")
            final_mp4 = OUTPUT_DIR / f"whiteboard_{ts}.mp4"
            merge_script = ROOT / "scripts" / "merge_scenes.py"
            cmd = [
                PYTHON_EXEC,
                str(merge_script),
                *[str(p) for p in temp_scenes],
                "-o", str(final_mp4)
            ]
            subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            for p in temp_scenes:
                p.unlink(missing_ok=True)

            md_script = f"## 🎬 Kịch Bản Hoàn Chỉnh: {effective_topic}\n\n"
            for sc in scenes:
                md_script += f"### 📍 Phân cảnh {sc.get('sceneIndex', 1)}: {sc.get('title', '')} ({sc.get('durationSec', 8)}s)\n"
                md_script += f"- **Lời thoại:** {sc.get('narration', '')}\n"
                md_script += f"- **Doodle Prompt:** `{sc.get('prompt', '')}`\n\n"

            progress(1.0, desc="✅ Xuất video thành công!")
            return str(final_mp4), gallery_images, md_script

        except Exception as e:
            return None, [], f"❌ Lỗi xử lý: {str(e)}"

    # Giao diện Glassmorphism với bộ CSS được tối ưu toàn diện
    THEME_HTML = """
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
      :root {
        --bg-main: #0b0d13;
        --card-bg: rgba(20, 24, 34, 0.85);
        --card-border: rgba(255, 255, 255, 0.08);
        --primary-blue: #3b82f6;
        --primary-hover: #2563eb;
        --accent-purple: #8b5cf6;
      }
      body, .gradio-container {
        font-family: 'Outfit', -apple-system, BlinkMacSystemFont, sans-serif !important;
        background-color: var(--bg-main) !important;
        background-image: 
          radial-gradient(circle at 10% 15%, rgba(59, 130, 246, 0.12) 0%, transparent 45%),
          radial-gradient(circle at 90% 85%, rgba(139, 92, 246, 0.12) 0%, transparent 45%) !important;
        color: #f8fafc !important;
        max-width: 1300px !important;
        margin: auto !important;
      }
      .block, .panel, .gr-box, .gr-panel, .form, .gr-form {
        background: var(--card-bg) !important;
        border: 1px solid var(--card-border) !important;
        border-radius: 14px !important;
        backdrop-filter: blur(12px) !important;
        box-shadow: 0 8px 30px rgba(0, 0, 0, 0.4) !important;
      }
      input, textarea, select {
        background: rgba(15, 18, 26, 0.95) !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
        color: #f8fafc !important;
        border-radius: 10px !important;
        font-size: 14px !important;
      }
      input:focus, textarea:focus {
        border-color: var(--primary-blue) !important;
        box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.3) !important;
      }
      label {
        color: #94a3b8 !important;
        font-weight: 500 !important;
        font-size: 13px !important;
        margin-bottom: 4px !important;
      }
      .custom-header {
        background: rgba(15, 18, 26, 0.85);
        border: 1px solid var(--card-border);
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 24px;
        text-align: center;
        backdrop-filter: blur(16px);
      }
      .badge-glow {
        display: inline-block;
        background: rgba(59, 130, 246, 0.15);
        border: 1px solid rgba(59, 130, 246, 0.35);
        color: #60a5fa;
        padding: 4px 14px;
        border-radius: 999px;
        font-size: 12px;
        font-weight: 600;
        margin-bottom: 10px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
      }
      .header-title {
        font-size: 28px;
        font-weight: 700;
        background: linear-gradient(135deg, #ffffff 0%, #cbd5e1 50%, #93c5fd 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 8px;
      }
      .header-desc {
        color: #94a3b8;
        font-size: 15px;
      }
      .btn-generate {
        background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%) !important;
        color: #ffffff !important;
        font-weight: 600 !important;
        font-size: 16px !important;
        border: 1px solid rgba(255, 255, 255, 0.25) !important;
        border-radius: 12px !important;
        box-shadow: 0 4px 20px rgba(59, 130, 246, 0.45) !important;
        padding: 14px 20px !important;
        transition: all 0.25s ease !important;
        cursor: pointer !important;
      }
      .btn-generate:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 8px 25px rgba(59, 130, 246, 0.7) !important;
      }
      .steps-row {
        display: flex;
        justify-content: center;
        gap: 16px;
        margin-top: 14px;
        flex-wrap: wrap;
      }
      .step-item {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 8px;
        padding: 6px 12px;
        font-size: 12px;
        color: #cbd5e1;
      }
      footer {
        display: none !important;
      }
    </style>
    """

    with gr.Blocks(title="Whiteboard Studio AI") as demo:
        # Nhúng trực tiếp toàn bộ CSS & Font Google vào đầu ứng dụng
        gr.HTML(THEME_HTML)

        # Header phong cách Whiteboard Studio AI
        gr.HTML(
            """
            <div class="custom-header">
              <span class="badge-glow">✨ AI Whiteboard Studio v2.0</span>
              <h1 class="header-title">🎨 SRT Whiteboard Studio AI</h1>
              <p class="header-desc">Hệ thống tạo Video Hoạt Hình Vẽ Tay trên Bảng Trắng tự động từ Kịch Bản hoặc Phụ Đề SRT</p>
              <div class="steps-row">
                <span class="step-item"><b>1.</b> Nhập chủ đề / SRT</span>
                <span class="step-item">➔ <b>2.</b> AI phân tích kịch bản</span>
                <span class="step-item">➔ <b>3.</b> Phác thảo nét vẽ doodle</span>
                <span class="step-item">➔ <b>4.</b> Render MP4 vẽ tay</span>
              </div>
            </div>
            """
        )

        with gr.Row():
            # Cột trái: Cấu hình và nhập kịch bản
            with gr.Column(scale=4):
                with gr.Tab("💡 Nhập Kịch Bản / Chủ Đề"):
                    topic_input = gr.Textbox(
                        label="Chủ đề hoặc nội dung cần làm video",
                        placeholder="Ví dụ: 5 bí quyết quản lý tài chính cá nhân, Tại sao chúng ta trì hoãn...",
                        lines=3,
                        value="5 bí quyết giúp làm việc tập trung và hiệu quả hơn"
                    )

                with gr.Tab("📄 Tải Lên Phụ Đề SRT"):
                    srt_input = gr.File(label="File phụ đề (.srt)", file_types=[".srt"])

                with gr.Row():
                    scene_slider = gr.Slider(minimum=2, maximum=6, value=3, step=1, label="Số phân cảnh (Scenes)")
                    ratio_radio = gr.Radio(choices=["16:9", "9:16"], value="16:9", label="Tỷ lệ khung hình")

                provider_dropdown = gr.Dropdown(
                    choices=["huggingface", "muse", "gemini"],
                    value="huggingface",
                    label="Nhà cung cấp AI tạo ảnh (Image AI Provider)"
                )

                api_key_input = gr.Textbox(
                    label="API Key / Token (HF Token hoặc MUSE Token)",
                    placeholder="Nhập hf_... hoặc để trống nếu dùng mặc định",
                    type="password"
                )

                generate_btn = gr.Button("🚀 BẮT ĐẦU TẠO VIDEO HOẠT HÌNH", elem_classes=["btn-generate"], size="lg")

            # Cột phải: Xem thành phẩm Video & Tranh vẽ
            with gr.Column(scale=5):
                video_output = gr.Video(label="🎬 Video Hoạt Hình Bảng Trắng Hoàn Chỉnh (MP4)", interactive=False)
                gallery_output = gr.Gallery(label="🖼️ Các bức vẽ phân cảnh (Doodle Scenes)", columns=3, height="auto")
                script_output = gr.Markdown(label="📝 Chi tiết kịch bản và phân cảnh")

        # Ràng buộc nút bấm trực tiếp với hàm có @spaces.GPU (Thỏa mãn ZeroGPU)
        generate_btn.click(
            fn=generate_whiteboard_animation,
            inputs=[
                topic_input,
                srt_input,
                scene_slider,
                ratio_radio,
                provider_dropdown,
                api_key_input
            ],
            outputs=[
                video_output,
                gallery_output,
                script_output
            ]
        )

    if __name__ == "__main__":
        demo.launch()
