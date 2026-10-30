# Smart Indoor Occupancy & Crowd Density Analytics System

Hệ thống IoT kết hợp AI Computer Vision theo dõi số lượng người và phân tích mật độ đám đông trong không gian kín theo thời gian thực bằng **Raspberry Pi 4/5**, **Camera**, **YOLOv8 + ByteTrack**, **Eclipse Mosquitto MQTT**, **Python FastAPI + SQLAlchemy 2.0 + PostgreSQL** và **React 18 + Vite + TypeScript**.

## 1. Cấu Trúc Monorepo

```text
iot-ck/
├── ai-service/          # AI Computer Vision Engine (Python, YOLOv8n/ONNX, OpenCV, ByteTrack, FastAPI, MQTT)
├── iot-service/         # Raspberry Pi 4/5 Edge Service (GPIO BCM 17/27/22/23, LED/Buzzer, Watchdog, MQTT LWT)
├── backend/             # Modular Python Backend (FastAPI, SQLAlchemy 2.0, PostgreSQL, Alembic, Async MQTT, WebSocket, JWT RBAC)
├── frontend/            # Realtime Monitoring Dashboard (React 18, Vite, TypeScript, Tailwind CSS, TanStack Query, Zustand, Recharts)
├── mosquitto/           # Cấu hình Eclipse Mosquitto 2.0 Broker (TCP :1883 & WebSocket :9001)
├── tests/               # Bộ kiểm thử tích hợp toàn hệ thống (End-to-End System Integration Tests)
└── docker-compose.yml   # Điều phối toàn bộ 6 dịch vụ
```

## 2. Khởi Chạy Nhanh Với Docker Compose

```powershell
# Khởi tạo và chạy toàn bộ hệ thống
docker compose up -d --build

# Kiểm tra trạng thái các container
docker compose ps
```

- **Web Dashboard:** http://localhost:3000
  - Tài khoản Admin: `admin` / `Admin@123`
  - Tài khoản Operator: `operator` / `Operator@123`
- **Backend API & Swagger UI:** http://localhost:4000/docs (`GET /api/v1/health`)
- **AI Vision Service:** http://localhost:8000/health (`GET /stream.mjpg`)
- **Mosquitto MQTT Broker:** `localhost:1883`

## 3. Chạy Kiểm Thử Toàn Hệ Thống (End-to-End & Unit Tests)

```powershell
# 1. Kiểm thử tích hợp toàn hệ thống (11 tests covering 10 real-world scenarios)
python -m pytest tests/test_system_integration.py -v

# 2. Kiểm thử Python FastAPI Backend (10 tests)
python -m pytest backend/tests -v

# 3. Kiểm thử AI Vision Engine (8 tests)
cd ai-service && python -m unittest discover -s tests -v

# 4. Kiểm thử Raspberry Pi IoT Edge Service (4 tests)
cd iot-service && python -m unittest discover -s tests -v

# 5. Kiểm thử & Build Frontend React + Vite + TypeScript (7 tests)
cd frontend && npm test && npm run build
```
