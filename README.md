---
title: Srt Ai
emoji: 📚
colorFrom: gray
colorTo: gray
sdk: gradio
sdk_version: 6.29.0
python_version: '3.12'
app_file: app.py
pinned: false
license: mit
short_description: Tạo video Whiteboard Animation tự động bằng AI
---

# Hoạt hình bảng trắng SRT (SRT Whiteboard Animation Skill)

Công cụ chuyển đổi phụ đề SRT thành video hoạt hình vẽ tay trên bảng trắng theo trình tự diễn biến kịch bản. Dự án kết hợp giữa **điều phối mặt nạ phân vùng** và **vẽ nét stream liên tục**: Mỗi thành phần xuất hiện lần lượt theo lời thoại, đầu bút lướt vẽ mực đen rồi dần tô màu, cuối cùng xuất ra file MP4.

Thích hợp làm video bài giảng kiến thức, video thuyết minh kể chuyện, phụ đề khóa học hoặc kịch bản video ngắn với phong cách tranh vẽ doodle trên nền giấy vàng kem cổ điển.

## Minh họa hiệu ứng

**Quy trình thể hiện:** Theo diễn biến lời thoại, bàn tay lần lượt vẽ bối cảnh, nhân vật chính, xung đột hành động và cuối cùng là phản ứng/kết quả theo từng vùng kịch bản định sẵn.

## Khả năng cốt lõi

- Phân tích phụ đề SRT và tự động chia cảnh theo thời lượng gợi ý 25–35 giây.
- Lên chiến lược phân cảnh và hình ảnh, đảm bảo mỗi màn chỉ tập trung diễn đạt một ý cốt lõi.
- Xây dựng thứ tự vẽ theo trình tự diễn biến câu chuyện thay vì tọa độ hình học đơn thuần.
- Dùng `annotation.json` quản lý các vùng vẽ, thời gian, phụ đề liên kết và vùng bảo vệ chồng lấn.
- Mỗi vùng áp dụng nét vẽ stream liền mạch: Trước đi nét mực `ink`, sau tô màu `color`.
- Hỗ trợ giao diện web cục bộ để xem trước, kéo thả chỉnh vùng, thứ tự, thời gian và phụ đề.
- Hỗ trợ render từng phân cảnh và tự động ghép nối thành MP4 hoàn chỉnh.

## Cách thức hoạt động

Quy trình hoạt động dựa trên nguyên tắc "Theo sát phụ đề, xác nhận từng bước" nhằm tránh lãng phí thời gian render khi kịch bản hay hình ảnh chưa hoàn thiện:

1. Phân tích SRT, đề xuất phân cảnh và hình minh họa.
2. Xác nhận kịch bản rồi tạo hình vẽ nét theo phong cách thống nhất.
3. Xác nhận nét vẽ, kết hợp phụ đề và ảnh gốc để tạo file cấu hình tọa độ, sau đó mở giao diện xem trước.
4. Kiểm tra ảnh bố cục và chiều hướng nét vẽ.
5. Tinh chỉnh vùng vẽ, thứ tự, thời lượng và phụ đề trên trang xem trước rồi bấm Lưu.
6. Xác nhận cấu hình cuối cùng, chạy lệnh render từng phân cảnh ra MP4.
7. Ghép nối các phân cảnh thành video hoàn chỉnh (đối với video nhiều cảnh).

## Quy chuẩn hình ảnh

- Nền giấy vàng kem cổ điển: Gợi ý mã màu `#F5EBD7`
- Nét phác thảo màu xám đậm; chỉ dùng đỏ, cam, lam làm điểm nhấn tối giản
- Tranh vẽ doodle tối giản, nền sạch sẽ và nhiều khoảng trống thoáng
- Không chèn chữ văn bản, nhãn mác, hiệu ứng 3D tả thực hay họa tiết phức tạp vào ảnh gốc

## Cài đặt & Môi trường

Dự án tích hợp sẵn script tự động tạo môi trường ảo Python. Lần đầu tiên sử dụng, hãy chạy:

```bash
python scripts/prepare_env.py --check
python scripts/prepare_env.py
```

Sau khi thành công, lệnh sẽ in ra `ENV_PY=<đường_dẫn>`; các lệnh render tiếp theo hãy dùng trình thông dịch này để đảm bảo cô lập thư viện.

## Cấu trúc tài nguyên dự án

```text
assets/whiteboard/<tên_dự_án>/
├── scene-01-<tên>.png
├── scene-01-<tên>.annotation.json
├── scene-01-<tên>-whiteboard.mp4
└── scene-01-<tên>-preview.mp4
```

Tên ảnh và file cấu hình phải trùng khớp nhau, ví dụ `scene-01-demo.png` tương ứng với `scene-01-demo.annotation.json`.

## Định dạng cấu hình Annotation

