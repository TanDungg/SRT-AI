#!/usr/bin/env python3
"""
AI Service tích hợp Google Gemini và OpenAI API
Tự động 100%:
1. Sinh kịch bản Whiteboard khoa học, hấp dẫn theo bất kỳ chủ đề nào (chuẩn 8s/cảnh).
2. Sinh hình ảnh vẽ Whiteboard Doodle trực quan bằng AI cho từng phân cảnh.
"""
from __future__ import annotations

import os
import sys
import re
import json
import base64
import random
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Optional, Dict, Any, List

ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT / "config.json"

# Danh sách model Gemini ưu tiên (hoạt động tốt nhất)
GEMINI_MODELS = [
    "gemini-3-flash-preview",
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-flash-latest",
    "gemini-pro-latest"
]


def load_config() -> dict:
    """Đọc cấu hình API từ config.json hoặc biến môi trường."""
    cfg = {
        "provider": "gemini",
        "gemini_api_key": os.environ.get("GEMINI_API_KEY", ""),
        "openai_api_key": os.environ.get("OPENAI_API_KEY", ""),
        "gemini_model": "gemini-3-flash-preview",
        "openai_model": "gpt-4o-mini",
        "image_provider": "huggingface",
        "huggingface_token": "",
        "huggingface_model": "black-forest-labs/FLUX.1-schnell",
        "muse_token": "",
        "muse_endpoint": "https://api.muse.ai/v1/generate"
    }
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                cfg.update(saved)
        except Exception:
            pass
    return cfg


def save_config(new_cfg: dict) -> dict:
    """Lưu cấu hình API."""
    cfg = load_config()
    cfg.update(new_cfg)
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Lỗi lưu config: {e}")
    return cfg


def get_resolution_for_ratio(ratio: str) -> tuple[int, int]:
    ratios = {
        "16:9": (1376, 768),
        "9:16": (768, 1376),
        "4:3": (1024, 768),
        "3:4": (768, 1024)
    }
    return ratios.get(ratio, (1376, 768))


# ==========================================
# 1. SINH KỊCH BẢN BẰNG AI (GEMINI / OPENAI)
# ==========================================

def generate_script_with_ai(topic: str, scene_count: int = 2, ratio: str = "16:9", api_key: str = "", provider: str = "gemini") -> Optional[List[Dict[str, Any]]]:
    """Sử dụng Gemini hoặc OpenAI để viết kịch bản chuyên sâu đúng chủ đề."""
    cfg = load_config()
    active_provider = provider or cfg.get("provider", "gemini")
    key = api_key or (cfg.get("gemini_api_key") if active_provider == "gemini" else cfg.get("openai_api_key"))

    if not key:
        return None

    system_instruction = (
        "Bạn là đạo diễn và biên kịch video Whiteboard Animation giáo dục, khoa học đời sống hàng đầu (như MinutePhysics, AsapSCIENCE).\n"
        "Nhiệm vụ: Dựa vào chủ đề người dùng nhập, sáng tạo kịch bản phân cảnh chuẩn xác, sâu sắc và cực kỳ hấp dẫn.\n"
        "Yêu cầu bắt buộc:\n"
        f"1. Tạo đúng {scene_count} phân cảnh (mỗi phân cảnh đúng 8 giây).\n"
        "2. Lời thoại 'subtitle' bằng Tiếng Việt súc tích (khoảng 22 đến 32 từ), đọc vừa vặn trong 8 giây, giải thích bản chất thực sự của sự vật/hiện tượng theo chủ đề.\n"
        "3. Mỗi phân cảnh phải có 'image_prompt' bằng TIẾNG ANH mô tả chi tiết hình vẽ Doodle nét vẽ tay (Whiteboard line art doodle sketch). "
        "Mô tả cụ thể các đối tượng trực quan theo đúng chủ đề (ví dụ nếu chủ đề cà phê thì mô tả: tách cà phê bốc khói, hạt cà phê, phân tử adenosine và caffeine bị chặn lại, não bộ tỉnh táo bừng sáng; không vẽ trừu tượng mơ hồ).\n"
        "4. Trả về đúng định dạng JSON không bọc markdown, schema:\n"
        "{\n"
        '  "scenes": [\n'
        '    {\n'
        '      "sceneIndex": 1,\n'
        '      "title": "Tiêu đề ngắn cảnh 1",\n'
        '      "durationSec": 8.0,\n'
        '      "subtitle": "Lời thuyết minh tiếng Việt chuẩn 8s...",\n'
        '      "visualIdea": "Mô tả ý tưởng hình ảnh ngắn bằng tiếng Việt",\n'
        '      "image_prompt": "Whiteboard doodle sketch of ... detailed elements, clean black marker outline, simple vector cartoon style on cream background"\n'
        '    }\n'
        '  ]\n'
        "}"
    )

    user_prompt = f"Chủ đề video: '{topic}'. Số phân cảnh: {scene_count} cảnh. Tỉ lệ khung hình: {ratio}."

    if active_provider == "gemini":
        for model in GEMINI_MODELS:
            res = _call_gemini_script(key, system_instruction, user_prompt, model)
            if res:
                return res
        return None
    else:
        return _call_openai_script(key, system_instruction, user_prompt, cfg.get("openai_model", "gpt-4o-mini"))


