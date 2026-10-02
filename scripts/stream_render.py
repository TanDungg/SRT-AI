#!/usr/bin/env python3
"""
Hoạt hình vẽ tay nét liền - Bộ render một ảnh đơn

Render một bức ảnh màu thành hoạt hình bảng trắng với "đầu bút lướt theo quỹ đạo liên tục, vừa đi vừa hạ mực".
Toàn bộ quá trình gồm 3 giai đoạn:
  Đi nét (ink)    Đầu bút đi theo dòng nét tạo bản vẽ nét đen
  Tô màu (color)  Quay lại theo cùng quỹ đạo, đầu bút chuyển màu gốc để thắp sáng bức tranh
  Dừng xem (gaze) Dừng lại sau khi vẽ xong, hiển thị toàn bộ ảnh gốc hoàn chỉnh

Khác với cách "nhảy từng ô rời rạc": Bộ render này coi thứ tự vẽ là đường gấp khúc chuyển động của đầu bút,
nội suy giữa các điểm kề nhau, cọ mực trượt theo đầu bút hạ mực liên tục tạo dòng chảy nét vẽ mượt mà.
"""
from __future__ import annotations

import argparse
import datetime
import math
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

if sys.platform.startswith("win"):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import cv2
import numpy as np

# ──────────────────────────────────────────────────────────────
# Định vị tài nguyên
# ──────────────────────────────────────────────────────────────
_SCRIPT_DIR = Path(__file__).resolve().parent
_ASSETS_DIR = _SCRIPT_DIR.parent / "assets"
DEFAULT_HAND_PNG = _ASSETS_DIR / "drawing-hand.png"


def _imread_any(path: str | Path, flags: int = cv2.IMREAD_COLOR) -> np.ndarray | None:
    """
    Đọc ảnh, tương thích với đường dẫn Windows chứa ký tự Unicode/dấu cách.
    Dùng np.fromfile đọc byte, sau đó chuyển cho cv2.imdecode giải mã,
    tránh lỗi của cv2.imread khi gặp đường dẫn non-ASCII.
    """
    raw = np.fromfile(str(path), dtype=np.uint8)
    if raw.size == 0:
        return None
    return cv2.imdecode(raw, flags)


# ──────────────────────────────────────────────────────────────
# Tập trung tham số render
# ──────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Config:
    fps: int = 60                  # Tần số khung hình cao giúp đầu bút di chuyển mượt như viết thật
    grid_edge: int = 10            # Lưới nhỏ hơn giúp giảm cảm giác khối hộp khi hiện nét
    sample_step: int = 2           # Khoảng cách lấy mẫu pixel của quỹ đạo đầu bút
    cap_long_edge: int = 1080      # Giới hạn cạnh dài ảnh đầu vào
    brush_radius: int = 40         # Bán kính cọ vẽ hình tròn trong giai đoạn tô màu
    ink_weight: int = 2            # Trọng số giai đoạn đi nét: Dành nhiều thời gian hơn để quan sát nét vẽ
    color_weight: int = 1          # Trọng số giai đoạn tô màu
    gaze_seconds: float = 1.0      # Số giây dừng xem ảnh hoàn chỉnh ở cuối (mặc định 1.0s)
    ink_threshold: int = 10        # Mức xám pixel thấp hơn giá trị này được coi là "nét mực"
    ink_reveal_radius: int = 4     # Bán kính nét vẽ lộ diện theo mỗi đoạn quỹ đạo đầu bút
    target_hand_height: int = 493  # Chiều cao mục tiêu của ảnh bàn tay sau khi co giãn (chuẩn 1080p)
    # Tọa độ chuẩn hóa của ngòi bút trong ảnh bàn tay (0..1)
    tip_anchor_x: float = 0.0
    tip_anchor_y: float = 0.0
    canvas_hex: str = "#F6F1E3"    # Màu nền giấy canvas
    match_bg: bool = True          # Nhuộm nền ảnh gốc thành màu canvas để đồng bộ
    match_bg_threshold: int = 28   # Chênh lệch màu nền nhỏ hơn mức này coi là nền
    steps_per_frame: int = 4       # Số điểm hạ mực cơ bản trên mỗi khung hình
    # ── Chế độ tô màu contour-wipe ──
    color_fill: str = "contour-wipe"  # Phong cách tô màu: "contour-wipe" quét viền từ trên xuống (mặc định) | "brush" cọ vẽ theo nét
    wipe_decay: float = 0.86       # Hệ số suy giảm trường cản theo hàng xuống dưới
    wipe_delay_ratio: float = 0.04  # Tỉ lệ pixel bị giữ lại tại đường viền
    wipe_blocks: int = 18          # Số lượt quét ngang qua lại của đầu bút
    # ── Tự điều chỉnh nhịp dừng ở giai đoạn đi nét (mô phỏng nhịp thở/nhấc bút) ──
    pause_mode: str = "heavy"
    pause_ratio_heavy: float = 0.03   # Tỉ lệ dừng cho nhịp chậm (~3% số khung hình)
    pause_ratio_light: float = 0.008  # Tỉ lệ dừng nhẹ (~0.8%)
    pause_heavy_fpc: float = 0.7
    pause_light_fpc: float = 0.4
    # ── Chế độ đường nét vẽ ──
    # ink_path_mode: "grid" nội suy tâm ô lưới (mặc định) | "skeleton" dò khung xương mức pixel
    ink_path_mode: str = "grid"
    skeleton_min_points: int = 8        # Số điểm tối thiểu của nét khung xương (lọc rác)
    skeleton_resample_spacing: float = 2.5  # Khoảng cách lấy mẫu lại khung xương (pixel)


# ──────────────────────────────────────────────────────────────
# Tiện ích nhỏ
# ──────────────────────────────────────────────────────────────
def _hex_to_bgr(hex_color: str) -> np.ndarray:
    digits = hex_color.lstrip("#")
    if len(digits) != 6:
        raise ValueError(f"Giá trị màu không hợp lệ: {hex_color}")
    r = int(digits[0:2], 16)
    g = int(digits[2:4], 16)
    b = int(digits[4:6], 16)
    return np.array([b, g, r], dtype=np.uint8)


def _bounding_box(mask: np.ndarray) -> tuple[tuple[int, int], tuple[int, int]]:
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        return (0, 0), (0, 0)
    return (int(xs.min()), int(ys.min())), (int(xs.max()), int(ys.max()))


# ──────────────────────────────────────────────────────────────
# Phân chia các khối ô mực
# ──────────────────────────────────────────────────────────────
def _to_grid_blocks(image: np.ndarray, edge: int) -> np.ndarray:
    """Cắt ảnh HxW(xC) thành dạng khối (số hàng, số cột, edge, edge[, C])."""
    image = np.ascontiguousarray(image)
    h, w = image.shape[:2]
    if h % edge or w % edge:
        raise ValueError(f"Kích thước ảnh {w}x{h} phải là bội số của {edge}")
    rows, cols = h // edge, w // edge
    if image.ndim == 2:
        return image.reshape(rows, edge, cols, edge).transpose(0, 2, 1, 3)
    return image.reshape(rows, edge, cols, edge, image.shape[2]).transpose(0, 2, 1, 3, 4)


def _active_mask(threshold_map: np.ndarray, edge: int, threshold: int) -> np.ndarray:
    """Ô lưới nào chứa nét mực: Trả về True nếu trong khối có pixel độ xám thấp hơn ngưỡng."""
    blocks = _to_grid_blocks(threshold_map, edge)
    return np.any(blocks < threshold, axis=(2, 3))


# ──────────────────────────────────────────────────────────────
# Phân cụm luồng mực + Di chuyển theo gradient mật độ
# ──────────────────────────────────────────────────────────────
def _label_components(active: np.ndarray) -> tuple[np.ndarray, int]:
    """Gắn nhãn miền liên thông 8 hướng cho các ô có mực, trả về (ma trận nhãn, số miền)."""
    n, labels = cv2.connectedComponents(active.astype(np.uint8), connectivity=8)
    return labels, n - 1  # Bỏ nhãn nền 0


def _component_cells(labels: np.ndarray, label: int) -> list[tuple[int, int]]:
    coords = np.argwhere(labels == label)
    return [(int(r), int(c)) for r, c in coords]


def _merge_small_components(
    components: list[list[tuple[int, int]]],
    merge_threshold: int,
) -> list[list[tuple[int, int]]]:
    """
    Gộp các miền liên thông nhỏ vào miền lớn gần nhất trong không gian.
    Tránh việc các mảnh vụn làm gián đoạn nét vẽ của khối chữ lớn.
    Nếu không có miền lớn nào thì giữ nguyên.
    """
    if not components:
        return components
    big = [c for c in components if len(c) > merge_threshold]
    small = [c for c in components if len(c) <= merge_threshold]
    if not small or not big:
        return components

    # Tính trước tâm của mỗi vùng lớn
    centroids = []
    for cells in big:
        rs = [c[0] for c in cells]
        cs = [c[1] for c in cells]
        centroids.append((sum(rs) / len(rs), sum(cs) / len(cs)))

    # Gộp từng mảnh nhỏ vào vùng lớn gần nhất
    merged = [list(cells) for cells in big]  # Bản sao, có thể thêm phần tử
    for cells in small:
        rs = [c[0] for c in cells]
        cs = [c[1] for c in cells]
        cr = sum(rs) / len(rs)
        cc = sum(cs) / len(cs)
        best = min(
            range(len(big)),
            key=lambda i: (centroids[i][0] - cr) ** 2 + (centroids[i][1] - cc) ** 2,
        )
        merged[best].extend(cells)
    return merged


