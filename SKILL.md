---
name: srt-whiteboard-animation
description: Chuyển đổi phụ đề SRT thành video hoạt hình bảng trắng vẽ tay trên nền giấy vàng kem. Quy trình: Đọc phụ đề → Xuất chiến lược hình ảnh → Xác nhận rồi tạo hình nét vẽ thống nhất → Gắn nhãn phân vùng theo ngữ nghĩa câu chuyện → Tinh chỉnh trên bàn xem trước → Render MP4. Điều phối kết hợp phân vùng mặt nạ (annotation.json / sequence / startMs / protectedRegions), nét mực vẽ stream liên tục (khung xương/lưới ink→color). Kích hoạt khi người dùng cung cấp phụ đề SRT và yêu cầu "làm video vẽ tay/bảng trắng theo phụ đề", "SRT tạo hoạt hình bảng trắng", "vẽ tay phân cảnh theo phụ đề".
---

# Hoạt hình bảng trắng SRT (Điều phối mặt nạ + Nét vẽ stream)

Chuyển phụ đề SRT thành hoạt hình bảng trắng vẽ tay: **Điều phối** kế thừa phân vùng mặt nạ (hiển thị từng vùng theo thứ tự kịch bản, vùng chưa đến lượt hoàn toàn ẩn, phần chồng lấn dùng `protectedRegions` bảo vệ); **Cách vẽ** chuyển sang nét vẽ stream liên tục — mỗi vùng vẽ trong mặt nạ cho phép của mình, ngòi bút lướt liên tục dọc theo khung xương/lưới để hạ mực (đi nét `ink` → tô màu `color`), tất cả các vùng dùng chung một canvas liên tục, vùng đã vẽ xong được giữ nguyên trên canvas.

Khác với việc nhảy từng ô hay xóa khối chữ nhật đơn điệu: Nét vẽ ở đây là **dòng chảy liên tục**; khác với stream cả bức tranh: Công cụ này vẽ **theo từng phân vùng ngữ nghĩa của phụ đề**, kiểm soát được thứ tự xuất hiện và thời điểm xuất hiện của từng chi tiết.

## Các tham số mặc định

| Mục | Yêu cầu mặc định |
|---|---|
| Nền giấy | Sử dụng màu giấy vàng kem cổ điển (khuyên dùng `#F5EBD7`); khi render sẽ lấy mẫu 4 góc ảnh gốc để nhuộm màu nền, cấm nền trắng tinh. |
| Cách vẽ | Nét vẽ stream liên tục cho từng vùng: Đi nét `ink` (phác thảo nét đen) → Tô màu `color` (phục hồi màu gốc); tỉ lệ trọng số `ink:color = 2:1`. |
| Đường nét vẽ | `--ink-path grid` (lưới, mặc định, ổn định) hoặc `skeleton` (dò khung xương, bám sát các nét vẽ mảnh rõ ràng). |
| Phong cách tô màu | `--color-fill contour-wipe` (quét viền, mặc định) hoặc `brush` (cọ vẽ quét theo nét). |
| Vùng chưa vẽ | Mặt nạ cho phép của mỗi vùng = hình chữ nhật `region` trừ đi "các vùng tiếp theo + protectedRegions"; vùng chưa vẽ hoàn toàn ẩn. |
| Nguồn thời lượng | `sceneDurationMs` của mỗi ảnh lấy từ khoảng thời gian của phân cảnh phụ đề tương ứng (gợi ý 25–35 giây/cảnh). |
| Khung chỉnh sửa | Bàn xem trước hiển thị đầy đủ các khung đánh số; khung này không xuất hiện trong video thành phẩm. |

## Quy chuẩn hình ảnh thống nhất (Bắt buộc)

Ảnh gốc của tất cả các cảnh phải tuân thủ cùng một ngôn ngữ thị giác; trước khi tạo ảnh hãy đưa các yêu cầu sau vào prompt, tạo xong kiểm tra từng tiêu chí:

- **Phong cách & Bố cục:** Tranh minh họa vẽ tay tối giản, phong cách phác thảo sketch, thẩm mỹ doodle tinh tế tương tự Notion. Tập trung biểu đạt khái niệm, không chạy theo tả thực; bố cục gọn gàng, nền sạch, chừa nhiều khoảng trống, cảm xúc tổng thể nhẹ nhàng, rõ ràng, nét vẽ/nhân vật/màu sắc thống nhất xuyên suốt.
- **Màu sắc & Chất liệu:** Nền giấy màu be `#F5EBD7`, đường nét phác thảo màu xám đậm; chỉ dùng đỏ, cam, lam làm điểm nhấn ý niệm tối giản. Không dùng màu rực rỡ, độ bão hòa cao hoặc họa tiết phức tạp.
- **Nhân vật & Đối tượng:** Đối tượng được thể hiện bằng đường nét viền đơn giản, ít chi tiết và nhiều khoảng trống, nhấn mạnh mối quan hệ/sự thay đổi/khái niệm cốt lõi thay vì tỉ lệ, chất liệu hay chi tiết siêu thực.
- **Tuyệt đối cấm:** Bất kỳ chữ viết, từ ngữ, chữ cái, con số hay nhãn mác nào trong ảnh gốc; cảm giác ảnh chụp thực tế, chi tiết 3D; bối cảnh phức tạp, dày đặc hay trang trí rườm rà.
- **Ngoại lệ bàn tay vẽ:** Hình bàn tay `drawing-hand.png` là tài nguyên đồ họa của công cụ, không tính là chữ trong ảnh bối cảnh.

