#!/usr/bin/env python3
"""
video_people_counter.py
=======================
Input : 1 file video
Output: video đã vẽ box + ID + số người, file CSV theo từng frame, file JSON tóm tắt.

Pipeline: OpenCV đọc video -> YOLOv8 (class person) -> ByteTrack gán ID -> đếm.

Các số liệu được tính:
  - current : số người trong frame hiện tại
  - unique  : tổng số người khác nhau đã xuất hiện (đếm theo track ID)
  - peak    : số người đông nhất trong 1 frame
  - in/out  : số người đi qua vạch (chỉ khi dùng --line)

Cài đặt:
    pip install ultralytics opencv-python

Ví dụ:
    python video_people_counter.py --source room.mp4
    python video_people_counter.py --source door.mp4 --line 0,0.5,1,0.5
    python video_people_counter.py --source room.mp4 --model yolov8s.pt --conf 0.4 --show

Video lớn (1080p, 4K...):
    # Mặc định tự thu nhỏ nếu cạnh dài nhất > 1280 px (giữ tỉ lệ)
    python video_people_counter.py --source big_4k.mp4
    # Thu nhỏ còn tối đa 960 px cho chạy nhanh hơn trên CPU
    python video_people_counter.py --source big_4k.mp4 --max-size 960
    # Giữ nguyên kích thước gốc
    python video_people_counter.py --source big_4k.mp4 --max-size 0
"""

import argparse
import csv
import json
import time
from collections import defaultdict, deque
from pathlib import Path
from statistics import median

import cv2
from ultralytics import YOLO

PERSON_CLASS_ID = 0  # COCO: 0 = person


# --------------------------------------------------------------------------- #
# Hình học: kiểm tra người có đi qua vạch hay không
# --------------------------------------------------------------------------- #
def _ccw(a, b, c):
    return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])


def segments_intersect(a, b, c, d):
    """Đoạn AB có cắt đoạn CD không."""
    return _ccw(a, c, d) != _ccw(b, c, d) and _ccw(a, b, c) != _ccw(a, b, d)


def side_of_line(p, a, b):
    """Dấu cho biết điểm p nằm bên nào của đường thẳng a->b."""
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])


# --------------------------------------------------------------------------- #
# Đếm người
# --------------------------------------------------------------------------- #
class PeopleCounter:
    def __init__(self, line=None, min_hits=5, flip=False, density_thresholds=(5, 15)):
        self.line = line  # ((x1, y1), (x2, y2)) theo pixel hoặc None
        self.min_hits = min_hits
        self.flip = flip
        self.low_max, self.mid_max = density_thresholds

        self.hits = defaultdict(int)       # track_id -> số frame đã thấy
        self.confirmed = set()             # ID đã đủ min_hits
        self.last_point = {}               # track_id -> điểm chân ở frame trước
        self.counted_cross = set()         # ID đã tính in/out (tránh đếm lặp)

        self.count_in = 0
        self.count_out = 0
        self.peak = 0
        self.sum_current = 0
        self.frames = 0
        self.recent = deque(maxlen=15)     # làm mượt số người hiện tại

    def update(self, track_ids, foot_points, current):
        self.frames += 1
        self.sum_current += current
        self.peak = max(self.peak, current)
        self.recent.append(current)

        for tid, pt in zip(track_ids, foot_points):
            self.hits[tid] += 1
            if self.hits[tid] >= self.min_hits:
                self.confirmed.add(tid)

            if self.line is not None and tid in self.last_point and tid not in self.counted_cross:
                prev = self.last_point[tid]
                a, b = self.line
                if segments_intersect(prev, pt, a, b):
                    s_prev, s_cur = side_of_line(prev, a, b), side_of_line(pt, a, b)
                    going_in = s_prev > 0 > s_cur
                    if self.flip:
                        going_in = not going_in
                    if going_in:
                        self.count_in += 1
                    else:
                        self.count_out += 1
                    self.counted_cross.add(tid)
            self.last_point[tid] = pt

    @property
    def unique(self):
        return len(self.confirmed)

    @property
    def smoothed(self):
        return int(round(median(self.recent))) if self.recent else 0

    @property
    def average(self):
        return self.sum_current / self.frames if self.frames else 0.0

    def density_level(self):
        n = self.smoothed
        if n <= self.low_max:
            return "THAP", (0, 200, 0)
        if n <= self.mid_max:
            return "TRUNG BINH", (0, 200, 255)
        return "CAO", (0, 0, 255)