def _bounds(cells: Sequence[tuple[int, int]]) -> tuple[int, int, int, int]:
    rows = [row for row, _ in cells]
    cols = [col for _, col in cells]
    return min(rows), min(cols), max(rows), max(cols)


def _split_bridge_connected_component(
    cells: list[tuple[int, int]],
    min_side_cells: int = 20,
) -> list[list[tuple[int, int]]]:
    """Split a very wide component when it is connected only by a thin bridge.

    A baseline, arrow, or stray outline can join separate objects into one
    connected component.  Drawing that component with one nearest-neighbour
    walk makes the pen alternate between those objects.  Valleys in the
    vertical ink projection are reliable weak-bridge signals at grid scale.
    """
    if len(cells) < min_side_cells * 2:
        return [cells]

    min_row, min_col, max_row, max_col = _bounds(cells)
    height = max_row - min_row + 1
    width = max_col - min_col + 1
    if width < 16 or height < 10:
        return [cells]

    counts = {col: 0 for col in range(min_col, max_col + 1)}
    for _, col in cells:
        counts[col] += 1
    valley_limit = max(3, int(np.ceil(height * 0.30)))
    edge_guard = 4
    valleys: list[tuple[int, int]] = []
    start: int | None = None
    for col in range(min_col, max_col + 2):
        low = col <= max_col and counts[col] <= valley_limit
        if low and start is None:
            start = col
        elif not low and start is not None:
            end = col - 1
            if (
                end - start + 1 >= 2
                and start > min_col + edge_guard
                and end < max_col - edge_guard
            ):
                valleys.append((start, end))
            start = None
    if not valleys:
        return [cells]

    # Prefer the broadest empty corridor.  It is much less likely to be an
    # internal detail of a character than a one-column dip.
    start, end = max(valleys, key=lambda band: (band[1] - band[0], -band[0]))
    cut = (start + end) // 2
    left = [cell for cell in cells if cell[1] <= cut]
    right = [cell for cell in cells if cell[1] > cut]
    if len(left) < min_side_cells or len(right) < min_side_cells:
        return [cells]
    return (
        _split_bridge_connected_component(left, min_side_cells)
        + _split_bridge_connected_component(right, min_side_cells)
    )


def _split_bridge_connected_components(
    components: list[list[tuple[int, int]]],
) -> list[list[tuple[int, int]]]:
    return [
        piece
        for cells in components
        for piece in _split_bridge_connected_component(cells)
    ]


def _boxes_touch(
    first: tuple[int, int, int, int],
    second: tuple[int, int, int, int],
    margin: int = 2,
) -> bool:
    """Whether two component boxes belong to the same visual region."""
    a_top, a_left, a_bottom, a_right = first
    b_top, b_left, b_bottom, b_right = second
    return not (
        a_right + margin < b_left
        or b_right + margin < a_left
        or a_bottom + margin < b_top
        or b_bottom + margin < a_top
    )


def _group_adjacent_stroke_groups(
    groups: list[tuple[str, list[tuple[int, int]]]],
) -> list[list[tuple[str, list[tuple[int, int]]]]]:
    """Keep overlapping label parts and outline pieces in one draw region."""
    regions: list[list[tuple[str, list[tuple[int, int]]]]] = []
    boxes: list[tuple[int, int, int, int]] = []
    for group in groups:
        group_box = _bounds(group[1])
        touching = [index for index, box in enumerate(boxes) if _boxes_touch(group_box, box)]
        if not touching:
            regions.append([group])
            boxes.append(group_box)
            continue
        target = touching[0]
        regions[target].append(group)
        top, left, bottom, right = boxes[target]
        boxes[target] = (
            min(top, group_box[0]), min(left, group_box[1]),
            max(bottom, group_box[2]), max(right, group_box[3]),
        )
        # Merge any regions newly bridged by the expanded box.
        for index in reversed(touching[1:]):
            regions[target].extend(regions.pop(index))
            other = boxes.pop(index)
            top, left, bottom, right = boxes[target]
            boxes[target] = (
                min(top, other[0]), min(left, other[1]),
                max(bottom, other[2]), max(right, other[3]),
            )
    return regions


def classify_stroke_groups(
    active: np.ndarray,
) -> list[tuple[str, list[tuple[int, int]]]]:
    """Classify connected ink regions as a main subject, text, or local contour."""
    labels, count = _label_components(active)
    components = [
        _component_cells(labels, label)
        for label in range(1, count + 1)
    ]
    components = [cells for cells in components if cells]
    if not components:
        return []

    # A long ground line may connect a mountain, a character, and a crowd.
    # Split that weak connection before any region ordering is decided.
    components = _split_bridge_connected_components(components)

    # Gộp mảnh vụn vào vùng lớn gần nhất để tránh ngắt quãng khi vẽ chữ
    total_cells = sum(len(c) for c in components)
    merge_threshold = max(3, int(total_cells * 0.005))
    components = _merge_small_components(components, merge_threshold)

    subject_index = max(range(len(components)), key=lambda index: len(components[index]))
    groups: list[tuple[str, list[tuple[int, int]], tuple[int, int, int]]] = []
    for index, cells in enumerate(components):
        min_row, min_col, max_row, max_col = _bounds(cells)
        height = max_row - min_row + 1
        width = max_col - min_col + 1
        density = len(cells) / (height * width)
        if index == subject_index:
            kind, rank = "subject", 0
        elif height >= 2 and width / height >= 2.2 and density >= 0.5:
            kind, rank = "text", 1
        else:
            kind, rank = "contour", 2
        groups.append((kind, cells, (rank, min_row, min_col)))

    groups.sort(key=lambda group: group[2])
    return [(kind, cells) for kind, cells, _ in groups]


def _density_seed(cells: Sequence[tuple[int, int]], radius: int = 2) -> tuple[int, int]:
    """Chọn ô có lân cận dày đặc nhất làm điểm bắt đầu, mô phỏng hạ bút từ nơi mực đậm nhất."""
    cell_set = set(cells)
    best = cells[0]
    best_score = -1
    for (r, c) in cells:
        score = sum(
            1
            for dr in range(-radius, radius + 1)
            for dc in range(-radius, radius + 1)
            if (r + dr, c + dc) in cell_set
        )
        if score > best_score:
            best_score = score
            best = (r, c)
    return best