## Các chặng xác nhận (Bắt buộc)

Mỗi bước trong quy trình mặc định **sau khi hoàn thành phải dừng lại chờ người dùng xác nhận rõ ràng** rồi mới tiến hành bước tiếp theo. Không được tự ý tạo trước ảnh, file cấu hình, preview hay video của bước sau khi chưa có xác nhận.

Hành động liên kết duy nhất được phép tự động: **Sau khi tạo xong file JSON cấu hình, tự động mở bàn xem trước `assets/preview.html` và nạp thư mục chứa file JSON đó**.

## Quy trình làm việc từng bước

1. **Đọc phụ đề, đề xuất chiến lược (chưa tạo ảnh):** Dùng `scripts/parse_srt.py` để phân tích file phụ đề SRT thành các câu thoại và chia cảnh gợi ý từ 25–35 giây/màn. Đề xuất: số thứ tự cảnh, ý cốt lõi, chủ thể hình ảnh, khoảng thời gian phụ đề và `sceneDurationMs`. Mỗi màn chỉ truyền đạt một ý cốt lõi. **Xong dừng lại chờ người dùng xác nhận.**
2. **Tạo hình vẽ nét:** Sau khi người dùng duyệt chiến lược, tạo ảnh vẽ nét tỉ lệ 16:9 nền giấy vàng kem `#F5EBD7`, các chủ thể giữ khoảng cách trống thoáng để dễ tách vùng. **Xong dừng lại đưa ảnh cho người dùng duyệt.**
3. **Đọc phụ đề rồi đối chiếu ảnh, lập cấu hình và mở bàn xem trước:** Sau khi người dùng duyệt ảnh, đọc kỹ phụ đề và quan sát ảnh gốc, lấy kích thước pixel thật. Lập trình tự vẽ theo mạch: "Dựng bối cảnh → Nhân vật/đồ vật chính → Xung đột hành động → Phản ứng/kết quả". Tạo file `<tên_ảnh>.annotation.json`. Sau đó mở ngay `assets/preview.html` trên trình duyệt để kiểm tra. **Dừng lại chờ người dùng xác nhận cấu hình và xem trước.**
4. **Tạo ảnh xem trước phân vùng:** Sau khi người dùng duyệt, chạy `render_annotation_preview.py` để xuất ảnh kiểm tra số thứ tự và hướng mũi tên vẽ, đảm bảo không có chi tiết nào vượt ra ngoài canvas. **Dừng lại chờ xác nhận.**
5. **Tinh chỉnh trên bàn xem trước và Lưu:** Người dùng kéo thả chỉnh lại tọa độ ô chữ nhật, thời gian bắt đầu/kết thúc, câu phụ đề, sắp xếp lại thứ tự vẽ. Bấm "Lưu cảnh này" để ghi đè vào file `.annotation.json`. **Xong dừng lại chờ xác nhận.**
6. **Chạy lệnh render video:** Dùng `render_stream_whiteboard.py` để xuất video MP4 sắc nét từng cảnh. Kiểm tra 3 thời điểm: đầu video, giữa chừng các vùng đè nhau, và kết thúc. **Dừng lại chờ xác nhận.**
7. **Ghép nối nhiều cảnh:** Dùng `merge_scenes.py` để ghép các cảnh MP4 lại theo thứ tự thành một video hoàn chỉnh. **Hoàn tất.**

## Cấu trúc thư mục quy ước

Trong dự án của người dùng:

```text
assets/whiteboard/<tên_dự_án>/
  scene-01-<tên>.png
  scene-01-<tên>.annotation.json     # Cùng tên với ảnh png
  scene-01-<tên>-whiteboard.mp4      # Video thành phẩm
  scene-01-<tên>-preview.mp4         # Video xem trước chất lượng thấp
```

## Định dạng cấu hình và tọa độ chuẩn pixel

