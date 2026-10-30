# AI Computer Vision Engine (`ai-service`)
## Smart Indoor Occupancy & Crowd Density Analytics System

Tài liệu kỹ thuật chuyên sâu cho **AI Engine** được xây dựng bằng **Python, YOLOv8n/ONNX, ByteTrack, OpenCV, NumPy, FastAPI và Paho-MQTT**.

---

## 1. Cấu Trúc Module Tách Biệt

```text
ai-service/
├── config/
│   └── zones.json                   # Cấu hình Polygon Zones (A, B, C), diện tích (m²), ngưỡng mật độ & Virtual Lines
├── app/
│   ├── main.py                      # Entrypoint FastAPI + CLI (--source, --frame-skip, --export-onnx, --self-test)
│   ├── core/
│   │   ├── config.py                # Pydantic Settings quản lý toàn bộ tham số AI & tối ưu Raspberry Pi
│   │   └── logger.py                # Structured Logger
│   ├── schemas/
│   │   └── vision_schema.py         # Cấu trúc JSON thống nhất cho Detection, Track, Zone, Line, Alert, Performance
│   ├── vision/
│   │   ├── camera_manager.py        # Module đọc Webcam (0), PiCamera, RTSP và Video file (.mp4) đa luồng
│   │   ├── detector.py              # Module 1: Person Detection (YOLO class 0, giảm độ phân giải, xuất ONNX)
│   │   ├── tracker.py               # Module 2: ByteTrack Multi-Object Tracking (2-stage IoU & Occlusion recovery)
│   │   ├── counter.py               # Module 3: People Counting & Virtual Line Crossing (IN / OUT state machine)
│   │   ├── zone_analyzer.py         # Module 4: Point-in-Polygon Zone Density (người/m²) & đọc JSON config
│   │   ├── heatmap_generator.py     # Module 5: Gaussian Spatial Density Heatmap + Decay + Lưu ảnh PNG
│   │   ├── crowd_alert.py           # Module 6: Crowd Alert Engine với Hysteresis & Sustain Timer
│   │   ├── performance.py           # Module 7: Frame Skipping & Đo FPS, Inference Time (ms), Processing Time (ms)
│   │   └── annotator.py             # Vẽ Bounding Box, Confidence, Track ID, Virtual Line, Zones, Heatmap & HUD
│   ├── services/
│   │   ├── mqtt_publisher.py        # Publish JSON thống nhất qua MQTT & lắng nghe cập nhật cấu hình
│   │   └── pipeline_engine.py       # Điều phối toàn bộ 7 bước xử lý thị giác máy tính trên từng khung hình
│   └── api/
│       └── routes.py                # Endpoints: /health, /analytics/current, /analytics/zones, /heatmap/save, /streams/...
├── scripts/
│   └── run_video_demo.py            # Chạy kiểm thử bằng file Video (.mp4) trên máy tính trước khi đưa lên Pi
└── tests/
    └── test_vision_algorithms.py    # Bộ Unit Test kiểm증 toàn bộ thuật toán cốt lõi
```

---

## 2. Giải Thích Chi Tiết Các Thuật Toán

### 2.1. Person Detection & Tối Ưu Độ Phân Giải (`app/vision/detector.py`)
- Chỉ lọc duy nhất lớp **`Person` (`COCO class_id = 0`)**.
- Trước khi đưa vào mạng nơ-ron YOLO, khung hình gốc $(W_{\text{orig}}, H_{\text{orig}})$ được thu nhỏ về kích thước suy luận $(W_{\text{inf}}, H_{\text{inf}})$ (mặc định `640x384`). Sau khi suy luận, tọa độ Bounding Box $(x_1, y_1, x_2, y_2)$ được nội suy ngược về khung hình gốc theo tỷ lệ:
  $$x_{\text{orig}} = x_{\text{inf}} \cdot \frac{W_{\text{orig}}}{W_{\text{inf}}}, \quad y_{\text{orig}} = y_{\text{inf}} \cdot \frac{H_{\text{orig}}}{H_{\text{inf}}}$$

### 2.2. Multi-Object Tracking với ByteTrack (`app/vision/tracker.py`)
Thuật toán **ByteTrack** giải quyết bài toán mất dấu và đếm trùng khi người bị che khuất một phần:
1. **Phân tách ngưỡng kép:** Chia các phát hiện (detections) thành 2 tập:
   - $D_{\text{high}}$: các box có $\text{confidence} \ge \tau_{\text{high}}$ (ví dụ `0.35`).
   - $D_{\text{low}}$: các box có $\tau_{\text{low}} \le \text{confidence} < \tau_{\text{high}}$ (ví dụ `0.15 .. 0.35`).
2. **Dự đoán chuyển động (Motion Prediction):** Mỗi đối tượng đang theo dõi (`STrack`) cập nhật vị trí dự kiến bằng vận tốc làm mượt hàm mũ:
   $$\vec{v}_t = 0.6 \vec{v}_{t-1} + 0.4 \frac{\text{bbox}_t - \text{bbox}_{t-1}}{\Delta t}$$
3. **Liên kết Giai đoạn 1 (High-Confidence Association):** Ghép cặp các track (`TRACKED` và `LOST`) với $D_{\text{high}}$ thông qua ma trận **IoU (Intersection over Union)**.
4. **Liên kết Giai đoạn 2 (Low-Confidence / Occlusion Recovery):** Các track `TRACKED` chưa ghép được ở Giai đoạn 1 sẽ được ghép tiếp với $D_{\text{low}}$. Khi một người bị người khác che khuất một phần, điểm tự tin của YOLO giảm xuống vùng $D_{\text{low}}$ (`0.15 - 0.35`), Giai đoạn 2 giúp giữ nguyên `track_id` thay vì hủy track và tạo ID mới.
5. **Bộ đệm che khuất hoàn toàn (`track_buffer`):** Nếu bị khuất hoàn toàn, track chuyển sang trạng thái `LOST` và được giữ trong `track_buffer` frames (mặc định `30` frames) để khôi phục lại đúng ID cũ khi xuất hiện trở lại.

