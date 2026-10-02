#!/usr/bin/env python3
"""
Tự động sinh kịch bản và vẽ tranh Whiteboard Doodle cho mọi chủ đề.
Không sử dụng khung có sẵn cố định, phân tích động theo chủ đề người dùng.
"""
from __future__ import annotations

import sys
import re
import math
import unicodedata
import datetime
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Đảm bảo in UTF-8 không lỗi trên Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    from scripts.ai_service import generate_script_with_ai, generate_doodle_image_with_ai, load_config
except ImportError:
    from ai_service import generate_script_with_ai, generate_doodle_image_with_ai, load_config

# Màu nền canvas chuẩn phong cách Whiteboard
CANVAS_COLOR = (246, 241, 227)       # #F6F1E3 (Kem giấy nhám)
COLOR_INK = (30, 41, 59)             # Mực bút dạ đen / slate
COLOR_ACCENT_BLUE = (37, 99, 235)    # Xanh dương điểm nhấn
COLOR_ACCENT_ORANGE = (234, 88, 12)  # Cam năng lượng
COLOR_ACCENT_GREEN = (16, 185, 129)  # Xanh lục thành quả
COLOR_MUTED = (148, 163, 184)        # Xám nhạt viền


def safe_slug(text: str) -> str:
    """Tạo slug an toàn chỉ gồm ký tự ASCII a-z 0-9 để không bao giờ lỗi đường dẫn trên Windows/Web."""
    norm = unicodedata.normalize('NFKD', text)
    ascii_text = norm.encode('ascii', 'ignore').decode('ascii')
    clean = re.sub(r'[^a-zA-Z0-9]+', '_', ascii_text).strip('_').lower()
    ts = datetime.datetime.now().strftime("%m%d_%H%M%S")
    return f"{clean[:20] or 'topic'}_{ts}"


def get_font(size: int = 24, bold: bool = False):
    """Tìm font tiếng Việt hệ thống Windows để vẽ chữ đẹp."""
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/calibrib.ttf" if bold else "C:/Windows/Fonts/calibri.ttf",
        "C:/Windows/Fonts/tahoma.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def analyze_topic_structure(topic: str) -> dict:
    """Phân tích cấu trúc ngữ nghĩa của chủ đề để tùy biến câu chuyện."""
    t = topic.strip()
    t_lower = t.lower()

    category = "general"
    if any(k in t_lower for k in ["tại sao", "vì sao", "nguyên nhân", "lý do"]):
        category = "why"
    elif any(k in t_lower for k in ["cách", "làm sao", "làm thế nào", "hướng dẫn", "bước"]):
        category = "howto"
    elif any(k in t_lower for k in ["lợi ích", "tác dụng", "giá trị", "sức mạnh"]):
        category = "benefit"
    elif any(k in t_lower for k in ["bí quyết", "quy tắc", "phương pháp", "chiến lược", "nguyên lý"]):
        category = "secret"
    elif any(k in t_lower for k in ["thói quen", "kỷ luật", "tập trung", "năng suất", "thời gian"]):
        category = "productivity"

    # Trích xuất từ khóa chính (bỏ các từ nối thông dụng)
    clean_words = re.sub(r'(?i)\b(tại sao|vì sao|làm sao|cách|bí quyết|quy tắc|lợi ích của việc|những|trong|cho|và|với|của)\b', '', t).strip()
    core_keyword = clean_words or t

    return {
        "raw": t,
        "category": category,
        "core_keyword": core_keyword
    }