1. **Căn cứ đọc:** Trước khi tạo cấu hình phải có cả phụ đề và ảnh gốc thật.
2. **Căn cứ thứ tự:** `sequence`, `startMs` và `label` phải phản ánh diễn biến trước sau của lời thoại.
3. **Căn cứ tọa độ:** Xuất pixel nguyên `x`, `y`, `width`, `height` theo hệ tọa độ ảnh gốc; gốc tọa độ góc trên bên trái, cấm dùng phần trăm hay tỉ lệ ước lượng. `canvas.width` / `canvas.height` phải đúng bằng kích thước pixel ảnh gốc.
4. **Các trường của phần tử:** Mỗi phần tử gồm `sequence`, `narrativeRole`, `subtitle`, `region`, `reveal`, `handPath`. `narrativeRole` ghi rõ vai trò trong cốt truyện; `subtitle` chứa văn bản phụ đề tương ứng.
5. **Kiểm tra vùng bảo vệ:** Các chủ thể chồng lấn nhau cần dùng `protectedRegions` ở phần tử trước để che chắn, tránh lộ nét vẽ sau sớm.

## Mô hình thời gian (Dành riêng cho nét vẽ stream)

- **Tổng thời lượng mỗi cảnh** `sceneDurationMs` lấy từ khoảng thời gian của cảnh trong phụ đề (`scenes[].sceneDurationMs`).
- **Vẽ nối tiếp tuần tự:** Cách vẽ stream là một ngòi bút di chuyển, các vùng trong một cảnh nên **tiến hành nối tiếp theo thời gian** (`startMs` không chồng lấn): Vùng tiếp theo bắt đầu từ `startMs + durationMs` của vùng trước (+ khoảng nghỉ 100–300ms).
- **Phân bổ ink→color trong mỗi vùng:** Mỗi vùng sẽ chia `durationMs` theo tỉ lệ `ink:color = 2:1` (2 phần vẽ nét đen, 1 phần tô màu).
- **Dừng xem kết thúc:** Sau khi vẽ xong tất cả các vùng, video tự động bù đủ `sceneDurationMs` và đảm bảo dừng lại ít nhất 0.5 giây ảnh hoàn chỉnh.

## Bất biến của mặt nạ che chắn

- Tại thời điểm `t`, một khối chỉ được hiển thị các pixel tương ứng với tiến độ vẽ hiện tại; khối chưa đến lượt tuyệt đối không được lộ bất kỳ đường nét hay màu sắc nào.
- **Mặt nạ cho phép** của mỗi vùng = vùng chữ nhật `region` trừ đi **tất cả các `region` của các khối phía sau**, trừ tiếp `protectedRegions` của chính khối đó.

## Ví dụ mẫu cấu hình

```json
{
  "sceneId": "scene-01",
  "canvas": { "width": 1672, "height": 941 },
  "storyBasis": "Tóm tắt sự kiện của phân cảnh này",
  "sceneDurationMs": 9000,
  "elements": [
    {
      "id": "rockery",
      "label": "Bối cảnh hòn non bộ",
      "sequence": 1,
      "narrativeRole": "Dựng bối cảnh câu chuyện",
      "subtitle": "Trên núi khỉ, một chú khỉ con ngồi trên đỉnh hòn non bộ, tay cầm một quả chuối.",
      "type": "structure",
      "region": { "x": 20, "y": 120, "width": 540, "height": 780 },
      "reveal": { "direction": "top_to_bottom", "startMs": 300, "durationMs": 2600, "maskPaddingPx": 22, "protectedRegions": [] },
      "handPath": { "start": [290, 130], "end": [290, 890], "easing": "easeInOut" }
    }
  ]
}
```

## Các lệnh thực thi

Tất cả các script chạy bằng python trong môi trường `.venv`:

1. **Chuẩn bị môi trường:**
   ```bash
   python scripts/prepare_env.py --check
   python scripts/prepare_env.py
   ```
2. **Phân tích phụ đề + Gợi ý phân cảnh:**
   ```bash
   python scripts/parse_srt.py <phude.srt> --target-sec 30 --min-sec 25 --max-sec 35
   ```
3. **Ảnh kiểm tra phân vùng:**
   ```bash
   python scripts/render_annotation_preview.py <anh.png> <cấu_hình.json> <output_preview.png>
   ```
4. **Bàn xem trước trực quan (không cần server):** Mở `assets/preview.html` trên Chrome / Edge, chọn thư mục để sửa và lưu trực tiếp.
5. **Render video từng cảnh:**
   ```bash
   <ENV_PY> scripts/render_stream_whiteboard.py <anh.png> <cấu_hình.json> <output.mp4> assets/drawing-hand.png \
       [--ink-path grid|skeleton] [--color-fill contour-wipe|brush] [--total-ms <mili_giay>]
   ```
6. **Ghép nối nhiều cảnh:**
   ```bash
   <ENV_PY> scripts/merge_scenes.py --inputs canh1.mp4 canh2.mp4 canh3.mp4 --output final.mp4
   ```