def _gradient_walk(cells: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """
    Di chuyển tham lam theo gradient mật độ: Xuất phát từ ô hạt giống có mật độ cao nhất,
    mỗi bước ưu tiên ô có mật độ cao và góc đổi hướng nhỏ nhất tạo nét vẽ liền mạch.
    Khi không còn lân cận, nhảy tới ô chưa thăm gần nhất.
    """
    if not cells:
        return []

    cell_set = set(cells)
    seed = _density_seed(cells)
    visited: set[tuple[int, int]] = {seed}
    path: list[tuple[int, int]] = [seed]
    current = seed
    prev_dir = (0, 0)

    while len(visited) < len(cells):
        neighbors = [
            (r, c)
            for dr in (-1, 0, 1)
            for dc in (-1, 0, 1)
            if (dr or dc)
            and (r := current[0] + dr, c := current[1] + dc) in cell_set
            and (r, c) not in visited
        ]
        if neighbors:
            def cost(cell: tuple[int, int]) -> tuple:
                # Càng nhiều lân cận càng tốt, đổi hướng càng ít càng tốt, sắp xếp ổn định theo vị trí
                local = sum(
                    1
                    for dr in (-1, 0, 1)
                    for dc in (-1, 0, 1)
                    if (cell[0] + dr, cell[1] + dc) in cell_set
                    and (cell[0] + dr, cell[1] + dc) not in visited
                )
                step = (cell[0] - current[0], cell[1] - current[1])
                turn = (step[0] - prev_dir[0]) ** 2 + (step[1] - prev_dir[1]) ** 2
                return (-local, turn, cell[0], cell[1])

            nxt = min(neighbors, key=cost)
        else:
            # Nhấc bút: Nhảy tới ô chưa thăm gần nhất
            unvisited = [cell for cell in cells if cell not in visited]
            nxt = min(
                unvisited,
                key=lambda cell: (
                    (cell[0] - current[0]) ** 2 + (cell[1] - current[1]) ** 2,
                    cell[0],
                    cell[1],
                ),
            )

        prev_dir = (nxt[0] - current[0], nxt[1] - current[1])
        path.append(nxt)
        visited.add(nxt)
        current = nxt

    return path


def _nearest_neighbor_order(
    cells: Sequence[tuple[int, int]], seed: tuple[int, int]
) -> list[tuple[int, int]]:
    """Xuất phát từ seed, mỗi bước đi tới ô chưa thăm gần nhất tạo nét vẽ liên tục."""
    if not cells:
        return []
    remaining = list(cells)
    ordered: list[tuple[int, int]] = []
    current = seed if seed in remaining else remaining[0]
    while remaining:
        ordered.append(current)
        remaining.remove(current)
        if not remaining:
            break
        current = min(
            remaining,
            key=lambda cell: (cell[0] - ordered[-1][0]) ** 2
            + (cell[1] - ordered[-1][1]) ** 2,
        )
    return ordered


def _text_scan_order(
    cells: Sequence[tuple[int, int]], segment_cols: int = 4
) -> list[tuple[int, int]]:
    """
    Cách vẽ chuyên dụng cho vùng chữ: Quét ngang theo từng đoạn mô phỏng viết chữ.
    Chia các ô theo cột thành từng đoạn, thứ tự đoạn từ trái sang phải;
    trong đoạn di chuyển bám theo nét mực để tạo cảm giác viết tự nhiên.
    """
    if not cells:
        return []
    if segment_cols < 1:
        segment_cols = 1
    left_col = min(col for _, col in cells)
    # Phân nhóm theo cột bắt đầu, nhóm bên trái vẽ trước
    buckets: dict[int, list[tuple[int, int]]] = {}
    for cell in cells:
        bucket_key = (cell[1] - left_col) // segment_cols
        buckets.setdefault(bucket_key, []).append(cell)

    ordered: list[tuple[int, int]] = []
    prev_tail: tuple[int, int] | None = None
    for key in sorted(buckets):
        seg_cells = buckets[key]
        # Điểm bắt đầu của đoạn: Gần lối ra của đoạn trước để giảm nhấc bút
        if prev_tail is not None:
            seed = min(
                seg_cells,
                key=lambda cell: (cell[0] - prev_tail[0]) ** 2
                + (cell[1] - prev_tail[1]) ** 2,
            )
        else:
            seed = min(seg_cells, key=lambda cell: (cell[0], cell[1]))
        seg_order = _nearest_neighbor_order(seg_cells, seed)
        ordered.extend(seg_order)
        prev_tail = seg_order[-1]
    return ordered


def _order_stream_by_kind(
    kind: str, cells: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    """Chọn cách vẽ theo loại vùng: Chữ quét theo đoạn, chủ thể/đường viền đi theo gradient mật độ."""
    if kind == "text":
        return _text_scan_order(cells)
    return _gradient_walk(cells)


def _chain_region_paths(
    groups: list[tuple[str, list[tuple[int, int]]]],
) -> list[tuple[int, int]]:
    """Finish every component in one visual region before leaving it."""
    paths = [_order_stream_by_kind(kind, cells) for kind, cells in groups]
    remaining = [path for path in paths if path]
    ordered: list[tuple[int, int]] = []
    tail: tuple[int, int] | None = None
    while remaining:
        if tail is None:
            pick_index = 0  # groups retain subject/text/contour priority.
        else:
            pick_index = min(
                range(len(remaining)),
                key=lambda index: min(
                    (remaining[index][0][0] - tail[0]) ** 2
                    + (remaining[index][0][1] - tail[1]) ** 2,
                    (remaining[index][-1][0] - tail[0]) ** 2
                    + (remaining[index][-1][1] - tail[1]) ** 2,
                ),
            )
        path = remaining.pop(pick_index)
        if tail is not None and len(path) > 1:
            head_distance = (path[0][0] - tail[0]) ** 2 + (path[0][1] - tail[1]) ** 2
            end_distance = (path[-1][0] - tail[0]) ** 2 + (path[-1][1] - tail[1]) ** 2
            if end_distance < head_distance:
                path.reverse()
        ordered.extend(path)
        tail = path[-1]
    return ordered


def cluster_ink_streams(active: np.ndarray) -> list[list[tuple[int, int]]]:
    """
    Gom các ô mực thành các luồng nét vẽ theo ngữ nghĩa: Chủ thể -> Chữ -> Đường viền cục bộ,
    mỗi luồng chọn cách vẽ phù hợp; các luồng được liên kết động theo khoảng cách ngắn nhất để giảm nhấc bút.
    Trả về danh sách các luồng nét vẽ đã được sắp xếp.
    """
    if not active.any():
        return []
    groups = classify_stroke_groups(active)
    # A stream is now a complete visual region, not merely one connected
    # component.  Thus a label's border, its characters, and its arrow cannot
    # be interrupted by a different object that happens to be closer.
    regions = _group_adjacent_stroke_groups(groups)
    streams = [_chain_region_paths(region) for region in regions]
    streams = [s for s in streams if s]
    if not streams:
        return []

    # Liên kết: Bắt đầu từ chủ thể, sau đó nối tiếp luồng có điểm đầu gần điểm cuối hiện tại nhất，
    # đảo chiều luồng nếu cần để nét vẽ liền mạch。
    ordered: list[list[tuple[int, int]]] = []
    remaining = list(streams)
    tail: tuple[int, int] | None = None
    while remaining:
        if tail is None:
            pick_idx = 0  # classify đã xếp chủ thể lên đầu
        else:
            def dist_to_tail(stream: list[tuple[int, int]]) -> int:
                head = stream[0]
                return (head[0] - tail[0]) ** 2 + (head[1] - tail[1]) ** 2
            pick_idx = min(range(len(remaining)), key=lambda i: dist_to_tail(remaining[i]))
        pick = remaining.pop(pick_idx)
        # Đảo chiều nếu điểm cuối gần hơn điểm đầu
        if tail is not None and len(pick) > 1:
            head = pick[0]
            end = pick[-1]
            d_end = (end[0] - tail[0]) ** 2 + (end[1] - tail[1]) ** 2
            d_head = (head[0] - tail[0]) ** 2 + (head[1] - tail[1]) ** 2
            if d_end < d_head:
                pick = pick[::-1]
        ordered.append(pick)
        tail = pick[-1]
    return ordered


def flatten_streams(streams: list[list[tuple[int, int]]]) -> list[tuple[int, int]]:
    return [cell for stream in streams for cell in stream]


# ──────────────────────────────────────────────────────────────
# Phủ đầu bút / bàn tay
# ──────────────────────────────────────────────────────────────
def _load_hand(path: Path, target_h: int) -> tuple[np.ndarray, np.ndarray] | None:
    """
    Đọc tư liệu bàn tay và co giãn theo chiều cao mục tiêu.
    Ưu tiên kênh alpha làm mặt nạ; trả về (ảnh BGR, mặt nạ chuẩn hóa), lỗi trả về None.
    """
    if not path.exists():
        return None
    raw = _imread_any(path, cv2.IMREAD_UNCHANGED)
    if raw is None:
        return None

    if raw.ndim == 3 and raw.shape[2] == 4:
        hand = raw[:, :, :3]
        mask = raw[:, :, 3]
    else:
        hand = raw
        gray = cv2.cvtColor(hand, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray, 250, 255, cv2.THRESH_BINARY_INV)

    # Cắt về vùng hợp lệ
    (x0, y0), (x1, y1) = _bounding_box(mask)
    if x1 <= x0 or y1 <= y0:
        return None
    hand = hand[y0:y1 + 1, x0:x1 + 1]
    mask = mask[y0:y1 + 1, x0:x1 + 1]

    scale = target_h / hand.shape[0]
    new_w = max(1, int(round(hand.shape[1] * scale)))
    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
    hand = cv2.resize(hand, (new_w, target_h), interpolation=interp)
    mask = cv2.resize(mask, (new_w, target_h), interpolation=interp)
    mask = mask.astype(np.float32) / 255.0

    # Tô đen vùng ngoài mặt nạ để hòa trộn alpha
    hand[mask <= 0] = 0
    return hand, mask


def _procedural_tip(target_h: int) -> tuple[np.ndarray, np.ndarray]:
    """
    Đầu bút dự phòng: Tự động vẽ một cây bút dạ (thân gradient + ngòi tròn + bóng đổ).
    Không phụ thuộc file ảnh ngoài, tự hoạt động khi thiếu tư liệu.
    """
    w = max(1, int(target_h * 0.34))
    h = target_h
    rgba = np.zeros((h, w, 4), dtype=np.uint8)

    # Bóng đổ: Dải tối lệch vị trí làm mờ dưới đáy
    shadow = np.zeros((h, w), dtype=np.uint8)
    cv2.rectangle(shadow, (3, int(h * 0.06)), (w - 2, int(h * 0.62)), 90, thickness=-1)
    shadow = cv2.GaussianBlur(shadow, (15, 15), 0)
    rgba[:, :, 3] = shadow

    # Thân bút: Gradient dọc từ sáng sang tối
    for y in range(h):
        t = y / max(1, h - 1)
        shade = int(220 - 130 * t)
        rgba[y, :, 0:3] = (shade, shade, shade + 10)
    cv2.rectangle(rgba, (4, int(h * 0.04)), (w - 4, int(h * 0.58)), (0, 0, 0), thickness=1)

    # Ngòi bút tròn (màu ấm, mô phỏng mực)
    tip_cy = int(h * 0.70)
    cv2.circle(rgba, (w // 2, tip_cy), max(3, w // 4), (70, 90, 230), thickness=-1)

    # Hợp nhất viền thân bút và ngòi tròn làm mặt nạ alpha
    body_mask = np.zeros((h, w), dtype=np.uint8)
    cv2.rectangle(body_mask, (3, int(h * 0.04)), (w - 3, tip_cy), 255, thickness=-1)
    cv2.circle(body_mask, (w // 2, tip_cy), max(3, w // 4), 255, thickness=-1)
    body_mask = cv2.GaussianBlur(body_mask, (7, 7), 0)

    hand = rgba[:, :, :3]
    mask = np.maximum(rgba[:, :, 3], body_mask).astype(np.float32) / 255.0
    hand[mask <= 0] = 0
    return hand, mask


class TipOverlay:
    """Dán đầu bút/bàn tay lên canvas, căn ngòi bút khớp với điểm hạ mực có hòa trộn alpha."""

    def __init__(
        self,
        hand: np.ndarray,
        mask: np.ndarray,
        tip_anchor_x: float = 0.0,
        tip_anchor_y: float = 0.0,
    ) -> None:
        self.hand = hand
        self.mask = mask
        self.h, self.w = hand.shape[:2]
        self.mask_inv = 1.0 - mask
        # Tọa độ pixel ngòi bút trong ảnh bàn tay
        # Map normalized anchors exactly onto the source image's pixel range.
        self.tip_px = int(round((self.w - 1) * np.clip(tip_anchor_x, 0.0, 1.0)))
        self.tip_py = int(round((self.h - 1) * np.clip(tip_anchor_y, 0.0, 1.0)))

    def stamp(self, canvas: np.ndarray, x: int, y: int) -> np.ndarray:
        """Căn ngòi bút của ảnh bàn tay trùng với tọa độ canvas (x, y) (điểm hạ mực)."""
        # Góc trên trái ảnh = Điểm hạ mực - Độ lệch ngòi bút
        anchor_x = x - self.tip_px
        anchor_y = y - self.tip_py
        h_canvas, w_canvas = canvas.shape[:2]

        x0 = max(0, anchor_x)
        y0 = max(0, anchor_y)
        x1 = min(w_canvas, anchor_x + self.w)
        y1 = min(h_canvas, anchor_y + self.h)
        if x1 <= x0 or y1 <= y0:
            return canvas

        sx0 = x0 - anchor_x
        sy0 = y0 - anchor_y
        sx1 = sx0 + (x1 - x0)
        sy1 = sy0 + (y1 - y0)

        region = canvas[y0:y1, x0:x1]
        hand_region = self.hand[sy0:sy1, sx0:sx1]
        mask_region = self.mask[sy0:sy1, sx0:sx1]
        inv_region = self.mask_inv[sy0:sy1, sx0:sx1]

        for c in range(3):
            region[:, :, c] = (
                region[:, :, c] * inv_region + hand_region[:, :, c] * mask_region
            )
        canvas[y0:y1, x0:x1] = region
        return canvas


# ──────────────────────────────────────────────────────────────
# Cọ mực
# ──────────────────────────────────────────────────────────────
def _feathered_disk(radius: int) -> np.ndarray:
    """Tạo mặt nạ tròn bán kính r, làm mờ viền Gaussian, giá trị 0..1."""
    y, x = np.ogrid[-radius:radius + 1, -radius:radius + 1]
    dist = np.sqrt(x * x + y * y).astype(np.float32)
    return np.clip(1.0 - (dist - radius * 0.75) / (radius * 0.25), 0.0, 1.0)


# ──────────────────────────────────────────────────────────────
# Công cụ tô màu contour-wipe
# ──────────────────────────────────────────────────────────────
def _ease_in_out_sine(t: float | np.ndarray) -> float | np.ndarray:
    """Ease-in-out dạng sin: Bắt đầu/kết thúc chậm, ở giữa nhanh."""
    return -(np.cos(np.pi * t) - 1.0) / 2.0


def _build_wipe_wave(width: int) -> np.ndarray:
    """
    Tính trước biên sóng sin kép giúp đường ranh giới tô màu nhấp nhô như sóng nước thay vì đường thẳng phẳng.
    """
    wave_px1 = max(24.0, width / 20.0)
    wave_px2 = max(8.0, width / 72.0)
    xs = np.arange(width, dtype=np.float32)
    return np.sin(xs / wave_px1) + 0.35 * np.sin(xs / wave_px2 + 1.7)


# ──────────────────────────────────────────────────────────────
# Dò nét theo khung xương (thuật toán Zhang-Suen + dò cạnh thẳng nhất 8 hướng)
# ──────────────────────────────────────────────────────────────
_SKEL_NEIGHBORS_8 = [
    (-1, -1), (0, -1), (1, -1),
    (-1, 0),           (1, 0),
    (-1, 1),  (0, 1),  (1, 1),
]


def _zhang_suen_skeleton(mask: np.ndarray, max_iterations: int = 160) -> np.ndarray:
    """
    Thuật toán làm mảnh Zhang-Suen 2 bước lặp, rút gọn mặt nạ tiền cảnh về khung xương rộng 1px.
    """
    img = np.pad(mask.astype(np.uint8), 1, mode="constant")
    for _ in range(max_iterations):
        changed = False
        for step in (0, 1):
            p2, p3, p4 = img[:-2, 1:-1], img[:-2, 2:], img[1:-1, 2:]
            p5, p6, p7 = img[2:, 2:], img[2:, 1:-1], img[2:, :-2]
            p8, p9 = img[1:-1, :-2], img[:-2, :-2]
            center = img[1:-1, 1:-1]
            neighbors = [p2, p3, p4, p5, p6, p7, p8, p9]
            # Số lần chuyển đổi 0->1 theo chiều kim đồng hồ
            transitions = sum(
                (neighbors[i] == 0) & (neighbors[(i + 1) % 8] == 1) for i in range(8)
            )
            count = sum(neighbors)
            if step == 0:
                marker = (
                    (center == 1) & (count >= 2) & (count <= 6)
                    & (transitions == 1)
                    & ((p2 * p4 * p6) == 0) & ((p4 * p6 * p8) == 0)
                )
            else:
                marker = (
                    (center == 1) & (count >= 2) & (count <= 6)
                    & (transitions == 1)
                    & ((p2 * p4 * p8) == 0) & ((p2 * p6 * p8) == 0)
                )
            if np.any(marker):
                center[marker] = 0
                changed = True
        if not changed:
            break
    return img[1:-1, 1:-1].astype(bool)


def _skel_neighbors(skel: np.ndarray, point: tuple[int, int]) -> list[tuple[int, int]]:
    """
    Trả về các điểm lân cận 8 hướng hợp lệ của điểm khung xương, bỏ qua các điểm chéo dư thừa.
    """
    x, y = point
    h, w = skel.shape
    result: list[tuple[int, int]] = []
    for dx, dy in _SKEL_NEIGHBORS_8:
        nx, ny = x + dx, y + dy
        if not (0 <= nx < w and 0 <= ny < h and skel[ny, nx]):
            continue
        if dx != 0 and dy != 0 and (skel[y, nx] or skel[ny, x]):
            continue  # Đã có cầu nối trực giao, bỏ qua đường chéo dư
        result.append((nx, ny))
    return result


def _edge_key(a: tuple[int, int], b: tuple[int, int]) -> tuple[tuple[int, int], tuple[int, int]]:
    """Chuẩn hóa cạnh vô hướng: (A,B) và (B,A) map về cùng một key."""
    return (a, b) if a <= b else (b, a)


def _choose_next(
    prev: tuple[int, int],
    cur: tuple[int, int],
    candidates: list[tuple[int, int]],
    visited_edges: set,
) -> tuple[int, int] | None:
    """
    Tại giao điểm, chọn cạnh thẳng nhất chưa thăm dựa vào độ tương đồng cosine.
    """
    fresh = [p for p in candidates if _edge_key(cur, p) not in visited_edges and p != prev]
    if not fresh:
        return None
    vx, vy = cur[0] - prev[0], cur[1] - prev[1]
    vlen = math.hypot(vx, vy)
    return max(
        fresh,
        key=lambda p: (
            (vx * (p[0] - cur[0]) + vy * (p[1] - cur[1]))
            / (vlen * math.hypot(p[0] - cur[0], p[1] - cur[1]) or 1.0)
        ),
    )


def trace_8connected(skel: np.ndarray, min_points: int = 8) -> list[list[tuple[int, int]]]:
    """
    Dò khung xương 1px thành chuỗi nét vẽ có thứ tự.
    """
    ys, xs = np.nonzero(skel)
    points = [(int(x), int(y)) for x, y in zip(xs, ys)]
    if not points:
        return []
    degrees = {p: len(_skel_neighbors(skel, p)) for p in points}
    starts = (
        [p for p in points if degrees[p] == 1]
        + [p for p in points if degrees[p] > 2]
        + points
    )
    visited_edges: set = set()
    strokes: list[list[tuple[int, int]]] = []
    for start in starts:
        for nb in _skel_neighbors(skel, start):
            edge = _edge_key(start, nb)
            if edge in visited_edges:
                continue
            path = [start]
            prev, cur = start, nb
            visited_edges.add(edge)
            while True:
                path.append(cur)
                next_pt = _choose_next(prev, cur, _skel_neighbors(skel, cur), visited_edges)
                if next_pt is None:
                    break
                visited_edges.add(_edge_key(cur, next_pt))
                prev, cur = cur, next_pt
            if len(path) >= min_points:
                strokes.append(path)
    return strokes


# ── Hậu xử lý nét khung xương (lấy mẫu lại + làm mịn + sắp xếp) ──
def _stroke_cumulative_length(points: list[tuple[float, float]]) -> list[float]:
    """Độ dài cung tích lũy của từng điểm."""
    cum = [0.0]
    for a, b in zip(points, points[1:]):
        cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    return cum


def _resample_stroke_points(
    points: list[tuple[float, float]], spacing: float
) -> list[tuple[float, float]]:
    """Lấy mẫu đều theo khoảng cách spacing để khử răng cưa pixel."""
    if len(points) < 2:
        return list(points)
    cum = _stroke_cumulative_length(points)
    total = cum[-1]
    if total < spacing:
        return [points[0], points[-1]]
    n = max(2, int(round(total / spacing)))
    result: list[tuple[float, float]] = []
    for i in range(n + 1):
        target = total * i / n
        # Tìm kiếm nhị phân
        lo, hi = 0, len(cum) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if cum[mid] < target:
                lo = mid + 1
            else:
                hi = mid
        if lo == 0:
            result.append(points[0])
            continue
        seg_start = cum[lo - 1]
        seg_len = cum[lo] - seg_start
        t = (target - seg_start) / seg_len if seg_len > 0 else 0.0
        ax, ay = points[lo - 1]
        bx, by = points[lo]
        result.append((ax + (bx - ax) * t, ay + (by - ay) * t))
    return result


def _chaikin_smooth(
    points: list[tuple[float, float]], iterations: int = 1
) -> list[tuple[float, float]]:
    """Làm mịn góc Chaikin: Thay thế mỗi đoạn bằng 2 điểm 0.25/0.75, giữ nguyên đầu và cuối."""
    pts = list(points)
    for _ in range(iterations):
        if len(pts) < 3:
            break
        smoothed = [pts[0]]
        for a, b in zip(pts, pts[1:]):
            smoothed.append((a[0] * 0.75 + b[0] * 0.25, a[1] * 0.75 + b[1] * 0.25))
            smoothed.append((a[0] * 0.25 + b[0] * 0.75, a[1] * 0.25 + b[1] * 0.75))
        smoothed.append(pts[-1])
        pts = smoothed
    return pts


def _order_skeleton_strokes(strokes: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    """
    Sắp xếp nét vẽ: Từ trên xuống dưới, từ trái sang phải, ưu tiên nét dài.
    """
    def sort_key(s):
        if not s:
            return (0, 0, 0, 0)
        xs = [p[0] for p in s]
        ys = [p[1] for p in s]
        length = _stroke_cumulative_length(s)[-1]
        return (min(ys) // 12, min(xs), min(ys), -length)
    return sorted(strokes, key=sort_key)


# ──────────────────────────────────────────────────────────────
# Phân chia thời lượng / giai đoạn
# ──────────────────────────────────────────────────────────────
@dataclass
class PhasePlan:
    ink_frames: int
    color_frames: int
    gaze_frames: int
    ratio_label: str


def plan_phases(total_ms: int, cfg: Config) -> PhasePlan:
    """
    Chia tổng thời lượng thành 3 giai đoạn: Đi nét / Tô màu / Dừng xem.
    """
    weight_sum = cfg.ink_weight + cfg.color_weight
    gaze_ms = int(cfg.gaze_seconds * 1000)
    anim_ms = total_ms - gaze_ms
    remainder = anim_ms % weight_sum
    if remainder:
        anim_ms -= remainder
        gaze_ms += remainder

    ink_frames = round(anim_ms * cfg.ink_weight / weight_sum * cfg.fps / 1000)
    color_frames = round(anim_ms * cfg.color_weight / weight_sum * cfg.fps / 1000)
    gaze_frames = round(gaze_ms * cfg.fps / 1000)
    if ink_frames <= 0 and color_frames <= 0:
        ink_frames = color_frames = 0
    return PhasePlan(ink_frames, color_frames, gaze_frames, f"{cfg.ink_weight}:{cfg.color_weight}")


# ──────────────────────────────────────────────────────────────
# Thân bộ render chính
# ──────────────────────────────────────────────────────────────
class StreamBoardRenderer:
    """Nắm giữ toàn bộ trạng thái của một lần render."""

    def __init__(
        self,
        image_bgr: np.ndarray,
        cfg: Config,
        hand_png: Path | None,
        bare_tip: bool,
    ) -> None:
        self.cfg = cfg
        self.canvas_bgr = _hex_to_bgr(cfg.canvas_hex)

        # Tính kích thước xuất: Giới hạn cạnh dài theo cap, căn theo bội số chẵn của grid_edge
        h0, w0 = image_bgr.shape[:2]
        scale = cfg.cap_long_edge / max(h0, w0)
        w = int(round(w0 * scale))
        h = int(round(h0 * scale))
        align = cfg.grid_edge if cfg.grid_edge % 2 == 0 else cfg.grid_edge * 2
        w = (w // align) * align
        h = (h // align) * align
        self.out_w = max(align, w)
        self.out_h = max(align, h)

        self.color_img = cv2.resize(image_bgr, (self.out_w, self.out_h), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(self.color_img, cv2.COLOR_BGR2GRAY)
        self.thresh_map = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 10
        )
        self.active = _active_mask(self.thresh_map, cfg.grid_edge, cfg.ink_threshold)
        self.grid_blocks = _to_grid_blocks(self.thresh_map, cfg.grid_edge)
        self.ink_pixels = self.thresh_map < cfg.ink_threshold
        self.ink_paint = np.repeat(self.thresh_map[:, :, None], 3, axis=2).astype(np.float32)

        # Nhuộm nền ảnh gốc thành màu canvas để đồng bộ màu nền, không ảnh hưởng chất lượng nét vẽ.
        if cfg.match_bg:
            self._match_original_background()

        # Phân cụm không gian ô lưới
        self.ink_streams = cluster_ink_streams(self.active)

        # Đường nét vẽ: Chọn grid (tâm ô lưới) hoặc skeleton (dò khung xương) theo ink_path_mode
        if cfg.ink_path_mode == "skeleton":
            self.skeleton_strokes = self._build_skeleton_path()
            if self.skeleton_strokes:
                self.stroke_path = [pt for stroke in self.skeleton_strokes for pt in stroke]
            else:
                # Nếu không dò được khung xương, quay về đường dẫn tâm ô
                self.stroke_path = flatten_streams(self.ink_streams)
        else:
            self.skeleton_strokes = []
            self.stroke_path = flatten_streams(self.ink_streams)

        # Canvas (dùng bộ đệm số thực để hòa trộn cọ mực)
        self.drawn = np.zeros((self.out_h, self.out_w, 3), dtype=np.float32)
        self.drawn[...] = self.canvas_bgr.astype(np.float32)

        # Phủ đầu bút
        self.tip: TipOverlay | None = None
        if not bare_tip:
            hand_data = _load_hand(hand_png, cfg.target_hand_height) if hand_png else None
            tip_anchor_x = cfg.tip_anchor_x
            tip_anchor_y = cfg.tip_anchor_y
            if hand_data is None:
                hand_data = _procedural_tip(cfg.target_hand_height)
                tip_anchor_x = 0.5
                tip_anchor_y = 0.70
            self.tip = TipOverlay(
                hand_data[0], hand_data[1],
                tip_anchor_x=tip_anchor_x,
                tip_anchor_y=tip_anchor_y,
            )

    # ── Nhuộm nền ảnh gốc thành màu nền canvas ──
    def _match_original_background(self) -> None:
        """
        Lấy mẫu 4 góc ảnh gốc làm màu nền chuẩn, thay các pixel gần màu nền bằng canvas_hex để đồng nhất.
        """
        img = self.color_img
        h, w = img.shape[:2]
        margin = max(3, min(h, w) // 50)
        samples = [
            img[:margin, :margin], img[:margin, -margin:],
            img[-margin:, :margin], img[-margin:, -margin:],
        ]
        bg_color = np.median(np.concatenate([s.reshape(-1, 3) for s in samples]), axis=0)
        diff = np.abs(img.astype(np.int16) - bg_color.astype(np.int16)).sum(axis=2)
        bg_mask = diff < self.cfg.match_bg_threshold
        img[bg_mask] = self.canvas_bgr

    # ── Tọa độ pixel tâm nét vẽ ──
    def _cell_center(self, cell: tuple[int, int]) -> tuple[int, int]:
        r, c = cell
        e = self.cfg.grid_edge
        return (c * e + e // 2, r * e + e // 2)  # (x, y)

    # ── Đường nét khung xương (thuật toán Zhang-Suen + dò cạnh thẳng nhất) ──
    def _build_skeleton_path(self) -> list[list[tuple[int, int]]]:
        """
        Dò khung xương tạo chuỗi nét vẽ mức pixel, giúp đầu bút bám sát nét vẽ thật.
        """
        cfg = self.cfg
        skel = _zhang_suen_skeleton(self.ink_pixels, max_iterations=160)
        raw_strokes = trace_8connected(skel, min_points=cfg.skeleton_min_points)
        if not raw_strokes:
            print("  [warn] Không có nét khung xương, quay lại đường dẫn tâm ô")
            return []

        spacing = cfg.skeleton_resample_spacing
        processed: list[list[tuple[int, int]]] = []
        for stroke in raw_strokes:
            pts = [(float(x), float(y)) for x, y in stroke]
            pts = _resample_stroke_points(pts, spacing)
            pts = _chaikin_smooth(pts, iterations=1)
            pts = _resample_stroke_points(pts, spacing)
            if len(pts) >= 2 and _stroke_cumulative_length(pts)[-1] > 2.0:
                processed.append([(int(round(x)), int(round(y))) for x, y in pts])

        processed = _order_skeleton_strokes(processed)
        total_pts = sum(len(s) for s in processed)
        print(f"  Dò khung xương: {len(processed)} nét, {total_pts} điểm mẫu")
        return processed

    # ── Trường cản contour-wipe (tính toán lười, tái sử dụng cho cả giai đoạn tô màu) ──
    def _build_resistance_field(self) -> np.ndarray:
        """
        Dùng nét mực để dựng "trường cản": Tại viền cản ≈ 1, hướng xuống dưới suy giảm theo decay.
        Đường biên lộ diện gặp cản cao sẽ bị giữ lại số pixel, tạo hiệu ứng "bị khựng lại ở đường viền rồi từ từ tràn qua".
        """
        if getattr(self, "_resistance", None) is not None:
            return self._resistance

        h, w = self.out_h, self.out_w
        cfg = self.cfg

        # 1) Nhị phân hóa nét mực (uint8 0/255)
        ink_u8 = (self.ink_pixels.astype(np.uint8)) * 255

        # 2) Giãn nở (dilate): Phần tử hình elip làm dày đường viền tạo dải cản
        spread = int(np.clip(min(w, h) // 64, 3, 17))
        if spread % 2 == 0:
            spread = max(3, spread - 1)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (spread, spread))
        dilated = cv2.dilate(ink_u8, kernel, iterations=1)

        # 3) Làm mờ Gaussian: Biến cạnh cứng thành dải chuyển tiếp mềm
        blur_r = max(1, int(round(min(w, h) / 220.0)))
        if blur_r % 2 == 0:
            blur_r += 1
        resistance = cv2.GaussianBlur(dilated, (blur_r, blur_r), 0).astype(np.float32)

        # 4) Chuẩn hóa về [0,1]
        peak = float(resistance.max())
        if peak > 1e-6:
            resistance /= peak
        else:
            # Không có nét mực (ảnh trắng): Trường cản bằng 0
            resistance = np.zeros((h, w), dtype=np.float32)

        # 5) Lan truyền suy giảm decay theo hàng xuống dưới
        decay = cfg.wipe_decay
        for row in range(1, h):
            resistance[row] = np.maximum(resistance[row], resistance[row - 1] * decay)

        self._resistance = resistance
        return resistance

    # ── Hạ điểm mực tại vị trí rơi: Đi nét hạ ảnh ngưỡng, tô màu hạ màu gốc ──
    def _reveal_ink_segment(
        self, start: tuple[int, int], end: tuple[int, int]
    ) -> None:
        """Chỉ hiển thị các pixel nét vẽ gốc được chạm bởi một cử động bút."""
        segment = np.zeros((self.out_h, self.out_w), dtype=np.uint8)
        thickness = max(1, self.cfg.ink_reveal_radius * 2 + 1)
        cv2.line(segment, start, end, 255, thickness=thickness, lineType=cv2.LINE_AA)
        revealed = (segment > 0) & self.ink_pixels
        self.drawn[revealed] = self.ink_paint[revealed]

    def _ink_stamp(self, cell: tuple[int, int]) -> None:
        r, c = cell
        e = self.cfg.grid_edge
        block = self.grid_blocks[r, c]
        ink_region = block < self.cfg.ink_threshold
        paint = np.repeat(block[:, :, None], 3, axis=2)
        target = self.drawn[r * e:r * e + e, c * e:c * e + e]
        target[ink_region] = paint[ink_region]

    def _color_stamp(self, px: int, py: int, disk: np.ndarray) -> None:
        radius = self.cfg.brush_radius
        h, w = self.out_h, self.out_w
        y0, y1 = max(0, py - radius), min(h, py + radius + 1)
        x0, x1 = max(0, px - radius), min(w, px + radius + 1)
        if y1 <= y0 or x1 <= x0:
            return
        by0, by1 = y0 - (py - radius), disk.shape[0] - ((py + radius + 1) - y1)
        bx0, bx1 = x0 - (px - radius), disk.shape[1] - ((px + radius + 1) - x1)
        m = disk[by0:by1, bx0:bx1]
        inv = 1.0 - m
        target = self.drawn[y0:y1, x0:x1]
        source = self.color_img[y0:y1, x0:x1].astype(np.float32)
        for ch in range(3):
            target[:, :, ch] = target[:, :, ch] * inv + source[:, :, ch] * m

    # ── Ghi vài khung hình ảnh chụp canvas hiện tại (kèm đầu bút) ──
    def _snapshot_with_tip(self, px: int, py: int) -> np.ndarray:
        snap = self.drawn.astype(np.uint8)
        if self.tip is not None:
            self.tip.stamp(snap, px, py)
        return snap

    def _build_stroke_samples(
        self, path: list[tuple[int, int]]
    ) -> tuple[list[tuple[int, int]], set[int], list[int]]:
        """
        Nội suy đường gấp khúc thành chuỗi tọa độ pixel liên tục của đầu bút.
        Giữa tâm các ô kề nhau lấy mẫu đều theo sample_step tạo quỹ đạo trượt mượt mà.
        """
        samples: list[tuple[int, int]] = []
        pen_lifts: set[int] = set()
        sample_cell_index: list[int] = []
        for idx, cell in enumerate(path):
            cx, cy = self._cell_center(cell)
            if idx == 0:
                samples.append((cx, cy))
                sample_cell_index.append(idx)
                continue
            prev_cell = path[idx - 1]
            prev = self._cell_center(prev_cell)
            cell_distance = math.hypot(cell[0] - prev_cell[0], cell[1] - prev_cell[1])
            if cell_distance > math.sqrt(2):
                pen_lifts.add(len(samples))
                samples.append((cx, cy))
                sample_cell_index.append(idx)
                continue
            steps = max(
                1, int(math.hypot(cx - prev[0], cy - prev[1]) / self.cfg.sample_step)
            )
            for s in range(1, steps + 1):
                samples.append(
                    (int(prev[0] + (cx - prev[0]) * s / steps),
                     int(prev[1] + (cy - prev[1]) * s / steps))
                )
                sample_cell_index.append(idx)
        return samples, pen_lifts, sample_cell_index

    def _frame_progress_indices(self, n_steps: int, target_frames: int) -> list[int]:
        """Ánh xạ n_steps vị trí đầu bút vào target_frames khung hình."""
        if n_steps == 0 or target_frames <= 0:
            return []
        if target_frames == 1:
            return [n_steps - 1]
        return [
            round(f * (n_steps - 1) / (target_frames - 1))
            for f in range(target_frames)
        ]

    def _pause_frame_indices(
        self, target_frames: int, n_cells: int
    ) -> set[int]:
        """Tự động tính toán các khung hình tạm dừng thích ứng để tạo nhịp thở khi viết."""
        mode = self.cfg.pause_mode
        if mode == "off" or target_frames < 8 or n_cells <= 0:
            return set()

        if mode == "light":
            ratio = self.cfg.pause_ratio_light
        elif mode == "heavy":
            ratio = self.cfg.pause_ratio_heavy
        else:
            fpc = target_frames / n_cells
            if fpc >= self.cfg.pause_heavy_fpc:
                ratio = self.cfg.pause_ratio_heavy
            elif fpc >= self.cfg.pause_light_fpc:
                ratio = self.cfg.pause_ratio_light
            else:
                return set()

        pause_count = min(
            max(0, int(round(target_frames * ratio))),
            max(0, target_frames - 2),
        )
        if pause_count <= 0:
            return set()

        return {
            max(1, min(target_frames - 2,
                       round((idx + 1) * target_frames / (pause_count + 1))))
            for idx in range(pause_count)
        }

    # ── Giai đoạn đi nét: Đi theo stroke_path, đầu bút trượt đồng bộ với lộ diện mực ──
    def lay_down_ink(self, writer: cv2.VideoWriter, target_frames: int) -> None:
        """Giai đoạn đi nét: Phân bổ tới dò khung xương hoặc đường lưới."""
        if self.cfg.ink_path_mode == "skeleton" and self.skeleton_strokes:
            return self._lay_down_ink_skeleton(writer, target_frames)
        return self._lay_down_ink_grid(writer, target_frames)

    # ── Chế độ grid: Đi nét theo tâm các ô lưới ──
    def _lay_down_ink_grid(self, writer: cv2.VideoWriter, target_frames: int) -> None:
        path = self.stroke_path
        n = len(path)
        if n == 0:
            print("  Không có nét mực, bỏ qua giai đoạn đi nét")
            for _ in range(target_frames):
                writer.write(self._snapshot_with_tip(self.out_w // 2, self.out_h // 2))
            return

        samples, pen_lifts, sample_cell_index = self._build_stroke_samples(path)
        sample_idx_for_frame = self._frame_progress_indices(len(samples), target_frames)

        pause_frames = self._pause_frame_indices(target_frames, n)
        if pause_frames:
            print(f"  Tạm dừng thích ứng: {len(pause_frames)} khung hình đóng băng (chế độ={self.cfg.pause_mode})")

        written = 0
        cells_revealed = 0
        last_sample_idx: int | None = None
        for fi, si in enumerate(sample_idx_for_frame):
            if fi in pause_frames and last_sample_idx is not None:
                sx, sy = samples[last_sample_idx]
                writer.write(self._snapshot_with_tip(sx, sy))
                written += 1
                if (fi + 1) % max(1, target_frames // 10) == 0:
                    print(f"  Tiến độ đi nét: {int((fi + 1) / target_frames * 100)}%")
                continue

            if last_sample_idx is None:
                self._reveal_ink_segment(samples[si], samples[si])
            else:
                for sample_idx in range(last_sample_idx + 1, si + 1):
                    if sample_idx in pen_lifts:
                        continue
                    self._reveal_ink_segment(
                        samples[sample_idx - 1], samples[sample_idx]
                    )

            target_cell = sample_cell_index[si]
            while cells_revealed <= target_cell and cells_revealed < n:
                self._ink_stamp(path[cells_revealed])
                cells_revealed += 1

            sx, sy = samples[si]
            writer.write(self._snapshot_with_tip(sx, sy))
            written += 1
            last_sample_idx = si
            if (fi + 1) % max(1, target_frames // 10) == 0:
                print(f"  Tiến độ đi nét: {int((fi + 1) / target_frames * 100)}%")

        while cells_revealed < n:
            self._ink_stamp(path[cells_revealed])
            cells_revealed += 1
        last = samples[-1]
        while written < target_frames:
            writer.write(self._snapshot_with_tip(*last))
            written += 1
        print(f"  Đi nét hoàn thành: {n} ô, {written} khung hình")

    # ── Chế độ skeleton: Đi nét theo pixel khung xương thật ──
    def _lay_down_ink_skeleton(self, writer: cv2.VideoWriter, target_frames: int) -> None:
        """Đi nét theo khung xương mức pixel."""
        strokes = self.skeleton_strokes
        if not strokes:
            return self._lay_down_ink_grid(writer, target_frames)

        samples: list[tuple[int, int]] = []
        pen_lifts: set[int] = set()
        for si, stroke in enumerate(strokes):
            if si > 0:
                pen_lifts.add(len(samples))
            samples.extend(stroke)

        n = len(samples)
        if n == 0:
            print("  Không có nét khung xương, bỏ qua giai đoạn đi nét")
            for _ in range(target_frames):
                writer.write(self._snapshot_with_tip(self.out_w // 2, self.out_h // 2))
            return

        sample_idx_for_frame = self._frame_progress_indices(n, target_frames)

        pause_frames = self._pause_frame_indices(target_frames, len(strokes))
        if pause_frames:
            print(f"  Tạm dừng thích ứng: {len(pause_frames)} khung hình đóng băng (chế độ={self.cfg.pause_mode})")

        written = 0
        last_sample_idx: int | None = None
        report_step = max(1, target_frames // 10)
        for fi, si in enumerate(sample_idx_for_frame):
            if fi in pause_frames and last_sample_idx is not None:
                sx, sy = samples[last_sample_idx]
                writer.write(self._snapshot_with_tip(sx, sy))
                written += 1
                if (fi + 1) % report_step == 0:
                    print(f"  Tiến độ đi nét: {int((fi + 1) / target_frames * 100)}%")
                continue

            if last_sample_idx is None:
                self._reveal_ink_segment(samples[si], samples[si])
            else:
                for idx in range(last_sample_idx + 1, si + 1):
                    if idx in pen_lifts:
                        continue
                    self._reveal_ink_segment(samples[idx - 1], samples[idx])

            sx, sy = samples[si]
            writer.write(self._snapshot_with_tip(sx, sy))
            written += 1
            last_sample_idx = si
            if (fi + 1) % report_step == 0:
                print(f"  Tiến độ đi nét: {int((fi + 1) / target_frames * 100)}%")

        last = samples[-1]
        while written < target_frames:
            writer.write(self._snapshot_with_tip(*last))
            written += 1
        print(f"  Đi nét hoàn thành (khung xương): {n} điểm mẫu, {written} khung hình")

    # ── Giai đoạn tô màu: Phân phối theo color_fill ──
    def wash_color(self, writer: cv2.VideoWriter, target_frames: int) -> None:
        if self.cfg.color_fill == "contour-wipe":
            return self.wash_color_contour(writer, target_frames)
        return self.wash_color_brush(writer, target_frames)

    # ── Chế độ brush: Dùng cọ tròn phủ màu gốc theo nét ──
    def wash_color_brush(self, writer: cv2.VideoWriter, target_frames: int) -> None:
        path = self.stroke_path
        n = len(path)
        disk = _feathered_disk(self.cfg.brush_radius)
        if n == 0:
            print("  Không có nét mực, bỏ qua giai đoạn tô màu")
            gaze = self.color_img
            for _ in range(target_frames):
                writer.write(gaze)
            return

        centers = [self._cell_center(cell) for cell in path]
        cell_idx_for_frame = self._frame_progress_indices(n, target_frames)

        written = 0
        last_cell_idx: int | None = None
        for fi, ci in enumerate(cell_idx_for_frame):
            if last_cell_idx is None:
                self._color_stamp(*centers[ci], disk)
            else:
                for cell_idx in range(last_cell_idx + 1, ci + 1):
                    self._color_stamp(*centers[cell_idx], disk)

            cx, cy = centers[ci]
            writer.write(self._snapshot_with_tip(cx, cy))
            written += 1
            last_cell_idx = ci
            if (fi + 1) % max(1, target_frames // 10) == 0:
                print(f"  Tiến độ tô màu: {int((fi + 1) / target_frames * 100)}%")

        last = centers[-1]
        while written < target_frames:
            writer.write(self._snapshot_with_tip(*last))
            written += 1
        print(f"  Tô màu hoàn thành: {n} ô, {written} khung hình")

    # ── Chế độ contour-wipe: Quét viền tự động từ trên xuống ──
    def wash_color_contour(self, writer: cv2.VideoWriter, target_frames: int) -> None:
        cfg = self.cfg
        h, w = self.out_h, self.out_w

        if target_frames <= 0:
            print("  Không có khung hình tô màu, bỏ qua giai đoạn contour-wipe")
            return

        resistance = self._build_resistance_field()
        wave = _build_wipe_wave(w)
        delay_px = int(np.clip(h * cfg.wipe_delay_ratio, 12, 52))
        blocks = max(1, cfg.wipe_blocks)
        ys = np.arange(h, dtype=np.float32)[:, None]

        color_src = self.color_img.astype(np.float32)

        print(f"  contour-wipe: {w}x{h}, delay_px={delay_px}, số lượt quét={blocks}")

        written = 0
        sweep = h + 2 * delay_px
        report_step = max(1, target_frames // 10)

        for fi in range(target_frames):
            if target_frames == 1:
                progress = 1.0
            else:
                progress = fi / (target_frames - 1)
            lead = _ease_in_out_sine(progress) * sweep - delay_px

            threshold = lead + wave[None, :] - resistance * delay_px
            reveal = ys <= threshold

            self.drawn[reveal] = color_src[reveal]

            lane = (fi / blocks * 2.0) % 1.0
            lane = _ease_in_out_sine(lane)
            forward = (int(fi // blocks) % 2 == 0)
            cursor_x = int(lane * w) if forward else int((1.0 - lane) * w)
            cursor_x = max(0, min(w - 1, cursor_x))

            col_revealed = np.where(reveal[:, cursor_x])[0]
            cursor_y = int(col_revealed[-1]) if col_revealed.size > 0 else 0

            writer.write(self._snapshot_with_tip(cursor_x, cursor_y))
            written += 1
            if (fi + 1) % report_step == 0:
                print(f"  Tiến độ tô màu (contour-wipe): {int((fi + 1) / target_frames * 100)}%")

        full_reveal = np.ones((h, w), dtype=bool)
        self.drawn[full_reveal] = color_src[full_reveal]
        last = self._snapshot_with_tip(w // 2, h - 1)
        while written < target_frames:
            writer.write(last)
            written += 1
        print(f"  contour-wipe hoàn thành: {written} khung hình")

    def render_to(self, raw_path: Path, total_ms: int) -> Path:
        cfg = self.cfg
        plan = plan_phases(total_ms, cfg)
        ink_cells = len(self.stroke_path)

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(raw_path), fourcc, cfg.fps, (self.out_w, self.out_h))

        print(f"  Dòng mực: {len(self.ink_streams)} luồng, ô mực: {ink_cells}")
        print(
            f"  Thời lượng: {total_ms}ms -> Đi nét {plan.ink_frames}f / "
            f"Tô màu {plan.color_frames}f / Dừng xem {plan.gaze_frames}f (trọng số {plan.ratio_label})"
        )

        started = time.time()
        self.lay_down_ink(writer, plan.ink_frames)
        self.wash_color(writer, plan.color_frames)
        gaze_img = self.color_img
        for _ in range(plan.gaze_frames):
            writer.write(gaze_img)
        writer.release()
        print(f"  Thời gian render: {time.time() - started:.1f}s")
        return raw_path


# ──────────────────────────────────────────────────────────────
# Chuyển mã (ưu tiên ffmpeg hệ thống, PyAV dự phòng)
# ──────────────────────────────────────────────────────────────
def transcode_h264(src: Path, dst: Path) -> Path:
    """
    Chuyển mã video mp4v gốc sang H.264 (yuv420p) để tăng tính tương thích.
    Ưu tiên:
      1. ffmpeg hệ thống (tối ưu nhất, CRF=20)
      2. PyAV (dự phòng qua pip, CRF=28)
      3. Cả hai đều không có: Giữ nguyên mã hóa mp4v ban đầu và đưa ra cảnh báo
    """
    # Cách 1: ffmpeg hệ thống (Khuyến nghị, dung lượng tối ưu)
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is not None:
        cmd = [
            ffmpeg, "-y", "-loglevel", "error",
            "-i", str(src),
            "-c:v", "libx264",
            "-crf", "20",
            "-pix_fmt", "yuv420p",
            str(dst),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            src.unlink(missing_ok=True)
            print(f"  Chuyển mã H.264 hoàn tất (ffmpeg): {dst}")
            return dst
        print(f"  [warn] ffmpeg chuyển mã thất bại: {res.stderr.strip()}")

    # Cách 2: PyAV (Dự phòng qua pip)
    try:
        return _transcode_with_pyav(src, dst)
    except ImportError:
        pass
    except Exception as e:
        print(f"  [warn] PyAV chuyển mã thất bại: {e}")

    # Cách 3: Không có cả hai, giữ nguyên mp4v
    print(f"  [warn] Không tìm thấy ffmpeg và PyAV, giữ nguyên mã hóa mp4v gốc: {src}")
    print(f"         Cài đặt một trong hai để có H.264: pip install av  hoặc  cài đặt ffmpeg hệ thống")
    return src


def _transcode_with_pyav(src: Path, dst: Path) -> Path:
    """
    Dùng PyAV chuyển mã H.264 trong Python.
    """
    import av
    input_container = av.open(str(src), mode="r")
    if not input_container.streams.video:
        input_container.close()
        return src
    in_stream = input_container.streams.video[0]
    width = in_stream.codec_context.width
    height = in_stream.codec_context.height
    fps = in_stream.average_rate or in_stream.guessed_rate or 30

    output_container = av.open(str(dst), mode="w")
    out_stream = output_container.add_stream("h264", rate=fps)
    out_stream.width = width
    out_stream.height = height
    out_stream.pix_fmt = "yuv420p"
    out_stream.options = {"crf": "28", "preset": "medium"}

    pts_counter = 0
    for frame in input_container.decode(video=0):
        frame.pts = pts_counter
        pts_counter += 1
        for packet in out_stream.encode(frame):
            output_container.mux(packet)
    # flush
    for packet in out_stream.encode(None):
        output_container.mux(packet)

    output_container.close()
    input_container.close()
    src.unlink(missing_ok=True)
    print(f"  Chuyển mã H.264 hoàn tất (PyAV): {dst}")
    return dst


# ──────────────────────────────────────────────────────────────
# Giao diện dòng lệnh (CLI)
# ──────────────────────────────────────────────────────────────
def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Render một bức ảnh thành video hoạt hình bảng trắng vẽ tay"
    )
    p.add_argument("image", help="Đường dẫn ảnh đầu vào (PNG/JPG/JPEG/BMP/TIFF)")
    p.add_argument("--out-dir", default="./out", help="Thư mục xuất kết quả (mặc định: ./out)")
    p.add_argument("--total-ms", type=int, default=10000, help="Tổng thời lượng video (mili-giây, mặc định: 10000)")
    p.add_argument("--bare-tip", action="store_true", help="Không vẽ đè bàn tay / ngòi bút")
    p.add_argument(
        "--pen-image", default=str(DEFAULT_HAND_PNG),
        help="Đường dẫn ảnh ngòi bút / bàn tay tùy biến (mặc định: drawing-hand.png tích hợp sẵn)",
    )
    p.add_argument("--fps", type=int, default=None, help="Ghi đè tốc độ khung hình mặc định")
    p.add_argument("--grid-edge", type=int, default=None, help="Ghi đè kích thước cạnh lưới mặc định")
    p.add_argument("--brush-radius", type=int, default=None, help="Ghi đè bán kính cọ vẽ mặc định")
    p.add_argument(
        "--color-fill", default="contour-wipe", choices=["brush", "contour-wipe"],
        help="Phong cách tô màu: contour-wipe quét viền từ trên xuống (mặc định); brush quét theo nét vẽ",
    )
    p.add_argument(
        "--wipe-decay", type=float, default=None,
        help="contour-wipe: Hệ số suy giảm trường cản xuống dưới (mặc định 0.86)",
    )
    p.add_argument(
        "--wipe-delay-ratio", type=float, default=None,
        help="contour-wipe: Tỉ lệ giữ lại tại viền (mặc định 0.04)",
    )
    p.add_argument(
        "--wipe-blocks", type=int, default=None,
        help="contour-wipe: Số lượt quét ngang qua lại của đầu bút (mặc định 18)",
    )
    p.add_argument(
        "--pause", default="heavy", choices=["auto", "off", "light", "heavy"],
        help="Nhịp dừng khi đi nét: heavy rõ rệt (mặc định); auto tự động theo mật độ; off tắt; light nhẹ",
    )
    p.add_argument(
        "--ink-path", default="grid", choices=["grid", "skeleton"],
        help="Đường nét khi đi nét: grid nội suy tâm ô lưới (mặc định); skeleton dò khung xương mức pixel",
    )
    p.add_argument(
        "--gaze", "--gaze-seconds", type=float, default=1.0, dest="gaze_seconds",
        help="Số giây dừng xem ảnh tĩnh ở cuối video (mặc định: 1.0s, ví dụ: 1.0 hoặc 1.5)",
    )
    return p.parse_args(argv)


def _build_cfg(args: argparse.Namespace) -> Config:
    kw: dict = {}
    if args.fps is not None:
        kw["fps"] = args.fps
    if args.grid_edge is not None:
        kw["grid_edge"] = args.grid_edge
    if args.brush_radius is not None:
        kw["brush_radius"] = args.brush_radius
    if args.color_fill is not None:
        kw["color_fill"] = args.color_fill
    if args.wipe_decay is not None:
        kw["wipe_decay"] = args.wipe_decay
    if args.wipe_delay_ratio is not None:
        kw["wipe_delay_ratio"] = args.wipe_delay_ratio
    if args.wipe_blocks is not None:
        kw["wipe_blocks"] = args.wipe_blocks
    if args.pause is not None:
        kw["pause_mode"] = args.pause
    if args.ink_path is not None:
        kw["ink_path_mode"] = args.ink_path
    if args.gaze_seconds is not None:
        kw["gaze_seconds"] = args.gaze_seconds
    return Config(**kw)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    cfg = _build_cfg(args)

    print("=" * 56)
    print("Bộ render hoạt hình vẽ tay nét liền")
    print("=" * 56)

    image_bgr = _imread_any(args.image)
    if image_bgr is None:
        print(f"[err] Không thể đọc ảnh: {args.image}")
        return 1

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path = out_dir / f"stream_{ts}.mp4"
    h264_path = out_dir / f"stream_{ts}_h264.mp4"

    pen_png = Path(args.pen_image) if args.pen_image else None
    renderer = StreamBoardRenderer(image_bgr, cfg, pen_png, args.bare_tip)
    print(f"  Đầu vào: {args.image}")
    print(f"  Kích thước xuất: {renderer.out_w}x{renderer.out_h}, FPS: {cfg.fps}")

    renderer.render_to(raw_path, args.total_ms)
    final = transcode_h264(raw_path, h264_path)

    size_mb = final.stat().st_size / (1024 * 1024)
    print(f"\nVideo hoàn thành: {final}")
    print(f"  Dung lượng: {size_mb:.2f} MB")
    print("=" * 56)
    print("Hoàn tất")
    # Dòng cuối in ra đường dẫn để bên ngoài dễ bắt
    print(f"OUTPUT={final}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
