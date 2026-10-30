# Raspberry Pi 4 / 5 IoT Edge Module (`iot-service`)
## Smart Indoor Occupancy & Crowd Density Analytics System

Module nhúng Linux & IoT chạy trên **Raspberry Pi 4 / 5** chịu trách nhiệm kết nối Camera, nhận dữ liệu số lượng người (`count`), mật độ (`density`) và cảnh báo (`alerts`) từ **AI Service** qua **Eclipse Mosquitto MQTT**, điều khiển hệ thống đèn cảnh báo **LED (Xanh / Vàng / Đỏ)** và **Còi Buzzer**, kèm cơ chế **Auto-Reconnect**, **Watchdog tự phục hồi** và **Simulation Mode**.

---

## 1. Sơ Đồ Chân GPIO (Approved Pin Mapping — 40-Pin Header J8)

| Thiết bị ngoại vi | Trạng thái biểu thị | Chân BCM | Chân Vật Lý (Board Pin) | Hướng dẫn đấu dây trên Breadboard |
| :--- | :--- | :---: | :---: | :--- |
| **LED Xanh (Green)** | Mật độ bình thường (`LOW` / `MEDIUM`) | **GPIO 17** | **Pin 11** | `Pin 11` $\rightarrow$ Điện trở $220\Omega$ $\rightarrow$ Anode (+) LED Xanh $\rightarrow$ Cathode (-) về **GND Rail** |
| **LED Vàng (Yellow)** | Mật độ gần ngưỡng (`WARNING` / `HIGH`) | **GPIO 27** | **Pin 13** | `Pin 13` $\rightarrow$ Điện trở $220\Omega$ $\rightarrow$ Anode (+) LED Vàng $\rightarrow$ Cathode (-) về **GND Rail** |
| **LED Đỏ (Red)** | Mật độ vượt ngưỡng (`CRITICAL`) | **GPIO 22** | **Pin 15** | `Pin 15` $\rightarrow$ Điện trở $220\Omega$ $\rightarrow$ Anode (+) LED Đỏ $\rightarrow$ Cathode (-) về **GND Rail** |
| **Còi Buzzer** | Báo động âm thanh khi `CRITICAL` | **GPIO 23** | **Pin 16** | `Pin 16` $\rightarrow$ Điện trở $1\text{k}\Omega$ $\rightarrow$ cực Base (B) Transistor NPN `2N2222` (Collector nối cực (-) Buzzer, cực (+) Buzzer nối `Pin 2 (5V)`, Emitter nối **GND Rail**) |
| **GND Chung** | Mass tham chiếu `0V` | **GND** | **Pin 14** (hoặc 6, 9, 20) | Nối từ `Pin 14` ra thanh nguồn âm (`-`) của Breadboard |

---

## 2. Kiến Trúc Tách Biệt 4 Lớp

```text
iot-service/
├── .env.example                      # Cấu hình BCM GPIO pins, Room ID, Thresholds, Simulation Mode
├── systemd/
│   └── smart-occupancy-iot.service   # Unit file systemd tự động khởi động & Watchdog cấp OS
├── app/
│   ├── main.py                       # Entrypoint + Signal Handlers (SIGINT/SIGTERM) + Ensure GPIO Cleanup
│   ├── config.py                     # Pydantic Settings
│   ├── logger.py                     # Ghi log đồng thời ra Console và Rotating File (logs/iot_device.log)
│   ├── hardware/
│   │   ├── gpio_interface.py         # Lớp trừu tượng BaseGpioDriver + RPiHardwareGpioDriver + SimulationGpioDriver
│   │   ├── gpio_driver.py            # Điều khiển LED (Green/Yellow/Red), Buzzer Pulse 2Hz & Auto-Cleanup
│   │   └── camera_streamer.py        # Kiểm tra kết nối Camera (USB/CSI), phát MJPEG & HTTP fallback tới AI Service
│   ├── processor/
│   │   └── occupancy_processor.py    # Xử lý dữ liệu count, density, alerts & quyết định trạng thái LED/Buzzer
│   ├── mqtt/
│   │   └── client.py                 # Giao tiếp Mosquitto MQTT + Auto-Reconnect Backoff + Last Will (LWT)
│   └── watchdog/
│       └── supervisor.py             # Watchdog giám sát kết nối MQTT, luồng Buzzer & tự phục hồi khi lỗi
└── tests/
    └── test_iot_module.py            # Bộ Unit Test kiểm thử Simulation Mode, Processor, MQTT Routing & Watchdog
```

---

## 3. Danh Sách MQTT Topics Hỗ Trợ

- `occupancy/room1/count` *(Subscribe)*: Nhận số lượng người hiện tại và sức chứa tối đa.
- `occupancy/room1/density` *(Subscribe)*: Nhận mật độ người ($\text{người}/m^2$) và mức mật độ (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
- `occupancy/room1/alerts` *(Subscribe)*: Nhận cảnh báo mật độ/đám đông (`NONE`, `WARNING`, `CRITICAL`).
- `occupancy/room1/device/status` *(Publish - QoS 1, Retained + LWT)*: Xuất trạng thái thiết bị, trạng thái chân GPIO, nhiệt độ CPU và thời gian hoạt động (`uptimeSec`).
- `occupancy/room1/device/command` *(Subscribe)*: Nhận lệnh điều khiển từ xa (`SET_STATE`, `SILENCE_BUZZER`, `RESET`).

---

## 4. Hướng Dẫn Chạy Kiểm Thử Simulation & Triển Khai Thực Tế

### A. Chạy bộ Unit Tests (Kiểm chứng 4 lớp độc lập)
```bash
cd iot-service
pip install -r requirements.txt
python -m unittest discover -s tests -v
```

### B. Chạy chế độ Simulation Mode (Khi chưa cắm mạch Raspberry Pi thật)
```bash
python -m app.main --simulate
```
Chế độ `--simulate` sẽ mô phỏng toàn bộ chu trình:
1. Mật độ bình thường (`14 người`, `0.12 người/m²`) $\rightarrow$ `GPIO17(GREEN)=ON (3.3V) | BUZZER=SILENT`
2. Mật độ tiệm cận ngưỡng (`50 người`, `0.41 người/m²`) $\rightarrow$ `GPIO27(YELLOW)=ON (3.3V) | BUZZER=SILENT`
3. Cảnh báo nghiêm trọng (`CRITICAL`) $\rightarrow$ `GPIO22(RED)=ON (3.3V) | GPIO23(BUZZER)=ACTIVE`
4. Nhận lệnh tắt còi `SILENCE_BUZZER` qua MQTT $\rightarrow$ `GPIO22(RED)=ON (3.3V) | GPIO23(BUZZER)=SILENT`
5. Mật độ giảm về bình thường $\rightarrow$ `GPIO17(GREEN)=ON (3.3V)`
6. Kết thúc chương trình $\rightarrow$ Giải phóng toàn bộ chân GPIO về `LOW (0.0V)`.

### C. Chạy kết nối với Mosquitto Broker (Trên PC hoặc Raspberry Pi 4/5)
```bash
# Chạy tự động nhận diện phần cứng (hoặc thêm --force-sim-gpio nếu muốn ép chế độ giả lập):
python -m app.main
```

### D. Cài đặt dịch vụ chạy ngầm tự khởi động trên Raspberry Pi OS (`systemd`)
```bash
sudo cp systemd/smart-occupancy-iot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now smart-occupancy-iot.service
sudo systemctl status smart-occupancy-iot.service
```