def generate_script(topic: str, scene_count: int = 2, ratio: str = "16:9", api_key: str = "", provider: str = "") -> list[dict]:
    """Tự động sinh kịch bản chân thực, hấp dẫn cho bất kỳ chủ đề nào (AI hoặc Phân tích động)."""
    # 1. Thử gọi AI (Gemini hoặc OpenAI) nếu có API Key
    try:
        ai_scenes = generate_script_with_ai(topic, scene_count=scene_count, ratio=ratio, api_key=api_key, provider=provider)
        if ai_scenes and len(ai_scenes) >= scene_count:
            for idx, sc in enumerate(ai_scenes[:scene_count]):
                sc["sceneIndex"] = idx + 1
                sc["durationSec"] = 8.0
                sc["stepTag"] = f"BƯỚC {idx + 1}: {sc.get('title', '').split(':')[-1].strip().upper() or 'PHÂN CẢNH'}"
                sc["topicKeyword"] = topic[:20]
                if "image_prompt" not in sc:
                    sc["image_prompt"] = f"Whiteboard doodle sketch of {topic}, clean black marker line art on cream paper #F6F1E3"
            return ai_scenes[:scene_count]
    except Exception as e:
        print(f"Lỗi sinh kịch bản AI, chuyển về fallback: {e}")

    # 2. Fallback phân tích ngữ nghĩa
    analysis = analyze_topic_structure(topic)
    raw = analysis["raw"]
    core = analysis["core_keyword"]
    cat = analysis["category"]

    scenes = []

    # Cảnh 1: Mở đầu - Nêu vấn đề / Đặt câu hỏi kích thích tò mò
    if cat == "why":
        sub1 = f"Bạn đã bao giờ tự hỏi vì sao {core} lại tạo ra sự khác biệt to lớn đến thế trong cuộc sống của chúng ta?"
        vis1 = f"Não bộ suy tư cùng dấu hỏi lớn và các mối liên kết xung quanh {core}"
        layout1 = "mindmap_question"
        prompt1 = f"Whiteboard doodle sketch of human brain with thoughts and question marks thinking about {core}, clean black ink marker on cream paper #F6F1E3"
    elif cat == "howto":
        sub1 = f"Làm thế nào để bắt đầu với {core} một cách hiệu quả nhất mà không bị quá tải hay nản lòng?"
        vis1 = f"Người đứng trước ngã rẽ và chiếc la bàn định hướng tới mục tiêu {core}"
        layout1 = "compass_path"
        prompt1 = f"Whiteboard doodle sketch of a directional compass and path towards goal {core}, clean marker line art on cream paper #F6F1E3"
    elif cat == "benefit":
        sub1 = f"Khám phá những giá trị đáng kinh ngạc từ {core} mà có thể trước giờ bạn chưa từng nhận ra."
        vis1 = f"Hộp quà tri thức mở ra những biểu tượng giá trị sáng chói về {core}"
        layout1 = "gift_spark"
        prompt1 = f"Whiteboard doodle sketch of treasure chest of ideas opening with glowing symbols of {core}, clean ink on cream paper #F6F1E3"
    elif cat == "secret":
        sub1 = f"Đằng sau sự hiệu quả của {core} là một nguyên lý đơn giản nhưng ít người kiên trì áp dụng mỗi ngày."
        vis1 = f"Chiếc chìa khóa vạn năng mở khóa ổ khóa tư duy về {core}"
        layout1 = "key_unlock"
        prompt1 = f"Whiteboard doodle sketch of master key unlocking a brain padlock for {core}, clean marker line art on cream paper #F6F1E3"
    else:
        sub1 = f"Khám phá góc nhìn hoàn toàn mới về {raw} để tối ưu hóa hiệu suất và nâng tầm cuộc sống của bạn."
        vis1 = f"Bóng đèn ý tưởng bừng sáng giữa các bánh răng tư duy về {core}"
        layout1 = "lightbulb_gears"
        prompt1 = f"Whiteboard doodle sketch of bright lightbulb glowing amidst thought gears and ideas about {core}, clean black line art on cream paper #F6F1E3"

    scenes.append({
        "sceneIndex": 1,
        "title": f"Cảnh 1: Bí mật về {core[:28]}",
        "durationSec": 8.0,
        "subtitle": sub1,
        "visualIdea": vis1,
        "image_prompt": prompt1,
        "layout": layout1,
        "topicKeyword": core[:24],
        "stepTag": "BƯỚC 1: KHỞI ĐỘNG"
    })

    # Cảnh 2: Cơ chế - Giải pháp then chốt
    if cat == "why":
        sub2 = f"Cốt lõi nằm ở cách não bộ và thói quen phản ứng: khi thấu hiểu cơ chế này, bạn sẽ làm chủ hoàn toàn {core}!"
        vis2 = f"Cơ chế đòn bẩy và sơ đồ dòng chảy năng lượng giúp bứt phá cùng {core}"
        layout2 = "mechanism_flow"
        prompt2 = f"Whiteboard doodle sketch of leverage mechanism and energy flow for {core}, clean black ink doodle on cream background #F6F1E3"
    elif cat == "howto":
        sub2 = f"Hãy chia nhỏ thành từng bước hành động cụ thể, bắt đầu từ điều dễ nhất để xây dựng đà quán tính vững chắc."
        vis2 = f"Quy trình 3 bước hình mũi tên tiến lên và dấu tích hoàn thành từng mốc"
        layout2 = "steps_arrow"
        prompt2 = f"Whiteboard doodle sketch of 3-step action roadmap with checkmarks and forward arrows, clean ink on cream paper #F6F1E3"
    elif cat == "benefit":
        sub2 = f"Khi duy trì đều đặn, tác động kép sẽ kích hoạt, mang lại nguồn năng lượng tích cực và sự tập trung cao độ."
        vis2 = f"Biểu đồ tăng trưởng dốc đứng và ngọn lửa năng lượng nhiệt huyết"
        layout2 = "growth_chart"
        prompt2 = f"Whiteboard doodle sketch of growth bar chart with rising arrow and energy spark, clean line art on cream paper #F6F1E3"
    elif cat == "secret":
        sub2 = f"Tập trung trọn vẹn vào điểm mấu chốt quan trọng nhất, loại bỏ mọi yếu tố gây xao nhãng để tối đa hóa kết quả."
        vis2 = f"Tâm điểm bia ngắm với mũi tên bắn trúng hồng tâm mục tiêu {core}"
        layout2 = "target_bullseye"
        prompt2 = f"Whiteboard doodle sketch of archery target bullseye with arrow hitting center of {core}, clean marker drawing on cream paper #F6F1E3"
    else:
        sub2 = f"Chìa khóa quyết định là sự kiên định: mỗi nỗ lực nhỏ tích lũy hôm nay sẽ tạo nên bước nhảy vọt ngày mai."
        vis2 = f"Bậc thang thăng tiến từng bước vững vàng chạm tới đỉnh thành công"
        layout2 = "stairs_success"
        prompt2 = f"Whiteboard doodle sketch of staircase ascending to success with flag on top, clean ink on cream paper #F6F1E3"

    scenes.append({
        "sceneIndex": 2,
        "title": f"Cảnh 2: Điểm cốt lõi & Hành động",
        "durationSec": 8.0,
        "subtitle": sub2,
        "visualIdea": vis2,
        "image_prompt": prompt2,
        "layout": layout2,
        "topicKeyword": "HÀNH ĐỘNG CỐT LÕI",
        "stepTag": "BƯỚC 2: THỰC THI"
    })

    # Cảnh 3 (nếu chọn 3 cảnh): Kết luận & Kêu gọi hành động
    if scene_count >= 3:
        scenes.append({
            "sceneIndex": 3,
            "title": f"Cảnh 3: Chinh phục thành quả",
            "durationSec": 8.0,
            "subtitle": f"Đừng chần chừ nữa! Hãy bắt tay vào thực hiện ngay hôm nay để đón nhận những thay đổi tuyệt vời nhất!",
            "visualIdea": f"Tên lửa phóng lên bầu trời và cúp vô địch chiến thắng rạng rỡ",
            "image_prompt": f"Whiteboard doodle sketch of space rocket blasting off into sky with sparkling stars and winner trophy, clean black ink on cream paper #F6F1E3",
            "layout": "rocket_trophy",
            "topicKeyword": "BỨT PHÁ NGAY",
            "stepTag": "BƯỚC 3: THÀNH CÔNG"
        })

    return scenes


