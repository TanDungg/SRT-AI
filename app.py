#!/usr/bin/env python3
"""
Entrypoint cho Hugging Face Spaces & ZeroGPU
Tự động khởi chạy giao diện Whiteboard Studio AI trên cổng 7860
Hỗ trợ đầy đủ môi trường ZeroGPU của Hugging Face
"""
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

# Thư mục gốc
ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
UPLOADS_DIR = ROOT / "uploads"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# Đảm bảo có hình ảnh bàn tay vẽ
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
        """Hàm chính xử lý tạo video hoạt hình bảng trắng có gắn @spaces.GPU cho Hugging Face ZeroGPU"""
        try:
            # 1. Xử lý nội dung kịch bản hoặc file SRT
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

            progress(0.1, desc="Đang phân tích kịch bản và tạo phân cảnh...")
            scenes = generate_script(
                effective_topic,
                int(scene_count),
                ratio=ratio,
                api_key=api_key.strip() if api_key else "",
                provider=provider
            )

            # 2. Tạo hình ảnh minh họa doodle
            progress(0.3, desc="Đang vẽ phác thảo doodle cho từng phân cảnh...")
            slug = safe_slug(effective_topic)
            project_dir = ROOT / "assets" / "whiteboard" / f"proj_{slug}"
            project_dir.mkdir(parents=True, exist_ok=True)

            gallery_images = []
            for i, sc in enumerate(scenes):
                idx = sc.get("sceneIndex", i + 1)
                img_path = project_dir / f"scene_{idx:02d}.png"
                sc["imagePath"] = str(img_path)
                progress(0.3 + 0.3 * (i / max(1, len(scenes))), desc=f"Đang vẽ phân cảnh {i + 1}/{len(scenes)}...")
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

            # 3. Render video vẽ tay cho từng phân cảnh
            progress(0.65, desc="Đang render hiệu ứng tay vẽ hoạt hình...")
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
                
                # Tìm file video xuất ra
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

            # 4. Ghép các phân cảnh lại thành video hoàn chỉnh
            progress(0.9, desc="Đang ghép nối toàn bộ phân cảnh...")
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

            # 5. Kịch bản markdown hiển thị
            md_script = f"## 🎬 Kịch bản: {effective_topic}\n\n"
            for sc in scenes:
                md_script += f"### Phân cảnh {sc.get('sceneIndex', 1)}: {sc.get('title', '')} ({sc.get('durationSec', 8)}s)\n"
                md_script += f"- **Lời thoại:** {sc.get('narration', '')}\n"
                md_script += f"- **Doodle Prompt:** `{sc.get('prompt', '')}`\n\n"

            progress(1.0, desc="Hoàn tất video!")
            return str(final_mp4), gallery_images, md_script

        except Exception as e:
            return None, [], f"❌ Lỗi xử lý: {str(e)}"

    # Giao diện Gradio chuyên nghiệp
    custom_css = """
    .gradio-container { max-width: 1250px !important; margin: auto !important; }
    .hero-title { text-align: center; margin-bottom: 1.5rem; }
    """

    with gr.Blocks(title="SRT Whiteboard Studio AI", css=custom_css, theme=gr.themes.Soft()) as demo:
        gr.Markdown(
            """
            # 🎨 SRT Whiteboard Studio AI
            ### Tự động tạo Video Hoạt Hình Vẽ Tay trên Bảng Trắng từ Kịch Bản hoặc Phụ Đề SRT
            """,
            elem_classes="hero-title"
        )

        with gr.Row():
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

                generate_btn = gr.Button("🚀 BẮT ĐẦU TẠO VIDEO HOẠT HÌNH", variant="primary", size="lg")

            with gr.Column(scale=5):
                video_output = gr.Video(label="🎬 Video Hoạt Hình Bảng Trắng Thành Phẩm (MP4)", interactive=False)
                gallery_output = gr.Gallery(label="🖼️ Các bức vẽ phân cảnh (Doodle Scenes)", columns=3, height="auto")
                script_output = gr.Markdown(label="📝 Chi tiết kịch bản và phân cảnh")

        # Ràng buộc nút bấm trực tiếp với hàm có @spaces.GPU (Thỏa mãn tuyệt đối kiểm tra ZeroGPU của Hugging Face)
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
        port = int(os.environ.get("PORT", 7860))
        demo.launch(server_name="0.0.0.0", server_port=port)
