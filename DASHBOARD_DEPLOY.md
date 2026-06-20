# Web Dashboard — Hướng dẫn deploy (CHG-FX-015)

Trang web giám sát + thao tác tay cho bot Forex, chạy song song với
`forex-bot.service`, không ảnh hưởng bot đang chạy.

## 1. Chức năng

- Hiển thị **balance** tài khoản (real-time)
- Hiển thị **positions** đang mở (symbol, side, units, giá vào...)
- Hiển thị **open orders** (gồm SL/TP đang chờ khớp)
- Hiển thị **recent fills** — 20 lệnh khớp gần nhất
- Auto-refresh mỗi 5 giây
- Nút **"Đóng"** — đóng tay 1 position (có confirm dialog trước khi gửi lệnh)
- Nút **"Cancel"** — cancel 1 order đang chờ (ví dụ SL/TP còn sót lại), có confirm
- Login bằng HTTP Basic Auth (`DASHBOARD_USER` / `DASHBOARD_PASS`)

## 2. Kiến trúc / an toàn

- File: `phase9_live/web_dashboard.py` (FastAPI + uvicorn)
- Kết nối IB Gateway riêng bằng `IBKROrderManager(client_id_offset=40)` →
  `clientId = IB_CLIENT_ID + 40`. Các clientId khác đang dùng:
  - `forex-bot.service` (`live_engine.py`) → offset 20
  - `scripts/test_order.py` → offset 30
  - Web dashboard → offset 40
  → Không trùng, không gây conflict với bot đang chạy.
- `asyncio.Lock()` đảm bảo các request tới dashboard không gọi đồng thời lên
  cùng 1 connection IB.

## 3. Các file đã thay đổi/thêm (đã viết xong, syntax OK)

| File | Thay đổi |
|---|---|
| `phase9_live/web_dashboard.py` | **MỚI** — FastAPI app, toàn bộ UI + API |
| `config/settings.py` | Thêm `DASHBOARD_USER`, `DASHBOARD_PASS`, `DASHBOARD_CLIENT_ID_OFFSET=40` |
| `requirements.txt` | Thêm `fastapi>=0.110.0`, `uvicorn>=0.29.0` |
| `.env.example` | Thêm mẫu `DASHBOARD_USER`/`DASHBOARD_PASS` |
| `GUIDELINE.md` | Mục "Web Dashboard — monitor + đóng lệnh tay qua web (CHG-FX-015)" |
| `CHANGED.md` | Entry CHG-FX-015 |

## 4. Deploy lên VPS

### Bước 1 — rsync code từ Mac

Chạy trên **Mac** (terminal, không dùng `scp`):

```bash
rsync -avzc /Users/ngocdang/Claude/Projects/API_FOREX/phase9_live/web_dashboard.py root@69.12.65.42:/root/API_FOREX/phase9_live/
rsync -avzc /Users/ngocdang/Claude/Projects/API_FOREX/config/settings.py root@69.12.65.42:/root/API_FOREX/config/
rsync -avzc /Users/ngocdang/Claude/Projects/API_FOREX/requirements.txt root@69.12.65.42:/root/API_FOREX/
```

### Bước 2 — cài dependency + thêm config trên VPS

SSH vào VPS rồi chạy:

```bash
cd /root/API_FOREX
source .venv/bin/activate
pip install -r requirements.txt
```

Thêm credentials vào `.env` (đổi password mạnh, không để `changeme`):

```bash
cat >> /root/API_FOREX/.env << 'EOF'

DASHBOARD_USER=admin
DASHBOARD_PASS=<đặt password mạnh>
EOF
```

### Bước 3 — tạo systemd service

```bash
cat > /etc/systemd/system/forex-dashboard.service << 'EOF'
[Unit]
Description=Forex Bot Web Dashboard
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/API_FOREX
ExecStart=/root/API_FOREX/.venv/bin/uvicorn phase9_live.web_dashboard:app --host 0.0.0.0 --port 8080 --loop asyncio
Restart=on-failure
RestartSec=10
StandardOutput=append:/root/API_FOREX/logs/dashboard.log
StandardError=append:/root/API_FOREX/logs/dashboard_errors.log

[Install]
WantedBy=multi-user.target
EOF
```

### Bước 4 — mở port + start service

```bash
ufw allow 8080/tcp
systemctl daemon-reload
systemctl enable --now forex-dashboard
systemctl status forex-dashboard
```

### Bước 5 — kiểm tra

Mở browser: `http://<VPS_IP>:8080` → login bằng `DASHBOARD_USER`/`DASHBOARD_PASS`
vừa tạo. Kiểm tra balance, positions, open orders, recent fills hiển thị đúng.

Nếu lỗi, xem log:

```bash
tail -50 /root/API_FOREX/logs/dashboard.log
tail -50 /root/API_FOREX/logs/dashboard_errors.log
journalctl -u forex-dashboard -n 50 --no-pager
```

## 5. Lưu ý bảo mật

- Đây là **HTTP, không phải HTTPS** — Basic Auth credentials gửi không mã hoá.
- Khuyến nghị: dùng SSH tunnel thay vì mở port 8080 ra internet:

```bash
# trên Mac
ssh -L 8080:localhost:8080 root@69.12.65.42
```

  Sau đó truy cập `http://localhost:8080` trên Mac — không cần mở firewall port 8080.

- Hoặc đặt Nginx reverse proxy + Let's Encrypt (HTTPS) phía trước nếu muốn truy
  cập trực tiếp từ internet một cách an toàn hơn.

## 6. Trạng thái

- ✅ Code đã viết xong, syntax verified (`python3 -m py_compile`)
- ⏳ **Chưa deploy lên VPS** — cần thực hiện đủ 4 bước ở mục 4
- Liên quan: CHG-FX-014 (fix SL/TP OCA group) — đã deploy + verify thành công,
  xem `CHANGED.md` và `BACKUP_CONTEXT.md` mục 12d