def get_resolution_for_ratio(ratio: str) -> tuple[int, int]:
    ratios = {
        "16:9": (1376, 768),
        "9:16": (768, 1376),
        "4:3": (1024, 768),
        "3:4": (768, 1024)
    }
    return ratios.get(ratio, (1376, 768))


def draw_doodle_scene(scene: dict, ratio: str, out_path: Path, api_key: str = "", provider: str = "", image_provider: str = "") -> Path:
    """Tự động tạo tranh vẽ Whiteboard bằng AI (Hugging Face / MUSE / Pollinations / DALL-E / Gemini), fallback doodle canvas."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cfg = load_config()

    if not api_key:
        active_provider = provider or cfg.get("provider", "gemini")
        api_key = cfg.get("gemini_api_key") if active_provider == "gemini" else cfg.get("openai_api_key")

    img_provider = image_provider or cfg.get("image_provider", "huggingface")

    # 1. Thử sinh ảnh bằng AI
    img_prompt = scene.get("image_prompt")
    if img_prompt:
        try:
            ok = generate_doodle_image_with_ai(img_prompt, ratio, out_path, api_key=api_key, provider=img_provider)
            if ok and out_path.exists():
                return out_path
        except Exception as e:
            print(f"Không thể sinh ảnh bằng AI: {e}")

    # 2. Fallback vẽ đồ họa Whiteboard Doodle chất lượng cao
    w, h = get_resolution_for_ratio(ratio)

    img = Image.new("RGB", (w, h), CANVAS_COLOR)
    draw = ImageDraw.Draw(img)

    # Thêm vân giấy nhám tự nhiên (doodle whiteboard parchment)
    np_img = np.array(img, dtype=np.int16)
    noise = np.random.normal(0, 3.5, np_img.shape).astype(np.int16)
    np_img = np.clip(np_img + noise, 0, 255).astype(np.uint8)
    img = Image.fromarray(np_img)
    draw = ImageDraw.Draw(img)

    # Viền phác thảo tay bao quanh khung tranh
    pad = int(min(w, h) * 0.035)
    draw.rectangle([pad, pad, w - pad, h - pad], outline=COLOR_INK, width=4)
    draw.rectangle([pad + 5, pad + 5, w - pad - 5, h - pad - 5], outline=COLOR_MUTED, width=1)

    # Khởi tạo fonts
    font_badge = get_font(int(min(w, h) * 0.028), bold=True)
    font_title = get_font(int(min(w, h) * 0.045), bold=True)
    font_sub = get_font(int(min(w, h) * 0.030), bold=False)
    font_icon = get_font(int(min(w, h) * 0.035), bold=True)

    # Header Badge (Thẻ phân cảnh dạng vẽ tay)
    step_tag = scene.get("stepTag", f"PHÂN CẢNH {scene.get('sceneIndex', 1)}")
    badge_w = int(min(w, h) * 0.32)
    badge_h = int(min(w, h) * 0.065)
    bx0 = pad + 20
    by0 = pad + 15
    draw.rounded_rectangle([bx0, by0, bx0 + badge_w, by0 + badge_h], radius=8, fill=COLOR_INK)
    draw.text((bx0 + 16, by0 + 8), step_tag, fill=(255, 255, 255), font=font_badge)

    # Tiêu đề phân cảnh phía trên
    title_text = scene.get("title", "")
    draw.text((bx0, by0 + badge_h + 12), title_text, fill=COLOR_INK, font=font_title)

    # Khu vực vẽ Doodle trọng tâm ở trung tâm bức tranh
    cx = w // 2
    cy = int(h * 0.52)
    layout = scene.get("layout", "lightbulb_gears")
    keyword = scene.get("topicKeyword", "Ý TƯỞNG")

    # 1. Vẽ các biểu tượng minh họa doodle tương ứng layout
    if "question" in layout or "mindmap" in layout:
        # Doodle dấu hỏi lớn & mạng lưới tư duy
        r_head = int(min(w, h) * 0.18)
        draw.arc([cx - r_head, cy - r_head - 30, cx + r_head, cy + r_head - 30], start=180, end=360, fill=COLOR_ACCENT_BLUE, width=8)
        draw.line([cx + r_head, cy - 30, cx, cy + 40], fill=COLOR_ACCENT_BLUE, width=8)
        draw.line([cx, cy + 40, cx, cy + 70], fill=COLOR_ACCENT_BLUE, width=8)
        draw.ellipse([cx - 10, cy + 95, cx + 10, cy + 115], fill=COLOR_ACCENT_ORANGE)

        # Các vệ tinh ý tưởng tỏa ra
        for angle in [30, 75, 120, 210, 260, 310]:
            rad = math.radians(angle)
            dist = int(min(w, h) * 0.28)
            sx = int(cx + dist * math.cos(rad))
            sy = int(cy + dist * math.sin(rad) * 0.7)
            draw.line([cx, cy, sx, sy], fill=COLOR_MUTED, width=2)
            draw.ellipse([sx - 18, sy - 18, sx + 18, sy + 18], outline=COLOR_INK, fill=(255, 255, 255), width=3)
            draw.text((sx - 10, sy - 10), "★", fill=COLOR_ACCENT_ORANGE, font=font_icon)

    elif "target" in layout or "bullseye" in layout:
        # Doodle bia ngắm và mũi tên trúng hồng tâm
        r3 = int(min(w, h) * 0.22)
        r2 = int(min(w, h) * 0.15)
        r1 = int(min(w, h) * 0.08)
        draw.ellipse([cx - r3, cy - r3, cx + r3, cy + r3], outline=COLOR_INK, width=6)
        draw.ellipse([cx - r2, cy - r2, cx + r2, cy + r2], outline=COLOR_ACCENT_BLUE, width=5)
        draw.ellipse([cx - r1, cy - r1, cx + r1, cy + r1], outline=COLOR_INK, fill=COLOR_ACCENT_ORANGE, width=4)

        # Mũi tên cắm thẳng vào tâm
        draw.line([cx - int(r3 * 1.4), cy + int(r3 * 0.8), cx, cy], fill=COLOR_INK, width=8)
        draw.polygon([(cx, cy), (cx - 20, cy - 10), (cx - 10, cy + 20)], fill=COLOR_INK)

    elif "growth" in layout or "steps" in layout or "stairs" in layout:
        # Doodle biểu đồ tăng trưởng bứt phá & các bậc thang
        bw = int(w * 0.6)
        bh = int(h * 0.28)
        x0 = cx - bw // 2
        y0 = cy + bh // 2
        draw.line([x0, y0, x0 + bw, y0], fill=COLOR_INK, width=6)  # Trục hoành
        draw.line([x0, y0, x0, y0 - bh], fill=COLOR_INK, width=6)  # Trục tung

        # Các cột tăng dần
        col_w = int(bw / 6)
        for idx_col in range(4):
            ch = int(bh * (0.25 + idx_col * 0.22))
            c_x = x0 + int(col_w * (idx_col + 1.2))
            c_y = y0 - ch
            col_color = COLOR_ACCENT_GREEN if idx_col == 3 else (255, 255, 255)
            draw.rectangle([c_x, c_y, c_x + col_w - 10, y0], outline=COLOR_INK, fill=col_color, width=4)

        # Mũi tên tăng trưởng dốc đứng
        arrow_pts = [
            (x0 + 40, y0 - 30),
            (x0 + int(bw * 0.4), y0 - int(bh * 0.45)),
            (x0 + bw - 20, y0 - bh - 20)
        ]
        for i in range(len(arrow_pts) - 1):
            draw.line([arrow_pts[i], arrow_pts[i+1]], fill=COLOR_ACCENT_ORANGE, width=7)
        # Đầu mũi tên
        last_x, last_y = arrow_pts[-1]
        draw.polygon([(last_x, last_y), (last_x - 25, last_y + 8), (last_x - 8, last_y + 25)], fill=COLOR_ACCENT_ORANGE)

    elif "rocket" in layout or "trophy" in layout:
        # Doodle tên lửa bay vút lên bầu trời thành công
        rx, ry = cx, cy - 20
        body_h = int(min(w, h) * 0.22)
        body_w = int(min(w, h) * 0.10)
        draw.ellipse([rx - body_w, ry - body_h, rx + body_w, ry + body_h // 2], outline=COLOR_INK, fill=(255, 255, 255), width=5)
        # Cánh tên lửa
        draw.polygon([(rx - body_w, ry), (rx - int(body_w * 1.8), ry + int(body_h * 0.6)), (rx - body_w, ry + int(body_h * 0.4))], fill=COLOR_ACCENT_BLUE, outline=COLOR_INK)
        draw.polygon([(rx + body_w, ry), (rx + int(body_w * 1.8), ry + int(body_h * 0.6)), (rx + body_w, ry + int(body_h * 0.4))], fill=COLOR_ACCENT_BLUE, outline=COLOR_INK)
        # Cửa sổ phi thuyền
        draw.ellipse([rx - 15, ry - 30, rx + 15, ry], outline=COLOR_INK, fill=COLOR_ACCENT_BLUE, width=4)
        # Lửa đẩy
        draw.polygon([(rx - 18, ry + int(body_h * 0.5)), (rx, ry + int(body_h * 1.1)), (rx + 18, ry + int(body_h * 0.5))], fill=COLOR_ACCENT_ORANGE)

        # Các ngôi sao tỏa sáng xung quanh
        for star_dx, star_dy in [(-180, -80), (190, -90), (-140, 80), (160, 90)]:
            draw.text((rx + star_dx, ry + star_dy), "✨", fill=COLOR_ACCENT_ORANGE, font=font_title)

    else:
        # Doodle bóng đèn ý tưởng & năng lượng sáng tạo
        r_bulb = int(min(w, h) * 0.16)
        draw.ellipse([cx - r_bulb, cy - r_bulb - 40, cx + r_bulb, cy + r_bulb - 40], outline=COLOR_INK, fill=(255, 250, 205), width=6)
        # Đuôi bóng đèn
        bw_tail = int(r_bulb * 0.75)
        draw.rectangle([cx - bw_tail // 2, cy + 30, cx + bw_tail // 2, cy + 70], outline=COLOR_INK, fill=(200, 200, 200), width=4)
        draw.line([cx - bw_tail // 2, cy + 45, cx + bw_tail // 2, cy + 45], fill=COLOR_INK, width=3)
        draw.line([cx - bw_tail // 2, cy + 58, cx + bw_tail // 2, cy + 58], fill=COLOR_INK, width=3)
        # Dây tóc bóng đèn
        draw.line([cx - 20, cy - 30, cx, cy - 60], fill=COLOR_ACCENT_ORANGE, width=5)
        draw.line([cx, cy - 60, cx + 20, cy - 30], fill=COLOR_ACCENT_ORANGE, width=5)

        # Các tia sáng bừng nở xung quanh
        for a in range(0, 360, 45):
            rad = math.radians(a)
            x_in = cx + int((r_bulb + 15) * math.cos(rad))
            y_in = cy - 40 + int((r_bulb + 15) * math.sin(rad))
            x_out = cx + int((r_bulb + 50) * math.cos(rad))
            y_out = cy - 40 + int((r_bulb + 50) * math.sin(rad))
            draw.line([(x_in, y_in), (x_out, y_out)], fill=COLOR_ACCENT_ORANGE, width=5)

    # 2. Thẻ từ khóa Doodle nổi bật đặt phía dưới
    card_w = int(w * 0.65)
    card_h = int(min(w, h) * 0.08)
    card_x0 = cx - card_w // 2
    card_y0 = h - pad - card_h - 18

    # Viền đổ bóng sketch cho thẻ từ khóa
    draw.rounded_rectangle([card_x0 + 4, card_y0 + 4, card_x0 + card_w + 4, card_y0 + card_h + 4], radius=10, fill=COLOR_MUTED)
    draw.rounded_rectangle([card_x0, card_y0, card_x0 + card_w, card_y0 + card_h], radius=10, fill=(255, 255, 255), outline=COLOR_INK, width=3)

    kw_text = f"★  {keyword.upper()}"
    bbox = font_title.getbbox(kw_text)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text((card_x0 + (card_w - tw) // 2, card_y0 + (card_h - th) // 2 - 2), kw_text, fill=COLOR_INK, font=font_title)

    img.save(str(out_path), quality=95)
    return out_path


if __name__ == "__main__":
    # Test thử nhanh
    t = "Lợi ích của việc chạy bộ mỗi sáng"
    scs = generate_script(t, 2)
    print("Sinh kịch bản test:")
    for s in scs:
        print(s)
        p = Path(f"output/test_{s['sceneIndex']}.png")
        draw_doodle_scene(s, "16:9", p)
        print("Đã tạo ảnh:", p)