# --------------------------------------------------------------------------- #
# Vẽ
# --------------------------------------------------------------------------- #
def draw_hud(frame, counter, current, fps_proc):
    level, color = counter.density_level()
    lines = [
        f"Hien tai : {current}",
        f"Tong nguoi (unique): {counter.unique}",
        f"Dong nhat (peak): {counter.peak}",
    ]
    if counter.line is not None:
        lines.append(f"IN: {counter.count_in}   OUT: {counter.count_out}")
    lines.append(f"Mat do: {level}")
    lines.append(f"FPS xu ly: {fps_proc:.1f}")

    h = 26 * len(lines) + 14
    overlay = frame.copy()
    cv2.rectangle(overlay, (8, 8), (330, 8 + h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)
    for i, text in enumerate(lines):
        c = color if text.startswith("Mat do") else (255, 255, 255)
        cv2.putText(frame, text, (18, 34 + i * 26), cv2.FONT_HERSHEY_SIMPLEX, 0.62, c, 2, cv2.LINE_AA)


def compute_resize(width, height, max_size):
    """
    Nếu cạnh dài nhất của video lớn hơn max_size thì thu nhỏ (giữ tỉ lệ khung hình).
    max_size <= 0 nghĩa là không resize.
    Trả về (new_width, new_height, scale). Kích thước luôn là số chẵn (codec mp4 yêu cầu).
    """
    longest = max(width, height)
    if max_size <= 0 or longest <= max_size:
        return width, height, 1.0
    scale = max_size / longest
    new_w = max(2, int(round(width * scale / 2)) * 2)
    new_h = max(2, int(round(height * scale / 2)) * 2)
    return new_w, new_h, scale


def parse_line(text, width, height, scale=1.0):
    """
    'x1,y1,x2,y2'
      - Tất cả giá trị trong khoảng 0-1: hiểu là tỉ lệ theo kích thước ảnh.
      - Ngược lại: hiểu là pixel của VIDEO GỐC (tự động nhân với scale khi video bị resize).
    Trả về toạ độ theo kích thước ảnh đã xử lý.
    """
    vals = [float(v) for v in text.split(",")]
    if len(vals) != 4:
        raise ValueError("--line cần đúng 4 số: x1,y1,x2,y2")
    if all(0 <= v <= 1 for v in vals):
        px = [vals[0] * width, vals[1] * height, vals[2] * width, vals[3] * height]
    else:
        px = vals
    px = [v * scale for v in px]
    return (int(px[0]), int(px[1])), (int(px[2]), int(px[3]))


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="Phát hiện & đếm người trong video (YOLOv8 + ByteTrack)")
    ap.add_argument("--source", required=True, help="đường dẫn file video đầu vào")
    ap.add_argument("--model", default="yolov8n.pt", help="trọng số YOLO (yolov8n.pt nhẹ nhất, yolov8s/m chính xác hơn)")
    ap.add_argument("--conf", type=float, default=0.35, help="ngưỡng confidence")
    ap.add_argument("--iou", type=float, default=0.5, help="ngưỡng IoU cho NMS")
    ap.add_argument("--max-size", type=int, default=1280,
                    help="tự resize nếu cạnh dài nhất của video lớn hơn giá trị này (giữ tỉ lệ). "
                         "Mặc định 1280, đặt 0 để giữ nguyên kích thước gốc")
    ap.add_argument("--imgsz", type=int, default=640,
                    help="kích thước ảnh đưa vào model (video nhiều người nhỏ/xa nên tăng lên 960 hoặc 1280)")
    ap.add_argument("--device", default=None, help="cpu | 0 (GPU) | mps ... (mặc định tự chọn)")
    ap.add_argument("--stride", type=int, default=1, help="xử lý mỗi N frame (tăng để chạy nhanh hơn trên CPU)")
    ap.add_argument("--line", default=None, help="vạch đếm IN/OUT 'x1,y1,x2,y2' (tỉ lệ 0-1 hoặc pixel), vd 0,0.5,1,0.5")
    ap.add_argument("--flip", action="store_true", help="đảo chiều IN/OUT nếu bị ngược")
    ap.add_argument("--min-hits", type=int, default=5, help="ID phải xuất hiện ít nhất N frame mới tính vào unique")
    ap.add_argument("--density", default="5,15", help="ngưỡng mật độ 'thấp_max,trung_bình_max' (số người)")
    ap.add_argument("--out-dir", default="outputs", help="thư mục lưu kết quả")
    ap.add_argument("--show", action="store_true", help="hiển thị cửa sổ khi xử lý (bấm q để thoát)")
    ap.add_argument("--no-video", action="store_true", help="không ghi video kết quả (chỉ xuất CSV/JSON)")
    args = ap.parse_args()

    src = Path(args.source)
    if not src.exists():
        raise SystemExit(f"Không tìm thấy video: {src}")

    cap = cv2.VideoCapture(str(src))
    if not cap.isOpened():
        raise SystemExit(f"Không mở được video: {src}")

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0

    proc_w, proc_h, scale = compute_resize(width, height, args.max_size)
    resized = scale < 1.0

    line = parse_line(args.line, width, height, scale) if args.line else None
    low, mid = (int(v) for v in args.density.split(","))
    counter = PeopleCounter(line=line, min_hits=args.min_hits, flip=args.flip, density_thresholds=(low, mid))

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = src.stem
    video_path = out_dir / f"{stem}_counted.mp4"
    csv_path = out_dir / f"{stem}_counts.csv"
    json_path = out_dir / f"{stem}_summary.json"

    writer = None
    if not args.no_video:
        writer = cv2.VideoWriter(
            str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), fps / max(args.stride, 1), (proc_w, proc_h)
        )

    model = YOLO(args.model)

    csv_file = open(csv_path, "w", newline="", encoding="utf-8")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(["frame", "time_s", "current", "unique", "in", "out"])

    print(f"Video: {src}  |  {width}x{height}  |  {fps:.1f} fps  |  {total_frames} frames")
    if resized:
        print(f"Resize: {width}x{height} -> {proc_w}x{proc_h} (x{scale:.2f}, --max-size {args.max_size})")
    else:
        print(f"Resize: không cần (cạnh dài nhất <= {args.max_size})" if args.max_size > 0
              else "Resize: tắt, giữ kích thước gốc")
    t_start = time.time()
    frame_idx = 0
    processed = 0
    fps_proc = 0.0

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame_idx += 1
            if (frame_idx - 1) % args.stride != 0:
                continue

            if resized:
                frame = cv2.resize(frame, (proc_w, proc_h), interpolation=cv2.INTER_AREA)

            t0 = time.time()
            results = model.track(
                frame,
                persist=True,
                tracker="bytetrack.yaml",
                classes=[PERSON_CLASS_ID],
                conf=args.conf,
                iou=args.iou,
                imgsz=args.imgsz,
                device=args.device,
                verbose=False,
            )
            boxes = results[0].boxes

            track_ids, foot_points = [], []
            current = 0
            if boxes is not None and len(boxes) > 0:
                xyxy = boxes.xyxy.cpu().numpy()
                ids = boxes.id.int().cpu().tolist() if boxes.id is not None else [None] * len(xyxy)
                confs = boxes.conf.cpu().numpy()
                current = len(xyxy)

                for (x1, y1, x2, y2), tid, cf in zip(xyxy, ids, confs):
                    x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 220, 0), 2)
                    label = f"ID {tid}" if tid is not None else "person"
                    cv2.putText(frame, f"{label} {cf:.2f}", (x1, max(y1 - 6, 14)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA)
                    if tid is not None:
                        track_ids.append(tid)
                        foot_points.append(((x1 + x2) // 2, y2))  # điểm chân người

            counter.update(track_ids, foot_points, current)

            if line is not None:
                cv2.line(frame, line[0], line[1], (0, 0, 255), 3)

            processed += 1
            dt = time.time() - t0
            fps_proc = 0.9 * fps_proc + 0.1 * (1.0 / dt) if fps_proc else 1.0 / dt
            draw_hud(frame, counter, counter.smoothed, fps_proc)

            csv_writer.writerow([frame_idx, round(frame_idx / fps, 2), current,
                                 counter.unique, counter.count_in, counter.count_out])
            if writer is not None:
                writer.write(frame)

            if args.show:
                cv2.imshow("People counter", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    print("Dừng theo yêu cầu (q).")
                    break

            if processed % 50 == 0:
                pct = f"{frame_idx / total_frames * 100:.0f}%" if total_frames else "?"
                print(f"[{pct}] frame {frame_idx}: hiện tại={current}, unique={counter.unique}, "
                      f"peak={counter.peak}, {fps_proc:.1f} fps")
    finally:
        cap.release()
        if writer is not None:
            writer.release()
        csv_file.close()
        if args.show:
            cv2.destroyAllWindows()

    summary = {
        "video": str(src),
        "frames_read": frame_idx,
        "frames_processed": processed,
        "duration_s": round(frame_idx / fps, 2),
        "unique_people": counter.unique,
        "peak_in_frame": counter.peak,
        "average_in_frame": round(counter.average, 2),
        "line_in": counter.count_in if line else None,
        "line_out": counter.count_out if line else None,
        "original_size": f"{width}x{height}",
        "processed_size": f"{proc_w}x{proc_h}",
        "model": args.model,
        "conf": args.conf,
        "processing_time_s": round(time.time() - t_start, 1),
    }
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n===== KET QUA =====")
    for k, v in summary.items():
        print(f"{k:>18}: {v}")
    if not args.no_video:
        print(f"\nVideo kết quả : {video_path}")
    print(f"CSV theo frame: {csv_path}")
    print(f"Tóm tắt JSON  : {json_path}")


if __name__ == "__main__":
    main()