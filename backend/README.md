# Smart Indoor Occupancy & Crowd Density Analytics — Python Backend (`backend`)

Backend trung tâm được xây dựng bằng **Python 3.11+**, **FastAPI**, **SQLAlchemy 2.0**, **PostgreSQL**, **Alembic**, **Pydantic v2**, **Paho-MQTT**, **WebSocket**, và **JWT RBAC (`ADMIN` / `OPERATOR`)**.

---

## 1. Kiến trúc thư mục

```text
backend/
├── app/
│   ├── api/v1/
│   │   ├── auth/router.py          # Module 1: Login, Refresh, Logout, Me, Users
│   │   ├── rooms/router.py         # Module 2: Room CRUD & Thresholds
│   │   ├── zones/router.py         # Module 3: Polygon Zone CRUD & Calibration
│   │   ├── occupancy/router.py     # Module 4 & 5: Occupancy & Density Current/History
│   │   ├── alerts/router.py        # Module 6: Alert Listing, Acknowledge & Resolve
│   │   ├── devices/router.py       # Module 7: Raspberry Pi & Camera Status/Commands
│   │   └── analytics/router.py     # Module 8: Overview, Peak Hours, Series & OLS Forecast
│   ├── core/
│   │   ├── config.py               # Pydantic Settings (.env)
│   │   ├── security.py             # PBKDF2-SHA256, JWT Access/Refresh, Revocation, RBAC
│   │   └── exceptions.py           # Global Exception Handlers
│   ├── database/
│   │   ├── base.py                 # SQLAlchemy 2.0 DeclarativeBase
│   │   ├── session.py              # Engine & SessionLocal
│   │   └── seed.py                 # Idempotent Seeder (Admin/Operator, Room1, Zones A/B/C, RPi)
│   ├── models/
│   │   └── entities.py             # 9 ORM Models (users, rooms, zones, devices, occupancy_records, density_records, alerts, device_status_logs, system_events)
│   ├── schemas/                    # Pydantic v2 Schemas (Request/Response & MQTT Contracts)
│   ├── repositories/               # Data Access Layer (CRUD Repositories)
│   ├── services/                   # Business Logic Layer
│   ├── mqtt/
│   │   └── worker.py               # Async Paho-MQTT Worker (Retained filter, Dedup, Pydantic validation, IoT Actuation)
│   ├── websocket/
│   │   └── manager.py              # Realtime WebSocket Manager (Error isolation, Ping/Pong)
│   ├── analytics/
│   │   └── engine.py               # Historical Aggregations, Peak Hours & OLS Forecasting
│   └── main.py                     # FastAPI Entrypoint
├── alembic/                        # Alembic Database Migrations
├── tests/
│   └── test_backend_all.py         # Pytest Suite (10/10 verification areas)
├── requirements.txt
├── .env.example
└── Dockerfile
```

---

## 2. Hướng dẫn Cài đặt & Chạy

### 2.1. Cài đặt thư viện
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
```

### 2.2. Chạy Migration với Alembic
```bash
cd backend
alembic upgrade head
```

### 2.3. Chạy Backend Server
```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 4000 --reload
```
- Swagger UI (OpenAPI Docs): `http://localhost:4000/docs`
- Healthcheck: `http://localhost:4000/api/v1/health`
- WebSocket Realtime: `ws://localhost:4000/ws/realtime?room_id=room1`

### 2.4. Tài khoản Mặc định (Seeded)
- **Admin:** `admin` / `Admin@123` (Role: `ADMIN`)
- **Operator:** `operator` / `Operator@123` (Role: `OPERATOR`)

---

## 3. Chạy Kiểm thử Tự động (Pytest)
```bash
cd backend
pytest -v
```