def _call_gemini_script(api_key: str, system_text: str, user_text: str, model: str = "gemini-3-flash-preview") -> Optional[List[Dict[str, Any]]]:
    """Gọi Gemini REST API để sinh kịch bản JSON."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"{system_text}\n\n{user_text}"}]
            }
        ],
        "generationConfig": {
            "temperature": 0.7,
            "responseMimeType": "application/json"
        }
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            candidate = data.get("candidates", [{}])[0]
            content = candidate.get("content", {}).get("parts", [{}])[0].get("text", "")
            parsed = json.loads(content)
            return parsed.get("scenes", [])
    except Exception as e:
        print(f"Gemini {model} lỗi (Script): {e}")
        return None


def _call_openai_script(api_key: str, system_text: str, user_text: str, model: str = "gpt-4o-mini") -> Optional[List[Dict[str, Any]]]:
    """Gọi OpenAI REST API để sinh kịch bản JSON."""
    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text}
        ],
        "temperature": 0.7,
        "response_format": {"type": "json_object"}
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            return parsed.get("scenes", [])
    except Exception as e:
        print(f"Lỗi gọi OpenAI API (Script): {e}")
        return None


# ==========================================
# 2. SINH ẢNH DOODLE BẰNG AI (HUGGING FACE / MUSE / POLLINATIONS / DALL-E)
# ==========================================

def generate_doodle_image_with_ai(image_prompt: str, ratio: str, out_path: Path, api_key: str = "", provider: str = "") -> bool:
    """Tạo ảnh nét vẽ Whiteboard Doodle bằng Hugging Face, MUSE, Pollinations, OpenAI DALL-E hoặc Gemini SVG."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    image_provider = provider or cfg.get("image_provider", "huggingface")
    w, h = get_resolution_for_ratio(ratio)

    # 1. MUSE API (Đã sẵn sàng kết nối nhận Token)
    if image_provider == "muse":
        muse_token = cfg.get("muse_token", "").strip()
        muse_endpoint = cfg.get("muse_endpoint", "https://api.muse.ai/v1/generate").strip()
        if muse_token:
            if _call_muse_image(muse_token, muse_endpoint, image_prompt, w, h, out_path):
                return True
        print("[MUSE] Chưa có token hoặc gọi thất bại, chuyển sang phương thức dự phòng.")

    # 2. HUGGING FACE INFERENCE API
    if image_provider == "huggingface":
        hf_token = cfg.get("huggingface_token", "").strip()
        hf_model = cfg.get("huggingface_model", "black-forest-labs/FLUX.1-schnell").strip()
        if hf_token:
            if _call_huggingface_image(hf_token, image_prompt, w, h, out_path, hf_model):
                return True
        # Nếu chưa nhập HF token hoặc bị lỗi, tự động fallback sang Pollinations miễn phí chất lượng cao
        print("[HuggingFace] Không có token hoặc lỗi, tự động chuyển sang Pollinations miễn phí.")
        if _call_pollinations_image(image_prompt, w, h, out_path):
            return True

    # 3. POLLINATIONS AI (Hoàn toàn miễn phí, không cần key)
    if image_provider == "pollinations":
        if _call_pollinations_image(image_prompt, w, h, out_path):
            return True

    # 4. OPENAI DALL-E 3
    if image_provider == "openai":
        openai_key = cfg.get("openai_api_key", "").strip()
        if openai_key and _call_openai_dalle(openai_key, image_prompt, ratio, out_path):
            return True

    # 5. GEMINI SVG Vector Fallback
    gemini_key = cfg.get("gemini_api_key", "").strip()
    if gemini_key:
        if _generate_gemini_doodle_svg(gemini_key, image_prompt, w, h, out_path):
            return True

    # 6. Fallback cuối cùng sang Pollinations
    return _call_pollinations_image(image_prompt, w, h, out_path)


