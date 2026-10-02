import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Đảm bảo in tiếng Việt không bị lỗi UnicodeEncodeError trên Windows
if sys.platform.startswith("win"):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _get_font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    font_candidates = [
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/msyh.ttc",
    ]
    for fc in font_candidates:
        if Path(fc).exists():
            try:
                return ImageFont.truetype(fc, size)
            except Exception:
                continue
    return ImageFont.load_default()


def main(image_path: str, annotation_path: str, output_path: str) -> int:
    img_p = Path(image_path)
    ann_p = Path(annotation_path)
    out_p = Path(output_path)

    if not img_p.exists():
        print(f"[err] Không tìm thấy file ảnh: {image_path}", file=sys.stderr)
        return 1
    if not ann_p.exists():
        print(f"[err] Không tìm thấy file cấu hình annotation: {annotation_path}", file=sys.stderr)
        return 1

    try:
        data = json.loads(ann_p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[err] Không thể đọc hoặc phân tích cú pháp JSON: {e}", file=sys.stderr)
        return 1

    try:
        image = Image.open(img_p).convert("RGBA")
    except Exception as e:
        print(f"[err] Không thể mở file ảnh: {e}", file=sys.stderr)
        return 1

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    small_font = _get_font(18)
    colors = [(38, 103, 255, 225), (255, 105, 92, 225), (41, 167, 102, 225), (181, 100, 255, 225)]

    elements = data.get("elements", [])
    for index, element in enumerate(elements, start=1):
        region = element.get("region", {})
        x, y = int(round(region.get("x", 0))), int(round(region.get("y", 0)))
        w, h = int(round(region.get("width", 100))), int(round(region.get("height", 100)))
        right, bottom = x + w, y + h
        color = colors[(index - 1) % len(colors)]
        fill = (*color[:3], 24)
        draw.rounded_rectangle((x, y, right, bottom), radius=12, outline=color, width=4, fill=fill)
        draw.ellipse((x + 8, y + 8, x + 44, y + 44), fill=color)
        draw.text((x + 19, y + 8), str(index), anchor="ma", font=small_font, fill="white")

        direction = element.get("reveal", {}).get("direction", "")
        label_text = element.get("label", f"Vùng {index}")
        label = f"{index}. {label_text}  {direction}".strip()
        draw.rounded_rectangle((x + 52, y + 8, min(right - 8, x + 52 + len(label) * 16), y + 46), radius=6, fill=(255, 255, 255, 225))
        draw.text((x + 60, y + 12), label, font=small_font, fill=color)

        hand_path = element.get("handPath") or {}
        if "start" in hand_path and "end" in hand_path:
            start = tuple(hand_path["start"])
            end = tuple(hand_path["end"])
            draw.line((start, end), fill=color, width=4)
            draw.polygon((end, (end[0] - 13, end[1] - 7), (end[0] - 13, end[1] + 7)), fill=color)

    result = Image.alpha_composite(image, overlay).convert("RGB")
    out_p.parent.mkdir(parents=True, exist_ok=True)
    result.save(out_p, quality=95)
    print(f"[ok] Đã tạo ảnh xem trước: {out_p}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tạo ảnh xem trước các vùng phân cảnh và thứ tự vẽ")
    parser.add_argument("image", help="Đường dẫn file ảnh gốc (.png/.jpg)")
    parser.add_argument("annotation", help="Đường dẫn file annotation (.annotation.json)")
    parser.add_argument("output", help="Đường dẫn file ảnh xuất xem trước (.png/.jpg)")
    args = parser.parse_args()

    sys.exit(main(args.image, args.annotation, args.output))