### 2.3. People Counting & Virtual Line Crossing (`app/vision/counter.py`)
- Cho một đường ảo (Virtual Line) $AB$ từ $A(x_1, y_1)$ đến $B(x_2, y_2)$ và vector di chuyển chân của một người từ frame trước $P$ đến frame hiện tại $Q$.
- Hai đoạn thẳng $AB$ và $PQ$ cắt nhau khi và chỉ khi:
  $$\text{ccw}(A, B, P) \cdot \text{ccw}(A, B, Q) < 0 \quad \text{và} \quad \text{ccw}(P, Q, A) \cdot \text{ccw}(P, Q, B) < 0$$
  trong đó $\text{ccw}(U, V, W) = (V_x - U_x)(W_y - U_y) - (V_y - U_y)(W_x - U_x)$ là tích có hướng 2D.
- **Chống đếm trùng:** Mỗi cặp `(line_id, track_id)` lưu trạng thái hướng cắt cuối cùng (`IN` hoặc `OUT`) và thời gian debounce. Một `track_id` không thể cộng 2 lần liên tiếp cùng chiều `IN` nếu người đó đứng nhấp nhô ngay trên vạch.

### 2.4. Phân Tích Mật Độ Theo Vùng Đa Giác (`app/vision/zone_analyzer.py`)
- Điểm đại diện cho vị trí đứng của mỗi người là điểm giữa cạnh đáy Bounding Box:
  $$P_{\text{foot}} = \left( \frac{x_1 + x_2}{2}, y_2 \right)$$
- Kiểm tra $P_{\text{foot}}$ thuộc đa giác `Zone` nào bằng `cv2.pointPolygonTest(contour, P_foot, False) >= 0`.
- Tính mật độ thực tế đã hiệu chuẩn theo diện tích sàn $A_{\text{zone}}$ ($m^2$):
  $$\text{Density}_{\text{zone}} = \frac{N_{\text{zone}}}{A_{\text{zone}}} \quad (\text{người}/m^2)$$

### 2.5. Crowd Alert với Hysteresis & Sustain Timer (`app/vision/crowd_alert.py`)
- Để tránh cảnh báo bật/tắt liên tục (flapping) khi mật độ dao động quanh ngưỡng $T_{\text{trigger}}$, hệ thống định nghĩa ngưỡng giải phóng thấp hơn:
  $$T_{\text{clear}} = T_{\text{trigger}} \times (1 - \text{hysteresis\_ratio})$$
- Cảnh báo chỉ phát ra khi trạng thái vượt ngưỡng $T_{\text{trigger}}$ duy trì liên tục tối thiểu `sustain_sec` giây (mặc định `2.0s`), và chỉ tự động tắt khi giá trị đo giảm xuống dưới $T_{\text{clear}}$.

---

## 3. Hướng Dẫn Chạy Và Kiểm Thử Trên Máy Tính (Trước Khi Đưa Lên Raspberry Pi)

### Bước 1: Cài đặt thư viện
```bash
cd ai-service
pip install -r requirements.txt
```

### Bước 2: Chạy bộ Unit Test kiểm chứng thuật toán
```bash
python -m unittest discover -s tests -v
```

### Bước 3: Chạy kiểm thử bằng File Video (`.mp4`) khi chưa có Camera
```bash
# Tự động tạo video mẫu hoặc truyền đường dẫn file video bất kỳ vào --video
python scripts/run_video_demo.py --max-frames 30 --frame-skip 2
```
Script sẽ xuất ra:
- Video đã vẽ Bounding Box, Track ID, Virtual Line, Polygon Zones và Heatmap tại `outputs/annotated_output.mp4`.
- Ảnh chụp Density Heatmap PNG tại `outputs/heatmaps/`.

### Bước 4: Khởi chạy FastAPI Server với Webcam hoặc Video File
```bash
# Chạy với Webcam laptop (index 0):
python -m app.main --source 0

# Hoặc chạy với file video .mp4 lặp vòng:
python -m app.main --source outputs/sample_input.mp4 --frame-skip 2
```
Kiểm tra các REST Endpoints:
- `GET http://localhost:8000/health`
- `GET http://localhost:8000/analytics/current`
- `GET http://localhost:8000/analytics/zones`
- `POST http://localhost:8000/heatmap/save`
- Xem luồng video trực tiếp: `http://localhost:8000/streams/default/mjpeg?overlay_zones=true&overlay_heatmap=true`

---

## 4. Tối Ưu Hóa Khi Triển Khai Lên Raspberry Pi 4 / 5

1. **Chuyển đổi mô hình YOLO sang ONNX nhẹ hơn:**
   ```bash
   python -m app.main --export-onnx --inference-width 640 --inference-height 384
   ```
   Sau đó cấu hình `YOLO_MODEL_PATH=yolov8n.onnx` trong `.env`.
2. **Bật Frame Skipping & Giảm độ phân giải suy luận:**
   ```bash
   python -m app.main --source picamera --frame-skip 3 --inference-width 480 --inference-height 288
   ```
   Ở các frame bỏ qua suy luận YOLO, `ByteTracker.predict_only()` sẽ tự động nội suy vị trí Bounding Box dựa trên vector vận tốc để giữ nguyên độ mượt của luồng video và giảm tải CPU hơn 60%.