def _call_huggingface_image(hf_token: str, prompt: str, width: int, height: int, out_path: Path, model: str = "black-forest-labs/FLUX.1-schnell") -> bool:
    """Gọi Hugging Face InferenceClient để sinh ảnh Whiteboard chất lượng cao với FLUX."""
    try:
        from huggingface_hub import InferenceClient
        from PIL import Image, ImageOps
        client = InferenceClient(token=hf_token)

        full_prompt = (
            f"Whiteboard animation doodle sketch of {prompt}. "
            "Minimalist hand-drawn black ink marker outline, clean cartoon line art on solid warm cream paper background #F6F1E3, "
            "high contrast vector sketch, clean contours, no hands, educational illustration"
        )

        raw_img = client.text_to_image(full_prompt, model=model)
        if raw_img:
            canvas = Image.new("RGB", (width, height), "#F6F1E3")
            img_fit = ImageOps.contain(raw_img, (int(width * 0.92), int(height * 0.88)))
            pos = ((width - img_fit.width) // 2, (height - img_fit.height) // 2)
            canvas.paste(img_fit, pos)
            canvas.save(out_path)
            return True
    except Exception as e:
        print(f"[HuggingFace] Error: {e}")
    return False


def _call_muse_image(muse_token: str, endpoint: str, prompt: str, width: int, height: int, out_path: Path) -> bool:
    """Gọi API sinh ảnh MUSE từ token chuẩn bị sẵn."""
    full_prompt = (
        f"Whiteboard doodle animation illustration: {prompt}. "
        "Clean black marker outline, educational cartoon sketch on cream parchment background, simple vector drawing"
    )

    payload = {
        "prompt": full_prompt,
        "width": width,
        "height": height,
        "model": "muse",
        "style": "whiteboard_doodle"
    }

    headers = {
        "Authorization": f"Bearer {muse_token}",
        "Content-Type": "application/json",
        "User-Agent": "WhiteboardStudioAI/1.0"
    }

    req = urllib.request.Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            content_type = resp.headers.get("Content-Type", "")
            data = resp.read()
            # Nếu trả về trực tiếp binary ảnh
            if "image" in content_type:
                with open(out_path, "wb") as f:
                    f.write(data)
                return True
            # Nếu trả về JSON chứa URL hoặc base64
            res_json = json.loads(data.decode("utf-8"))
            if "image_url" in res_json or "url" in res_json:
                img_url = res_json.get("image_url") or res_json.get("url")
                with urllib.request.urlopen(img_url, timeout=30) as r_img:
                    with open(out_path, "wb") as f:
                        f.write(r_img.read())
                    return True
            elif "data" in res_json and len(res_json["data"]) > 0:
                item = res_json["data"][0]
                if "b64_json" in item:
                    with open(out_path, "wb") as f:
                        f.write(base64.b64decode(item["b64_json"]))
                    return True
                elif "url" in item:
                    with urllib.request.urlopen(item["url"], timeout=30) as r_img:
                        with open(out_path, "wb") as f:
                            f.write(r_img.read())
                        return True
    except Exception as e:
        print(f"Lỗi gọi MUSE API: {e}")
    return False


def _call_pollinations_image(prompt: str, width: int, height: int, out_path: Path) -> bool:
    """Gọi Pollinations AI miễn phí 100% để sinh ảnh Whiteboard sắc nét."""
    clean_p = (
        f"Whiteboard animation doodle sketch of {prompt}. "
        "Hand-drawn black ink marker outline, minimalist educational cartoon illustration on clean cream paper background, "
        "clear vector line art, high contrast, clean contours, no hands, no human body"
    )
    encoded = urllib.parse.quote(clean_p)
    seed = random.randint(100, 99999)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&nologo=true&seed={seed}"

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=35) as resp:
            data = resp.read()
            if len(data) > 2000:
                with open(out_path, "wb") as f:
                    f.write(data)
                return True
    except Exception as e:
        print(f"Lỗi Pollinations AI: {e}")
    return False