Mỗi phần tử dùng tọa độ pixel nguyên theo kích thước ảnh gốc, liên kết với sự kiện kịch bản qua `sequence`, `subtitle` và `narrativeRole`. Các vùng nên sắp xếp theo thứ tự: "Bối cảnh → Nhân vật/Đồ vật chính → Xung đột/Hành động → Phản ứng/Kết quả".

```json
{
  "sceneId": "scene-01",
  "canvas": { "width": 1672, "height": 941 },
  "storyBasis": "Khỉ con cầm quả chuối trên núi, khỉ lớn lao tới cướp, lũ trẻ đứng xem xung quanh.",
  "sceneDurationMs": 9000,
  "elements": [
    {
      "id": "rockery",
      "label": "Bối cảnh núi khỉ",
      "sequence": 1,
      "narrativeRole": "Dựng bối cảnh câu chuyện",
      "subtitle": "Trên núi khỉ, một chú khỉ con ngồi trên đỉnh hòn non bộ, tay cầm một quả chuối.",
      "type": "structure",
      "region": { "x": 20, "y": 120, "width": 540, "height": 780 },
      "reveal": {
        "direction": "top_to_bottom",
        "startMs": 300,
        "durationMs": 2600,
        "maskPaddingPx": 22,
        "protectedRegions": []
      },
      "handPath": {
        "start": [290, 130],
        "end": [290, 890],
        "easing": "easeInOut"
      }
    }
  ]
}
```

`direction` và `handPath` dùng cho mô phỏng trên giao diện web; video thành phẩm thực tế sẽ được bộ render tự động tạo nét vẽ bám sát hình ảnh. Với các chi tiết đè lên nhau, đặt vùng che chắn vào `protectedRegions` của phần tử trước để các nét sau không bị lộ sớm.

## Các lệnh thường dùng

Phân tích phụ đề và đề xuất phân cảnh:

```bash
python scripts/parse_srt.py <phude.srt> --target-sec 30 --min-sec 25 --max-sec 35
```

Tạo ảnh kiểm tra vùng vẽ và thứ tự:

```bash
python scripts/render_annotation_preview.py <đường_dẫn_ảnh> <đường_dẫn_json> <đường_dẫn_ảnh_xem_trước>
```

Mở `assets/preview.html` trên trình duyệt Chrome/Edge, bấm "Mở thư mục…" để chỉnh sửa vùng, thứ tự, thời gian và câu phụ đề tương ứng.

Render một phân cảnh:

```bash
python scripts/render_stream_whiteboard.py <đường_dẫn_ảnh> <đường_dẫn_json> <output.mp4>
```

Ghép nối nhiều phân cảnh:

```bash
python scripts/merge_scenes.py canh1.mp4 canh2.mp4 -o final.mp4
```

Render và ghép nối toàn bộ video tự động chỉ với **1 lệnh duy nhất**:

```bash
python scripts/build_video.py <thư_mục_chứa_các_cảnh> -o output/video_hoan_chinh.mp4
```

## Tiêu chuẩn chất lượng

- Khung hình đầu tiên là nền giấy vàng kem sạch sẽ, không lộ trước bất kỳ đường nét nào.
- Kích thước `canvas` trùng khớp kích thước ảnh gốc, mọi tọa độ là số nguyên nằm gọn trong ảnh.
- `sequence`, `startMs` bám sát mạch diễn biến của phụ đề.
- Ở các khung hình giữa chừng, các vùng chưa vẽ và vùng bảo vệ tuyệt đối không hiện trước.
- Đầu bút bám sát theo nét vẽ stream thật; nếu hình nét rõ ràng có thể dùng `--ink-path skeleton`.
- Kết thúc mỗi cảnh dừng lại ít nhất 0.5 giây ảnh hoàn chỉnh; ghép nhiều cảnh theo đúng thứ tự kịch bản.

## Cấu trúc thư mục

```text
srt-whiteboard-animation/
├── SKILL.md                         # Hướng dẫn quy trình & nguyên tắc chuẩn
├── assets/
│   ├── drawing-hand.png              # Ảnh tư liệu bàn tay cầm bút
│   ├── preview.html                  # Giao diện xem trước & chỉnh sửa trực quan
├── examples/                         # Tài nguyên ví dụ mẫu
├── scripts/
│   ├── parse_srt.py                  # Phân tích phụ đề và gợi ý phân cảnh
│   ├── render_annotation_preview.py  # Tạo ảnh kiểm tra thứ tự vùng vẽ
│   ├── render_stream_whiteboard.py   # Bộ render hoạt hình vẽ tay ra MP4
│   ├── merge_scenes.py               # Ghép nối các phân cảnh thành video dài
│   └── prepare_env.py                # Chuẩn bị môi trường & cài thư viện
└── agents/openai.yaml                # Cấu hình Metadata Agent
```

## Giấy phép

Dự án phát hành theo giấy phép nguồn mở MIT License, chi tiết xem [LICENSE](LICENSE).