def _generate_gemini_doodle_svg(api_key: str, image_prompt: str, width: int, height: int, out_path: Path) -> bool:
    """Yêu cầu Gemini tạo mã vector SVG Whiteboard Doodle chân thực và render thành PNG."""
    prompt = (
        f"You are a master Whiteboard Animation illustrator. Create a full, valid SVG vector illustration representing: '{image_prompt}'.\n"
        "Requirements:\n"
        f"- Output ONLY the raw <svg viewBox='0 0 {width} {height}' xmlns='http://www.w3.org/2000/svg'>...</svg> tag, without any markdown backticks or explanations.\n"
        f"- Canvas background: <rect width='{width}' height='{height}' fill='#F6F1E3'/>.\n"
        "- Art style: Hand-drawn whiteboard cartoon doodle sketch. Clear black marker outlines (stroke='#1E293B', stroke-width='5' or '6', fill='none', stroke-linecap='round', stroke-linejoin='round').\n"
        "- Use subtle marker fills/accents: warm orange #EA580C, marker yellow #FBBF24, soft blue #3B82F6, soft green #10B981, or white #FFFFFF fills inside shapes.\n"
        "- Draw clear, recognizable objects matching the prompt: characters, cups, brains, icons, arrows, molecules, steam, sparkles, badges.\n"
        f"- Add a hand-drawn sketch border rect around the margin: <rect x='30' y='30' width='{width-60}' height='{height-60}' fill='none' stroke='#1E293B' stroke-width='4' rx='10'/>.\n"
        "- Ensure SVG syntax is 100% valid."
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.4}
    }

    raw_svg = None
    for model in GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=35) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                if "<svg" in text and "</svg>" in text:
                    raw_svg = text
                    break
        except Exception as e:
            print(f"Gemini {model} lỗi sinh SVG: {e}")

    if not raw_svg:
        return False

    start = raw_svg.find("<svg")
    end = raw_svg.rfind("</svg>") + 6
    clean_svg = raw_svg[start:end]
    return _render_svg_to_png(clean_svg, width, height, out_path)


def _render_svg_to_png(svg_content: str, width: int, height: int, out_path: Path) -> bool:
    """Render mã SVG thành file PNG độ phân giải chuẩn bằng headless browser."""
    temp_html = out_path.parent / f"temp_{out_path.stem}.html"
    try:
        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin:0; padding:0; box-sizing: border-box; }}
  body {{ background: #F6F1E3; width: {width}px; height: {height}px; overflow: hidden; }}
  svg {{ width: {width}px; height: {height}px; display: block; }}
</style>
</head>
<body>{svg_content}</body>
</html>"""
        temp_html.write_text(html, encoding="utf-8")

        # Tìm trình duyệt Edge hoặc Chrome
        browsers = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
        ]
        exe = next((b for b in browsers if Path(b).exists()), None)
        if not exe:
            return False

        abs_out = out_path.resolve()
        cmd = [
            exe,
            "--headless",
            "--disable-gpu",
            f"--window-size={width},{height}",
            f"--screenshot={abs_out}",
            temp_html.resolve().as_uri()
        ]
        subprocess.run(cmd, capture_output=True, timeout=15)
        return out_path.exists() and out_path.stat().st_size > 1000
    except Exception as e:
        print(f"Lỗi render SVG to PNG: {e}")
        return False
    finally:
        temp_html.unlink(missing_ok=True)


def _call_openai_dalle(api_key: str, prompt: str, ratio: str, out_path: Path) -> bool:
    """Gọi OpenAI DALL-E 3 API."""
    url = "https://api.openai.com/v1/images/generations"

    if ratio == "9:16":
        size = "1024x1792"
    elif ratio == "16:9":
        size = "1792x1024"
    else:
        size = "1024x1024"

    full_prompt = (
        f"A clean educational whiteboard animation illustration: {prompt}. "
        "Hand-drawn black ink marker outline doodle sketch, simple vector line art with subtle marker accent colors. "
        "Solid cream paper parchment background (#F6F1E3), clean contours, no photorealism, no 3D rendering."
    )

    payload = {
        "model": "dall-e-3",
        "prompt": full_prompt[:1000],
        "n": 1,
        "size": size,
        "response_format": "b64_json"
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            item = data.get("data", [{}])[0]
            if "b64_json" in item:
                raw_b64 = item["b64_json"]
                img_data = base64.b64decode(raw_b64)
                with open(out_path, "wb") as f:
                    f.write(img_data)
                return True
    except Exception as e:
        print(f"Lỗi gọi OpenAI DALL-E: {e}")
    return False
