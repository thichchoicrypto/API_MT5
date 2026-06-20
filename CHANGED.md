# Forex SMC Scalper Bot — Change Log
> Track toàn bộ thay đổi code theo thời gian.
> Format: ngày giờ | lý do | file | phần fix | ảnh hưởng

---

## Conv 10 — Switch `forex-bot.service` sang `main.py live` (IBKR demo, real order routing) (2026-06-15)

---

### CHG-FX-010 | Thêm `set_position_mode` / `set_leverage` / `get_order` vào `IBKROrderManager`
- **Thời gian:** 2026-06-15 Conv 10 (implement ở session trước, document ở session này)
- **Tại sao:** `live_engine.py` (adapt từ OKX bot) gọi 3 method này ở `start()` (set
  hedge/position mode + leverage trước khi trade) và ở `_execute_signal()` (confirm
  LIMIT order đã fill chưa trước khi đặt SL child order) — `IBKROrderManager` (viết mới
  cho IBKR, Conv 1) chưa có 3 method này → `AttributeError` khi chạy `main.py live`.
- **File:** `phase9_live/ibkr_order_manager.py`
- **Fix:**
  - `set_position_mode()` — no-op + log, vì IBKR IDEALPRO là netting account (không có
    khái niệm hedge mode như OKX).
  - `set_leverage(symbol, leverage)` — no-op + debug log, vì leverage trên IBKR là
    account-level (Reg T/Portfolio Margin), không set per-symbol qua API như OKX.
  - `get_order(symbol, order_id)` — tìm trade trong `self._ib.trades()` theo `orderId`,
    map `orderStatus.status` (`Filled`/`Cancelled`/`ApiCancelled`/`Inactive`/khác) sang
    `state: "filled" | "cancelled" | "open"`, trả dict gồm `filled`, `remaining`,
    `avgFillPrice`, hoặc `None` nếu không tìm thấy.
- **Ảnh hưởng:** `main.py live` không còn crash `AttributeError` khi startup và khi
  `_execute_signal()` cần confirm LIMIT order fill.

---

### CHG-FX-011 | `NameError: name 'IBKRDownloader' is not defined` — crash ngay khi `main.py live` chạy gap-fill
- **Thời gian:** 2026-06-15 Conv 10
- **Tại sao:** Test foreground `main.py live` lần đầu crash ngay ở bước gap-fill lúc
  startup: `async with IBKRDownloader() as dl:` → `NameError`. Nguyên nhân: import
  `from phase1_data.ibkr_downloader import IBKRDownloader as OANDARestDownloader`
  (alias còn sót lại từ thời code gốc dùng OANDA — Conv 1 đổi sang IBKR nhưng quên xoá
  alias), nhưng phần dùng biến lại gọi tên `IBKRDownloader` (không alias) → tên không
  tồn tại trong scope.
- **File:** `phase9_live/live_engine.py`
  - `start()` — gap-fill section (~line 127)
  - `_backfill_gap()` (~line 294)
- **Fix:** Bỏ alias `as OANDARestDownloader`, import thẳng
  `from phase1_data.ibkr_downloader import IBKRDownloader` ở cả 2 vị trí.
- **Ảnh hưởng:** Gap-fill khi startup chạy được bình thường — verify: cả foreground test
  và `forex-bot.service` (systemd) backfill thành công cho cả 4 symbol (EURUSD/GBPUSD/
  USDJPY/XAUUSD) × 2 timeframe (15m/1h).

---

### CHG-FX-012 | `get_position`/`get_account_balance`/`get_account_summary` lỗi "This event loop is already running"
- **Thời gian:** 2026-06-15 Conv 10
- **Tại sao:** `IBKROrderManager` chạy bên trong `asyncio.run(main())` (event loop đang
  chạy). Các sync wrapper của ib_insync — `ib.reqPositions()`, `ib.positions()`,
  `ib.reqAccountUpdates(...)`, và cả `ib.accountSummary()` (không phải `*Async`) — bên
  trong gọi `util.run()` → `loop.run_until_complete()`, raise
  `RuntimeError: This event loop is already running` khi gọi từ context async đã có
  loop chạy sẵn. Lỗi này khiến `get_position()` luôn trả `None` (vô tình "che" được vị
  thế EUR 20,000 units mở từ `test_order.py` — không close được đúng cách) và
  `get_account_balance()` luôn trả `None`/lỗi.
- **File:** `phase9_live/ibkr_order_manager.py`
  - `get_position()` — `ib.reqPositions()` + `ib.positions()` → `await
    ib.reqPositionsAsync()` (coroutine, trả list positions đã populate).
  - `get_account_balance()` / `get_account_summary()` — `ib.reqAccountUpdates(...)` →
    `await ib.accountSummaryAsync()`. **Lưu ý:** `reqAccountSummaryAsync()` (có "req")
    chỉ trigger subscription và return ngay (`[]`, chưa có data) — phải dùng
    `accountSummaryAsync()` (không "req") để subscribe + chờ + trả data đã populate.
- **Ảnh hưởng:** Verify qua `scripts/check_account.py` trên VPS — balance
  (NetLiquidation=10005.74), AvailableFunds/BuyingPower/TotalCashValue/
  GrossPositionValue, open positions, open orders, recent fills đều đọc đúng. Vị thế
  EUR còn sót từ `test_order.py` (do bug này khiến close-step bị bỏ qua) đã được đóng và
  confirm flat (0 open positions).

---

### CHG-FX-013 | Switch `forex-bot.service`: `main.py paper` (internal simulation) → `main.py live` (real order routing trên IBKR demo account DUQ686904)
- **Thời gian:** 2026-06-15 Conv 10
- **Tại sao:** Sau khi fix CHG-FX-010/011/012 và verify end-to-end qua
  `scripts/test_order.py` (place→fill→query→close) + foreground `main.py live` chạy
  sạch tới "All subscriptions done — waiting for live bars ...", quyết định chuyển bot
  production sang `main.py live` (đặt lệnh thật qua IBKR API trên paper/demo account —
  KHÔNG phải tiền thật, vẫn port 7497/DUQ686904) thay vì `main.py paper` (chỉ mô phỏng
  nội bộ, không gửi lệnh qua IBKR).
- **File:** `/etc/systemd/system/forex-bot.service` (trên VPS) —
  `ExecStart=... main.py paper` → `ExecStart=... main.py live`
  (`sudo sed -i 's/main.py paper/main.py live/' /etc/systemd/system/forex-bot.service`)
- **Deploy:** `systemctl daemon-reload && systemctl restart forex-bot`
- **Verify (2026-06-15 10:04 UTC):** `systemctl status forex-bot` → `active (running)`,
  PID 151331, `python3 main.py live`. `scalper.log`: backfill 4 symbol × 2 TF OK, "No
  open positions to restore", 8/8 subscriptions done, `_monitoring_loop` chạy mỗi phút
  với balance thật từ IBKR (`{'balance': 9999.64→9997.61, 'open_positions': 0,
  'daily_pnl_pct': 0.0, 'api_errors': 0}`).
- **Ảnh hưởng:** Từ giờ mọi signal pass đủ 5 layers sẽ được `place_order()` gửi thật lên
  IBKR IDEALPRO (demo account, không mất tiền thật) — SL/TP đặt như child orders. Theo
  dõi qua `scripts/check_account.py` (đọc balance/position/order/fill, không cần login
  web — tránh session conflict với Gateway).

---

### CHG-FX-014 | SL/TP order bị IBKR reject "Error 201: Parent order is being cancelled" — đổi từ bracket (`parentId`) sang OCA group

- **Thời gian:** 2026-06-15 Conv 10
- **Tại sao:** Test `scripts/test_order.py` (MARKET BUY + SL/TP) lần đầu — main order
  fill bình thường, nhưng SL order (#5) và TP order (#6) đều bị IBKR reject ngay:
  `Error 201, reqId 5/6: Order rejected - reason: Parent order is being cancelled`. Root
  cause: `place_order()` gửi SL/TP như child orders với `parentId = <main order id>` và
  `transmit=True`, theo kiểu "bracket order". Nhưng `MarketOrder` (main) có
  `transmit=True` mặc định (không set) → main order transmit + fill NGAY LẬP TỨC, TRƯỚC
  khi SL/TP được tạo. Khi SL/TP gửi lên với `parentId` trỏ tới 1 order đã "xong"
  (filled), IBKR coi bracket không hợp lệ → reject cả 2 child orders. Kết quả: position
  mở ra HOÀN TOÀN KHÔNG có SL/TP bảo vệ.
- **File:** `phase9_live/ibkr_order_manager.py` — `place_order()`
- **Fix:** Bỏ `parentId`/bracket. Đặt SL (`StopOrder`) và TP (`LimitOrder`) như 2 orders
  **độc lập**, cùng `ocaGroup = f"OCA_{symbol}_{order.orderId}_{timestamp}"` và
  `ocaType = 1` (Cancel With Block) — khi 1 trong 2 khớp, IBKR tự cancel order còn lại.
  Cả 2 vẫn `transmit = True` (gửi ngay, không chờ nhau).
- **Verify (2026-06-15, `scripts/test_order.py`, clientId offset=30):** MARKET BUY
  20,000 EURUSD @ 1.16118 → SL #13 (stop=1.15618) và TP #14 (limit=1.17118) đều
  `status=PreSubmitted`, xuất hiện trong `get_open_trades()`. Đóng position →
  `get_position()=None`. `cancel_order()` dọn sạch SL/TP còn lại →
  `get_open_trades() = []`.
- **Lưu ý:** Test trên Client Portal Web API (`/portfolio/{accountId}/positions/all`)
  KHÔNG thấy position/order — đây là hạn chế sync của **paper trading account** (Client
  Portal Web session khác với TWS API session mà bot dùng), không phải lỗi code. TWS
  API (port 7497, dùng bởi `IBKROrderManager`) là nguồn chính xác.
- **Ảnh hưởng:** Mọi lệnh `_execute_signal()` đặt qua `forex-bot.service` từ giờ sẽ có
  SL/TP thật trên IBKR (trước đây bị reject âm thầm — `place_order()` không raise lỗi,
  chỉ log, nên không bị phát hiện cho tới khi test thủ công).

---

### CHG-FX-015 | Thêm Web Dashboard — monitor + đóng lệnh tay qua browser

- **Thời gian:** 2026-06-15 Conv 10
- **Tại sao:** Sau khi switch `forex-bot.service` sang `main.py live` (CHG-FX-013), cần
  cách xem position/open orders/recent fills và đóng lệnh tay khi cần (vd SL/TP đặt sai,
  muốn cắt lỗ sớm) — mà KHÔNG login Client Portal web (rủi ro "competing session" làm
  IB Gateway của bot bị đăng xuất, xem CHG-FX-012/013) và KHÔNG cần SSH chạy script mỗi
  lần.
- **File mới:** `phase9_live/web_dashboard.py` — FastAPI app:
  - `IBKROrderManager(client_id_offset=40)` — connection riêng, clientId =
    IB_CLIENT_ID+40 (khác bot=20, `test_order.py`=30).
  - HTTP Basic Auth (`DASHBOARD_USER`/`DASHBOARD_PASS` trong `.env`).
  - `GET /api/state` — balance, position từng symbol trong `SYMBOLS`, open orders
    (SL/TP), 20 fill gần nhất.
  - `POST /api/close` — đóng position (`close_trade`).
  - `POST /api/cancel` — cancel order (`cancel_order`).
  - `GET /` — trang HTML auto-refresh 5s, nút **Đóng**/**Cancel** có `confirm()`.
- **Config:** `config/settings.py` — thêm `DASHBOARD_USER`, `DASHBOARD_PASS`,
  `DASHBOARD_CLIENT_ID_OFFSET=40`. `.env.example` — thêm
  `DASHBOARD_USER`/`DASHBOARD_PASS`. `requirements.txt` — thêm `fastapi`, `uvicorn`.
- **Deploy:** Chạy qua `forex-dashboard.service` (systemd, port 8080) — xem GUIDELINE.md
  mục 12 "Web Dashboard". Truy cập `http://<VPS_IP>:8080`.
- **Lưu ý bảo mật:** HTTP (không TLS) — khuyến nghị SSH tunnel (`ssh -L
  8080:localhost:8080 root@69.12.65.42`) thay vì mở port 8080 ra internet, hoặc thêm
  Nginx + Let's Encrypt.
- **Ảnh hưởng:** Đã deploy + verify trên VPS — truy cập `http://<VPS_IP>:8080`
  login thành công, dashboard load OK.

---

### CHG-FX-016 | Web Dashboard lỗi "attached to a different loop" khi connect IB Gateway — chạy IB() trên event loop riêng (thread riêng)

- **Thời gian:** 2026-06-15 Conv 10
- **Triệu chứng:** Sau khi deploy CHG-FX-015, `forex-dashboard.service` crash-loop
  (`exit-code 3`). Log: `ConnectionError: Cannot connect to IB Gateway at
  127.0.0.1:7497`, nguyên nhân thật là
  `RuntimeError: ... Future ... attached to a different loop` khi
  `ib_insync.IB().connectAsync()` chạy trong lifespan của uvicorn.
- **Root cause:** `ib_insync.IB()` tạo transport/protocol gắn chặt với 1 event-loop
  instance tại thời điểm `connectAsync()`. Uvicorn chạy app trên loop riêng của nó
  (uvloop hoặc asyncio) — khác với `asyncio.run()` đơn giản mà `live_engine.py`/
  `test_order.py` dùng. Thử fix bằng `nest_asyncio.apply()` (thêm vào
  `ibkr_order_manager.py`) KHÔNG giải quyết được — lỗi vẫn xảy ra. Thử ép
  `uvicorn --loop asyncio` cũng KHÔNG đủ.
- **Fix:** `phase9_live/web_dashboard.py` — chạy `IBKROrderManager`/`IB()` trên 1
  event loop riêng (`asyncio.new_event_loop()`) trong 1 thread riêng
  (`threading.Thread(..., daemon=True)` chạy `loop.run_forever()`), giống cách
  `test_order.py` có loop riêng của tiến trình riêng. Mọi endpoint FastAPI gọi
  sang qua helper `_call_ib(coro)` dùng
  `asyncio.run_coroutine_threadsafe(coro, _ib_loop)` + `asyncio.wrap_future()`.
  `nest_asyncio.apply()` trong `ibkr_order_manager.py` giữ lại (không gây hại,
  không cần thiết với fix này nhưng để phòng hờ).
- **Đã verify:** Restart `forex-dashboard.service` → `active (running)`, không
  crash-loop, log không còn lỗi "different loop", truy cập
  `http://<VPS_IP>:8080` login thành công, dashboard hiển thị dữ liệu.
- **Ảnh hưởng:** Chỉ `web_dashboard.py` — không đụng `forex-bot.service` /
  `ibkr_order_manager.py` logic đặt lệnh (CHG-FX-014 vẫn nguyên).

---

### CHG-FX-017 | Dashboard trả 500 Internal Server Error khi login — `secrets.compare_digest` không hỗ trợ non-ASCII

- **Thời gian:** 2026-06-15 Conv 10
- **Triệu chứng:** Sau khi fix CHG-FX-016, đăng nhập dashboard → `401 Unauthorized`
  lần đầu (do nhập sai), sau đó MỌI request (kể cả refresh) → `500 Internal Server
  Error`. Log: `TypeError: comparing strings with non-ASCII characters is not
  supported` tại `check_auth()` → `secrets.compare_digest(credentials.password,
  DASHBOARD_PASS)`.
- **Root cause:** `.env` trên VPS vẫn còn giá trị placeholder gốc
  `DASHBOARD_PASS=<mật khẩu mạnh của bạn>` (có dấu tiếng Việt, non-ASCII), và bị
  thêm trùng 2 lần (`DASHBOARD_USER`/`DASHBOARD_PASS` xuất hiện 2 lần trong
  `.env`). `secrets.compare_digest()` chỉ chấp nhận `str` ASCII-only hoặc `bytes`
  — gặp ký tự có dấu → raise `TypeError` → FastAPI trả 500 cho **mọi** request
  (không phải lỗi do user/pass sai).
- **Fix:**
  1. `phase9_live/web_dashboard.py` — `check_auth()`: encode cả 2 chuỗi sang
     `utf-8` bytes trước khi `secrets.compare_digest()`, hỗ trợ password có dấu
     tiếng Việt mà không lỗi.
  2. VPS `.env`: xoá các dòng `DASHBOARD_USER`/`DASHBOARD_PASS` trùng/placeholder,
     set lại password ASCII thật (vd `MatKhau123!`).
- **Đã verify:** Login dashboard thành công, **đóng lệnh tay (Đóng) qua web hoạt
  động đúng**.
- **Ảnh hưởng:** Chỉ `web_dashboard.py` (auth) + `.env` trên VPS (không có trong
  repo, không sync qua rsync).

---

## Conv 11 — Dashboard: hiển thị đầy đủ position (giá/PnL/leverage/SL/TP), fix cross-client order visibility + hang (2026-06-15)

---

### CHG-FX-018 | Bảng "Position đang mở" thiếu giá hiện tại / PnL / leverage / SL / TP

- **Thời gian:** 2026-06-15 Conv 11
- **Tại sao:** Dashboard (CHG-FX-015) chỉ hiển thị Symbol/Side/Units/Avg cost — không
  thấy giá hiện tại, lãi/lỗ tạm tính, leverage, hay SL/TP đang bảo vệ position, phải
  SSH/đọc log mới biết.
- **File:**
  - `phase9_live/ibkr_order_manager.py` — `get_position()`: trả thêm
    `market_price`, `unrealized_pnl`, `value_usd` (đọc từ `ib.reqMktData`/
    `portfolio()`).
  - `phase9_live/web_dashboard.py`:
    - `_fetch_state()`: với mỗi position, quét `open_orders` (từ
      `get_open_trades()`) cùng symbol để gắn `sl_price` (order `STP`) và
      `tp_price` (order `LMT`); tính `leverage = value_usd / balance`.
    - `HTML_PAGE`: bảng "Position đang mở" thêm cột **Giá hiện tại, PnL,
      Leverage, SL, TP** (PnL/SL/TP tô màu xanh/đỏ theo long/short, `--` khi
      `null`).
- **Đã verify:** Dashboard hiển thị đúng — GBPUSD LONG 20000, avg cost 1.34385,
  giá hiện tại 1.34374, PnL -2.10 (đỏ), Leverage 2.69x, SL 1.33874, TP 1.35374 —
  số liệu khớp với order SL/TP thật đặt qua `place_order()`.
- **Ảnh hưởng:** Chỉ hiển thị, không thay đổi logic đặt/đóng lệnh.

---

### CHG-FX-019 | SL/TP do bot đặt không hiện trong "Open orders"; cancel order trả `ok:true` nhưng không có tác dụng (Error 10147)

- **Thời gian:** 2026-06-15 Conv 11
- **Triệu chứng 1:** Bảng "Open orders (SL/TP)" trống dù bot/test script đã đặt SL/TP
  thật (xác nhận qua `scripts/test_order.py`).
- **Root cause 1:** `ib.openTrades()` chỉ trả order của **chính clientId đang
  connect**. Dashboard connect bằng clientId riêng (offset 40) khác bot (offset 20)
  / test script (offset 30) → không thấy SL/TP do client khác đặt.
- **Fix 1:** `IBKROrderManager.get_open_trades()` — gọi
  `self._ib.reqAllOpenOrders()` + `await asyncio.sleep(0.5)` trước
  `self._ib.openTrades()` (TWS gửi snapshot open orders của **mọi** clientId về
  connection hiện tại).
- **Triệu chứng 2:** Sau fix 1, order đã `Cancelled`/đã fill từ trước vẫn hiện trong
  `get_open_trades()` ("ma"), và cancel order này → `Error 10147, reqId X: OrderId X
  that needs to be cancelled is not found`.
- **Root cause 2:** `wrapper.trades`/`wrapper.permId2Trade` (cache nội bộ
  ib_insync) giữ entry cũ với status cũ từ trước khi gọi `reqAllOpenOrders()`.
- **Fix 2:** `get_open_trades()` — `self._ib.wrapper.trades.clear()` +
  `self._ib.wrapper.permId2Trade.clear()` trước mỗi lần `reqAllOpenOrders()`, đảm
  bảo snapshot mới hoàn toàn.
- **Triệu chứng 3:** Bấm "Cancel" trên dashboard cho order do client khác đặt →
  `POST /api/cancel` trả `{"ok": true}` (vì `cancel_order()` optimistic, không verify
  server-side) nhưng order **vẫn còn** sau refresh, kèm `Error 10147` trong log.
- **Root cause 3:** IB Gateway từ chối cancel order của clientId khác theo mặc định.
- **Fix 3 (config, không phải code):** IB Gateway → Configure → Settings → API →
  Settings → **Master API client ID = 41** (clientId của dashboard) — cho phép
  dashboard có quyền xem/cancel order của mọi client. (Lưu ý: setting này dường
  như cần **restart IB Gateway** để áp dụng đầy đủ cho quyền cancel — xem CHG-FX-020.)
- **Workaround khi cancel cross-client vẫn bị 10147 (Master Client ID chưa có hiệu
  lực đầy đủ):** `scripts/cancel_orphan_orders.py <orderId...>` — connect lại bằng
  **đúng clientId đã đặt order** (offset=30, giống `test_order.py`/
  `test_orders_batch.py`) rồi cancel — same-client cancel luôn thành công.
- **Đã verify:** `test_orders_batch.py` (2 MARKET + 2 LIMIT, đủ SL/TP, 10 order) → cả
  10 order hiện đúng trong "Open orders" với `order_type`/`price` chính xác. Cancel
  cross-client từ dashboard bị 10147 → `cancel_orphan_orders.py` (offset=30) cancel
  sạch toàn bộ 10 order, `get_open_trades() = []`.
- **Ảnh hưởng:** `get_open_trades()` (dùng bởi dashboard + mọi script test) giờ thấy
  order của TẤT CẢ client — xem thêm side-effect ở CHG-FX-020 (cleanup loop cancel
  nhầm order client khác). `forex-bot.service`/`live_engine` dùng
  `order_manager.py` riêng, KHÔNG gọi hàm này → không ảnh hưởng.

---

### CHG-FX-020 | Dashboard treo vô hạn ("Đang tải..." không bao giờ xong) sau khi đóng lệnh; test script cleanup cancel nhầm order của dashboard

- **Thời gian:** 2026-06-15 Conv 11
- **Triệu chứng 1:** Sau khi bấm "Đóng" GBPUSD trên dashboard (tạo order #160, sau đó
  bị Cancelled — Error 10349), dashboard hiển thị "Đang tải..." mãi không xong (~21
  phút), `/api/state` không trả lỗi cũng không trả data. `restart
  forex-dashboard.service` cũng bị stuck ở "Waiting for connections to close"/
  "Waiting for background tasks to complete" — phải `pkill -9 -f web_dashboard` mới
  start lại được.
- **Root cause 1:** `_call_ib(coro)` dùng `await asyncio.wrap_future(fut)` KHÔNG
  timeout — nếu 1 lệnh gọi IB (chạy trong `_ib_loop`/thread riêng) bị stuck vô thời
  hạn, `await` không bao giờ trả về → giữ `_lock` mãi → MỌI `/api/state` sau đó
  hang; uvicorn graceful shutdown cũng chờ task này nên restart bị treo.
- **Fix 1:** `phase9_live/web_dashboard.py` — `_call_ib(coro, timeout=10.0)` bọc
  `asyncio.wait_for(..., timeout=10)`. Hết timeout → log error + raise
  `HTTPException(503)`; `_lock` được giải phóng ngay, request sau vẫn chạy bình
  thường (frontend hiện "Lỗi tải dữ liệu: ..." thay vì treo "Đang tải...").
- **Triệu chứng 2:** `scripts/test_orders_batch.py` đặt 2 MARKET + 2 LIMIT (10
  order). Trong lúc script đang ở bước cleanup (gọi `get_open_trades()` →
  reqAllOpenOrders thấy CẢ order #160 của dashboard, clientId 41), cleanup loop cũ
  cancel TẤT CẢ order trong `get_open_trades()` → cancel nhầm order #160 (đang
  PendingSubmit) của dashboard → race condition, đây cũng là nguyên nhân gián tiếp
  gây Triệu chứng 1.
- **Root cause 2:** Cleanup loop dùng `get_open_trades()` (cross-client từ
  CHG-FX-019) làm danh sách để cancel, nhưng không lọc theo orderId do CHÍNH script
  đặt.
- **Fix 2:** `scripts/test_orders_batch.py` — thu thập `placed_order_ids` (entry +
  `sl_order_id` + `tp_order_id` từ kết quả `place_order()` của CHÍNH script) ngay
  sau khi đặt lệnh; cleanup loop chỉ `cancel_order()` các orderId nằm trong
  `placed_order_ids`, các order khác (của client khác) bị `skip` + log.
- **Verify:** `python3 -m py_compile` OK cho cả 2 file. Chưa re-run
  `test_orders_batch.py` để kiểm tra end-to-end (sẽ test ở lần chạy kế tiếp).
- **Ảnh hưởng:** `web_dashboard.py` (mọi endpoint qua `_call_ib`) +
  `scripts/test_orders_batch.py`. Không đụng `forex-bot.service`.

---

### CHG-FX-021 | "Position đang mở" thiếu AUDUSD (và symbol khác ngoài SYMBOLS)

- **Thời gian:** 2026-06-15 Conv 11
- **Triệu chứng:** Sau `test_orders_batch.py`, dashboard chỉ hiện position GBPUSD
  (đầy đủ giá/PnL/leverage/SL/TP), KHÔNG hiện AUDUSD dù AUDUSD có position mở + SL/TP
  order #107/#108 đang open.
- **Root cause:** `_fetch_state()` build positions bằng `for sym in SYMBOLS: pos =
  await _om.get_position(sym)`. `SYMBOLS = _p["symbols"]` (`config/settings.py`,
  theo `_PROFILES`) chỉ chứa các symbol bot dùng để trade (vd
  `["EURUSD","GBPUSD","USDJPY","XAUUSD"]`) — KHÔNG có AUDUSD/USDCAD/NZDUSD (các symbol
  này chỉ dùng trong `test_orders_batch.py`) → position AUDUSD không bao giờ được
  query/hiển thị.
- **Fix:**
  - `phase9_live/ibkr_order_manager.py`:
    - Thêm `_IBKR_SYMBOL_MAP_REV = {pair: sym for sym, pair in
      IBKR_SYMBOL_MAP.items()}` (module-level, reverse map `(ib_symbol, currency) ->
      internal symbol`, vd `("AUD","USD") -> "AUDUSD"`).
    - Refactor logic tính `unrealized_pnl`/`value_usd`/dict trả về của
      `get_position()` thành helper chung `_position_dict(symbol, units, avg_cost)`.
    - Thêm `get_all_positions()` — gọi `reqPositionsAsync()` 1 lần, lặp TOÀN BỘ
      position `CASH` có `units != 0` (không giới hạn theo `IBKR_SYMBOL_MAP` của
      `SYMBOLS`), resolve symbol qua `_IBKR_SYMBOL_MAP_REV.get((c.symbol,
      c.currency), f"{c.symbol}{c.currency}")`, trả `List[Dict]` cùng shape với
      `get_position()`.
  - `phase9_live/web_dashboard.py` — `_fetch_state()`: thay `for sym in SYMBOLS: pos
    = await _om.get_position(sym)` bằng `for pos in await _om.get_all_positions():`
    (giữ nguyên phần enrich SL/TP/leverage). Bỏ import `SYMBOLS` (không còn dùng).
- **Verify:** `python3 -m py_compile phase9_live/ibkr_order_manager.py
  phase9_live/web_dashboard.py` OK. Đã deploy + verify trên VPS — AUDUSD hiện đầy đủ
  avg_cost/market_price/PnL/leverage/sl_price/tp_price trên dashboard.
- **Ảnh hưởng:** Chỉ `web_dashboard.py` (`/api/state`) — không đụng
  `forex-bot.service`/`live_engine.py`. Position của BẤT KỲ symbol nào (kể cả ngoài
  `SYMBOLS`) giờ sẽ hiện trong "Position đang mở" nếu có units != 0.

---

### CHG-FX-022 | Nút "Cancel" trên dashboard không hoạt động với order cross-client

- **Thời gian:** 2026-06-15 Conv 11
- **Triệu chứng:** Bấm "Cancel" trên dashboard cho 1 open order (đặt bởi clientId
  khác, vd test script clientId=31) — `/api/cancel` trả `{"ok": true}` (hoặc log
  "không tìm thấy order") nhưng order KHÔNG biến mất, lần `/api/state` kế tiếp vẫn
  thấy order đó.
- **Root cause:** `cancel_order()` (`ibkr_order_manager.py`) tìm order bằng
  `self._ib.trades()` — cache LOCAL của connection hiện tại (clientId=41) —
  KHÔNG gọi `reqAllOpenOrders()` để refresh trước như `get_open_trades()` đã làm.
  → Order do client khác đặt có thể không có trong cache tại thời điểm cancel
  → log "không tìm thấy order #X" → return `False`.
  Ngoài ra, ngay cả khi tìm thấy, `self._ib.cancelOrder(trade.order)` là
  fire-and-forget: log "Cancelled order #X" và return `True` ngay, KHÔNG verify
  IB server có thực sự accept cancel hay không (Error 10147 không raise exception
  ở bước này) → `/api/cancel` báo `ok:true` nhưng order vẫn còn sống trên IB.
- **Fix:** `phase9_live/ibkr_order_manager.py` — `cancel_order()`:
  - Clear `wrapper.trades`/`permId2Trade` + gọi `reqAllOpenOrders()` +
    `asyncio.sleep(0.5)` trước khi tìm order theo `orderId` (giống
    `get_open_trades()`) — đảm bảo thấy được order của MỌI clientId.
  - Sau khi gọi `cancelOrder()`, `sleep(1.0)` rồi tìm lại order, kiểm tra
    `orderStatus.status`:
    - Nếu đã `Cancelled`/`ApiCancelled`/`PendingCancel`/`Filled`/`Inactive`, hoặc
      không còn trong `trades()` nữa → return `True`.
    - Nếu vẫn `PreSubmitted`/`Submitted` → IB server đã từ chối cancel (vd Error
      10147, do Master Client ID chưa đúng) → log warning + return `False`.
- **Verify:** `python3 -m py_compile phase9_live/ibkr_order_manager.py` OK. Đã
  deploy lên VPS + restart `forex-dashboard.service`. **Test thực tế: FAIL** —
  xem CHG-FX-023 (cancel cross-client vẫn không finalize, `PendingCancel` revert
  về `PreSubmitted`).
- **Ảnh hưởng:** Chỉ `cancel_order()` — không đụng `get_open_trades()`,
  `close_trade()`, hay `live_engine.py`.

---

### CHG-FX-023 | [BLOCKER, CHƯA FIX] Cancel cross-client vẫn fail: `PendingCancel` → revert `PreSubmitted` dù đã set `OverrideTwsMasterClientID`

- **Thời gian:** 2026-06-15 Conv 11
- **Trạng thái:** 🔴 **OPEN — chưa fix được**, đang debug.
- **Triệu chứng:** Sau khi deploy CHG-FX-022, bấm "Cancel" trên dashboard
  (clientId=41) cho order đặt bởi clientId=31
  (`scripts/place_test_cancel_order.py`, order #162 và #166, NZDUSD BUY LIMIT
  20000 units):
  - `cancel_order()` nay TÌM ĐƯỢC order (fix CHG-FX-022 hoạt động đúng phần này).
  - Gọi `cancelOrder()` → IB trả status `PendingCancel` → `cancel_order()` return
    `True`.
  - Nhưng ở lần `reqAllOpenOrders()` kế tiếp (vd dashboard `/api/state` refresh),
    order REVERT lại `PreSubmitted` — order KHÔNG biến mất, dashboard vẫn hiện.
  - Lặp lại cancel nhiều lần → cùng pattern: `PendingCancel` rồi lại
    `PreSubmitted`.
- **Phân tích root cause:** IB Gateway/TWS chỉ cho phép 1 client cancel order của
  client khác nếu client đó được gán **API → Master Client ID** đúng. Đây không
  phải lỗi code Python — `cancelOrder()` được gửi đi nhưng server-side reject âm
  thầm (không raise exception, chỉ revert status).
- **Đã thử fix (KHÔNG thành công):**
  1. Sửa `/opt/ibc/config.ini`: `OverrideTwsMasterClientID=` (rỗng) →
     `OverrideTwsMasterClientID=41`. Xác nhận đã ghi đúng
     (`grep -n "OverrideTwsMasterClientID" /opt/ibc/config.ini` →
     `360:OverrideTwsMasterClientID=41`).
  2. Restart toàn bộ chain: `ibgateway.service` → `forex-bot.service` →
     `forex-dashboard.service` (xác nhận `ibgateway` active từ
     `2026-06-15 17:01:39 UTC`).
  3. Test lại cancel order #162/#166 SAU restart → **vẫn `PendingCancel` →
     `PreSubmitted`**, không khác gì trước.
  4. Kiểm tra `/root/Jts/jts.ini` (file lưu API config của IB Gateway) — dump
     toàn bộ, có `[IBGateway]`, `[Logon]`, `[Communication]`,
     `[u:cenbndpbdjoolbjombimejgpgbliahdnipoaahlk]` — **KHÔNG có key nào liên
     quan "master"/"client"** → không có evidence là `OverrideTwsMasterClientID`
     của IBC đã thực sự apply vào config Gateway.
- **Giả thuyết còn lại (chưa kiểm tra):**
  - IBC apply `OverrideTwsMasterClientID` bằng cách tự động điều khiển GUI
    Settings dialog của Gateway SAU khi login xong — có thể cần restart Gateway
    + đợi lâu hơn (login + điều hướng UI ảo) trước khi setting có hiệu lực.
  - Cần check log của IBC (`/opt/ibc/logs/` hoặc tương đương) để tìm dòng xác
    nhận IBC đã set Master Client ID — nếu không có dòng nào, có thể IBC version
    đang dùng không support đúng cách qua headless/Xvfb.
  - Fallback nếu IBC route không work: set Master Client ID = 41 thủ công qua
    VNC (Gateway GUI → Configure → API → Settings → "Master API client ID").
- **Việc cần làm tiếp:**
  1. Restart `ibgateway.service` 1 lần nữa, đợi ≥60s, check lại `jts.ini` +
     log IBC.
  2. Nếu vẫn không thấy setting trong `jts.ini` → set thủ công qua VNC.
  3. Sau khi Master Client ID có hiệu lực thật → test lại cancel #162/#166 (hoặc
     order test mới) bằng dashboard.
  4. Review lại `cancel_order()`: hiện đang coi `PendingCancel` là "thành công"
     (`return True`) — nhưng thực tế `PendingCancel` có thể revert. Cần poll lại
     sau vài giây để xác nhận chuyển hẳn sang `Cancelled`/`ApiCancelled` (hoặc
     biến mất khỏi `trades()`) mới return `True`; nếu revert về
     `PreSubmitted`/`Submitted` → return `False`.
  5. Cleanup order #162/#166 (NZDUSD, còn pending, harmless) bằng
     `scripts/cancel_orphan_orders.py 162 166` (clientId offset=30 — same-owner
     cancel, đã biết hoạt động).
- **Ảnh hưởng:** Dashboard "Cancel" button vẫn KHÔNG dùng được cho order
  cross-client (vd SL/TP do `forex-bot.service` clientId=21 đặt, cancel từ
  dashboard clientId=41) — đây là use case chính của CHG-FX-019/022, nên blocker
  này cần fix trước khi coi cancel feature là "done".

---

### CHG-FX-024 | Fix CHG-FX-023: cancel "as owner" (connect tạm bằng đúng clientId gốc) + nút "Cancel toàn bộ"

- **Thời gian:** 2026-06-15 Conv 11
- **Trạng thái:** ✅ Verify thành công trên VPS.
- **Bối cảnh:** CHG-FX-023 xác định cancel cross-client từ dashboard
  (clientId=41) chỉ đưa order về `PendingCancel` và KHÔNG finalize, dù Master
  API Client ID=41 + Read-Only API=off đã set đúng trên IB Gateway (xác nhận
  qua VNC). Ngược lại, cancel bằng ĐÚNG clientId đã đặt order
  (`cancel_orphan_orders.py`, same-owner) finalize thành `Cancelled` ngay lập
  tức.
- **Fix:** `phase9_live/ibkr_order_manager.py`:
  - `get_open_trades()`: thêm field `"clientId": t.order.clientId` vào mỗi
    order trả về — biết order do clientId nào đặt.
  - Hàm mới `cancel_order_as_owner(order_id, raw_client_id)`: connect TẠM tới
    IB Gateway bằng `clientId=raw_client_id` (đúng clientId gốc), tìm order,
    `cancelOrder()`, verify status, disconnect. Trả về:
    - `True` — cancel thành công (status `Cancelled`/`ApiCancelled`/`Filled`/
      `Inactive`, hoặc order biến mất khỏi `trades()`).
    - `False` — connect được nhưng cancel không finalize.
    - `None` — KHÔNG connect được bằng `raw_client_id` (Error 326 — clientId
      đang được 1 process khác dùng, vd `forex-bot.service` clientId=21 chạy
      24/7) → caller cần fallback sang cancel cross-client thường.
  - `phase9_live/web_dashboard.py`:
    - Endpoint mới `POST /api/cancel_all`: lặp qua toàn bộ `open_orders`.
      - Order do CHÍNH dashboard đặt (`clientId == IB_CLIENT_ID +
        DASHBOARD_CLIENT_ID_OFFSET`) → cancel trực tiếp (`cancel_order()`).
      - Order do client khác đặt → `cancel_order_as_owner()`. Nếu clientId
        gốc đang busy (return `None`) → fallback `cancel_order()` cross-client
        (có thể không finalize, nhưng vẫn trả kết quả thật).
      - Response: `{"results": [{"orderId", "symbol", "ok", "method"}]}` —
        `method` = `"direct"` | `"as-owner"` | `"cross-client-fallback"`.
    - UI: nút **"Cancel toàn bộ"** cạnh heading "Open orders (SL / TP)" (chỉ
      hiện khi có open order). Click → confirm → gọi `/api/cancel_all` →
      alert tổng kết (order nào cancel được + bằng method nào, order nào
      chưa).
  - `get_current_price()` (fix phụ, phát hiện trong lúc test): fallback dùng
    `ticker.close` nếu `bid`/`ask` không có (account thiếu live market data
    subscription cho symbol đó, vd NZDUSD trả `bid=ask=-1`).
- **Verify:** Deploy lên VPS, restart `forex-bot` + `forex-dashboard`. Đặt
  order test #174 (NZDUSD, clientId=31, `place_test_cancel_order.py`). Bấm
  "Cancel toàn bộ" trên dashboard (clientId=41) →
  `cancel_order_as_owner` connect tạm bằng clientId=31 (không process nào
  đang dùng) → `#174 status=Cancelled -> ok=True`. Order biến mất khỏi Open
  orders. **Cross-client cancel qua dashboard hoạt động đúng cho order của
  client KHÔNG đang chạy** (test scripts đã dừng).
  - **Chưa test case order do `forex-bot.service` (clientId=21, đang chạy
    24/7) đặt** — trường hợp này `cancel_order_as_owner` sẽ trả `None` (Error
    326, clientId 21 đang busy) → fallback cross-client thường → nhiều khả
    năng vẫn `PendingCancel` không finalize (chưa kiểm chứng). Đây vẫn là use
    case chính của CHG-FX-019 (cancel SL/TP của bot) — cần test khi có SL/TP
    order thật của bot đang mở.
- **Ảnh hưởng:** `ibkr_order_manager.py` (thêm field + hàm mới, không đổi hàm
  cũ), `web_dashboard.py` (endpoint + UI mới, không đổi `/api/cancel` cũ).

---

### CHG-FX-025 | Áp dụng luồng "as-owner / fallback" của CHG-FX-024 cho nút Cancel từng order

- **Thời gian:** 2026-06-15 Conv 11
- **Trạng thái:** ✅ Code xong, `py_compile` OK. Chưa deploy/verify trên VPS.
- **Bối cảnh:** CHG-FX-024 mới chỉ áp dụng "cancel as owner + fallback" cho
  nút "Cancel toàn bộ" (`/api/cancel_all`). User yêu cầu nút **Cancel riêng
  từng Open Order** (`/api/cancel` + `cancelOrder(orderId)`) cũng dùng cùng
  luồng đó, không chỉ cancel cross-client thường (dễ bị `PendingCancel` kẹt
  — CHG-FX-023).
- **Fix:** `phase9_live/web_dashboard.py`:
  - Tách logic cancel-1-order ra hàm chung `_cancel_order_dict(order)`:
    nếu `order["clientId"] == own_client_id` → `cancel_order()` trực tiếp
    (`method="direct"`); ngược lại → `cancel_order_as_owner()` (`method=
    "as-owner"`), nếu trả `None` (clientId gốc đang busy) → fallback
    `cancel_order()` cross-client (`method="cross-client-fallback"`).
  - `/api/cancel`: tìm order theo `order_id` trong `get_open_trades()`, nếu
    không còn → trả `{"ok": true, "method": "already-gone"}`; nếu còn → gọi
    `_cancel_order_dict(order)`.
  - `/api/cancel_all`: giữ nguyên hành vi, refactor để gọi
    `_cancel_order_dict(o)` cho từng order (giảm trùng code).
  - JS `cancelOrder(orderId)`: đọc `r.ok`/`r.method` từ response; nếu
    `!r.ok` → alert báo chưa cancel được + method đã thử.
- **Verify (cần làm):** Deploy lên VPS, restart `forex-dashboard`. Đặt 1 order
  test mới qua `place_test_cancel_order.py` (clientId=31, process đã dừng sau
  khi đặt xong), bấm nút "Cancel" riêng của order đó trên dashboard → kỳ vọng
  `method="as-owner"`, `ok=true`, status → `Cancelled`, biến mất khỏi Open
  orders.
- **Ảnh hưởng:** `web_dashboard.py` chỉ — không đổi `ibkr_order_manager.py`.

---

### CHG-FX-026 | Fix bug nghiêm trọng: SL/TP không bao giờ được đặt lên IBKR khi LIVE

- **Thời gian:** 2026-06-15 Conv 11
- **Trạng thái:** ✅ Code xong, `py_compile` OK. Chưa deploy/verify trên VPS
  (chưa test với tín hiệu LIVE thật).
- **Bối cảnh:** Trong lúc test "Open Orders (SL/TP)" với
  `test_orders_batch.py` (mỗi LIMIT entry tạo 3 order: entry + SL + TP, OCA
  group), user hỏi khi LIVE thật thì dashboard sẽ hiện mấy order cho 1 tín
  hiệu LIMIT. Trace `live_engine._execute_signal()` phát hiện **2 bug**:
  1. `place_order(symbol, sl_side, "STOP_MARKET", qty, stop_price=risk["sl"],
     reduce_only=True)` — `stop_price` KHÔNG phải tham số hợp lệ của
     `ibkr_order_manager.place_order()` (chữ ký dùng `price=` cho
     `STOP_MARKET`). Gọi với `stop_price=` raise `TypeError` → bị except bắt
     ở `_process_signal` (`Strategy error: ...`) → **SL không bao giờ được
     đặt lên IBKR**.
  2. `order_id = str(result.get("ordId", result.get("clOrdId", ...)))` —
     `"ordId"`/`"clOrdId"` là key kiểu OKX/cTrader cũ, IBKR trả về
     `"orderId"`. Luôn rơi vào fallback string giả
     (`f"{symbol}_{int(time.time())}"`) → `get_order(symbol, order_id)` không
     tìm thấy order thật → với LIMIT entry, `filled` luôn `False` dù entry đã
     khớp → SL/TP deferred vĩnh viễn.
  3. (Không phải bug, nhưng thiếu sót) TP **chưa từng** được đặt thành order
     trên IBKR ở cả 2 nhánh MARKET/LIMIT — chỉ tồn tại trong `risk` dict để
     log/lưu DB.
  - **Hậu quả nếu chưa fix:** mọi position LIVE chạy KHÔNG có SL/TP order
    thật trên IBKR — rủi ro lớn với tiền thật.
- **Fix:** `phase9_live/live_engine.py`, `_execute_signal()`:
  - Tính `tp_level` ngay đầu hàm (trước khi đặt entry).
  - **MARKET entry** (fill ngay): đặt entry + SL + TP trong CÙNG 1 lệnh
    `place_order(symbol, side_api, "MARKET", qty, stop_loss=risk["sl"],
    take_profit=tp_level if tp_level else None)` — `place_order()` tự gắn
    SL=StopOrder + TP=LimitOrder, OCA-linked (giống `test_orders_batch.py`,
    đã verify hoạt động).
  - **LIMIT entry**: đặt entry LIMIT riêng (chưa gắn SL/TP — chưa có
    position). `order_id = result["orderId"]` (sửa key đúng). Sau 2s, check
    `get_order()`:
    - Filled → đặt SL kèm TP cùng lúc:
      `place_order(symbol, sl_side, "STOP_MARKET", qty, price=risk["sl"],
      take_profit=tp_level if tp_level else None)` (SL = main order
      STOP_MARKET, TP = LimitOrder OCA-linked).
    - Chưa filled → log deferred như cũ (TODO: chưa có cơ chế tự đặt SL/TP
      khi LIMIT fill MUỘN sau lần check 2s này — cần theo dõi thêm ở
      `_monitoring_loop`/`_check_closed_positions` nếu phát sinh vấn đề).
- **Verify (cần làm):** Deploy lên VPS, đợi 1 tín hiệu LIVE thật (hoặc test
  thủ công qua `_execute_signal` với signal giả) → xác nhận dashboard "Open
  Orders (SL/TP)" hiện đúng SL (+TP nếu có) ngay sau khi entry fill, và
  `forex-bot.service` không log `Strategy error` liên quan `place_order`.
- **Ảnh hưởng:** `live_engine.py` chỉ — không đổi `ibkr_order_manager.py`,
  `web_dashboard.py`.

---

### CHG-FX-027 | Fix "naked position" — LIMIT entry fill MUỘN (sau 2s check) không bao giờ được gắn SL/TP + false "CLOSED" event cho LIMIT order chưa fill

- **Thời gian:** 2026-06-15 Conv 11
- **Trạng thái:** ✅ Code xong, `py_compile` OK. Chưa deploy/verify trên VPS
  (chưa test với tín hiệu LIVE thật).
- **Bối cảnh:** Sau CHG-FX-026, user hỏi tiếp về kịch bản: LIMIT entry +
  SL/TP đặt cùng lúc (như `test_orders_batch.py`) có thể bị "orphan fill" —
  TP/SL khớp trước khi entry khớp (vì cả 3 order live ngay từ đầu, không phụ
  thuộc nhau), mở vị thế sai hướng + mất bảo vệ. Khi đối chiếu với
  `live_engine.py` (đã fix ở CHG-FX-026: LIMIT entry KHÔNG gắn SL/TP ngay,
  chỉ check fill 1 lần sau 2s), phát hiện thêm **2 vấn đề còn lại**:
  1. **TODO ghi trong CHG-FX-026 chưa được giải quyết**: nếu LIMIT order
     chưa fill trong 2s đầu, code chỉ `logger.warning(...)` rồi BỎ QUÊN HOÀN
     TOÀN. Nếu order fill sau đó (vài phút/giờ sau) → position tồn tại trên
     IBKR nhưng **KHÔNG CÓ SL/TP** ("naked position") — rủi ro lỗ không giới
     hạn.
  2. **Bug khác phát hiện thêm**: `_finalize_entry` (telegram + `save_live_trade_open`
     + `position_monitor.track()`) trước đây được gọi NGAY CẢ KHI LIMIT order
     CHƯA fill (`filled=False`). Vì `position_monitor.track()` thêm symbol vào
     `open_positions` ngay, vòng `_monitoring_loop` (mỗi 60s) →
     `_check_closed_positions()` gọi `get_position(symbol)` → IBKR trả `None`
     (chưa có position thật, entry còn là LIMIT order chờ khớp) →
     `pos_open=False` → bot tưởng position "đã bị TP/SL đóng" ngay trong vòng
     60s đầu, gọi `_get_close_details()` (lấy nhầm trade gần nhất hoặc fallback
     `pos.entry, 0.0, "CLOSED"`), `save_live_trade_close()` với dữ liệu sai,
     gửi Telegram "CLOSED" giả, rồi `position_monitor.remove(symbol)` — trong
     khi LIMIT order thật vẫn còn nằm chờ trên IBKR, không còn được track.
- **Fix:** `phase9_live/live_engine.py`:
  - **`__init__`**: thêm `self._pending_limit_orders: Dict[str, Dict] = {}`
    (in-memory; biết hạn chế: mất khi bot restart giữa lúc 1 LIMIT order đang
    pending — acceptable edge-case hiện tại).
  - **`_execute_signal()`**: tách phần "đặt SL/TP cho LIMIT vừa fill" ra
    `_place_sl_tp_for_limit()`, và phần "telegram + DB + position_monitor.track"
    ra `_finalize_entry()` — dùng chung cho MARKET (fill ngay), LIMIT fill
    trong 2s đầu, và LIMIT fill muộn (qua `_check_pending_limit_orders`).
    Nếu LIMIT chưa fill sau 2s → lưu vào `_pending_limit_orders[symbol]`
    (order_id, signal, risk, qty, tp_level) — KHÔNG gọi `_finalize_entry` (nên
    KHÔNG bị track vào `open_positions` khi chưa có position thật → fix luôn
    vấn đề #2).
  - **`_check_pending_limit_orders()`** (mới) — gọi mỗi 60s từ
    `_monitoring_loop`: poll `get_order()` cho từng pending LIMIT —
    `"filled"` → đặt SL/TP + `_finalize_entry` + xoá khỏi pending (fix vấn đề
    #1); `"cancelled"`/`None` → bỏ theo dõi; `"open"` → giữ nguyên, check lại
    lần sau.
  - **`_process_signal()`**: `MAX_OPEN_POSITIONS` check giờ tính
    `len(open_positions) + len(_pending_limit_orders)` — tránh đặt thêm
    signal mới khi đã đủ slot (kể cả slot đang là LIMIT pending).
- **Verify (cần làm):** Deploy lên VPS, kích hoạt 1 tín hiệu LIMIT không fill
  trong 2s đầu (hoặc đặt giá xa để chắc chắn), xác nhận: (a) KHÔNG có Telegram
  "CLOSED" giả trong vòng 60s đầu; (b) khi giá chạm entry và order fill, log
  `_check_pending_limit_orders` báo "đã fill — SL/TP đã đặt" và dashboard "Open
  Orders (SL/TP)" hiện đúng SL+TP.
- **Ảnh hưởng:** `live_engine.py` chỉ — không đổi `ibkr_order_manager.py`,
  `web_dashboard.py`.

---

### CHG-FX-033 | Add EURJPY to AGGRESSIVE symbols (backtest PASSED)

- **Thời gian:** 2026-06-16 Conv 12
- **Trạng thái:** ✅ settings.py updated. Chưa deploy lên VPS.
- **Backtest EURJPY 15m (2024-06-16 → 2026-06-16):**
  - Trades: 100 | Winrate: 40% | Net profit: +$8,872 (+88.7%)
  - Profit Factor: 1.64 | Max DD: 10.7% | Sharpe: 3.07 | avg_R: 2.46
  - TP: 39 | SL: 29 | BE: 31 | **PASSED ✅**
- **File:** `config/settings.py`
- **Fix:** Thêm `"EURJPY"` vào `AGGRESSIVE.symbols` → 7 symbols tổng.

---

### CHG-FX-032 | Per-symbol `awaiting_confirm` config

- **Thời gian:** 2026-06-16 Conv 12
- **Trạng thái:** ✅ Code xong. Chưa backtest từng symbol với `False`.
- **Vấn đề:** `awaiting_confirm` (2-candle confirm) được hardcode True cho tất cả symbols.
  User muốn có thể tắt confirm per-symbol để test trade thêm mà không cần sửa code.
- **File:** `config/settings.py`, `phase5_entry/entry_engine.py`
- **Fix:**
  - Thêm `CONFIRM_REQUIRED: dict` vào `settings.py` — map symbol → bool.
  - Import `CONFIRM_REQUIRED` vào `entry_engine.py`.
  - Trong `evaluate()`: nếu `CONFIRM_REQUIRED.get(symbol, True) == False` → skip pending
    logic, enter ngay trên trigger candle (không cần candle N+1).
  - Nếu True → behavior giữ nguyên như cũ (2-candle confirm).
- **Default:** Tất cả symbols = `True` (an toàn). Chỉnh từng symbol trong `settings.py`.
- **Cảnh báo:** Khi set `False` → phải backtest lại symbol đó trước khi deploy live.
  EURUSD bị FAIL khi bỏ confirm (winrate 30%). USDJPY compounding inflated kết quả.

---

### CHG-FX-031 | Implement breakeven (SL → entry) cho live trading khi đạt 1R profit

- **Thời gian:** 2026-06-16 Conv 12
- **Trạng thái:** ✅ Code xong. Chưa deploy/verify trên VPS.
- **Vấn đề:** Breakeven (SL dời về entry khi giá đạt 1R profit) đã có trong backtest
  (`_update_trade()` dòng 409/434) nhưng **không có trong live trading**. Bot IBKR
  dựa hoàn toàn vào stop order đặt sẵn trên broker — không có logic trail SL trong code.
- **File:** `phase9_live/live_engine.py`
- **Fix:** Thêm method `_check_breakeven_live()` — được gọi từ `_monitoring_loop()` mỗi 60s:
  - LONG: `current_price >= entry + sl_dist` → gọi `modify_trade_sl(order_id, entry)`
  - SHORT: `current_price <= entry - sl_dist` → gọi `modify_trade_sl(order_id, entry)`
  - Đặt `pos.be_set = True` sau khi dời SL thành công (chỉ chạy 1 lần / position)
  - Gửi Telegram `🛡 [LIVE] Breakeven set` khi SL được dời
- **Ảnh hưởng:** Sau khi 1R profit, worst case là hoà vốn thay vì thua lỗ.

---

### CHG-FX-029 | Fix SL sai phía cho SHORT/LONG khi swing level nằm trong entry zone

- **Thời gian:** 2026-06-16 Conv 12
- **Trạng thái:** ✅ Code xong, `py_compile` OK. Chưa deploy/verify trên VPS.
- **Bối cảnh:** Signal GBPUSD SHORT tracker row — sl=1.340527, tp=1.339927, entry~1.341128
  → SL nằm DƯỚI entry cho lệnh SHORT (đúng ra SL phải TRÊN entry). Biên độ sl↔tp
  chỉ 6 pip, bị quét trong 1 nến 15m.
- **Root cause:** `calc_sl` SHORT dùng `last_swing_high + buffer` nhưng `last_swing_high`
  (1.340125) nằm bên dưới OB entry zone midpoint (1.341128) → SL (1.340527) < entry
  → inverted SL. Clone pattern từ OKX project (đã fix trước đó).
- **Fix:** `phase6_risk/risk_engine.py` — `calc_sl()`:
  - Thêm parameter `entry: Optional[float] = None`
  - LONG: nếu swing sl >= entry → fallback `entry - atr * 2`
  - SHORT: nếu swing sl <= entry → fallback `entry + atr * 2`
  - Log debug khi fallback xảy ra
  - `evaluate()`: truyền `entry=entry` vào `calc_sl()`
- **Ảnh hưởng:** `risk_engine.py` — SL luôn đúng phía entry. Signal có sl sai phía
  trước đây sẽ dùng ATR fallback (~20-40 pip cho GBPUSD 15m) thay vì 2-6 pip inverted.
  RR filter (`MIN_RR=1.5`) vẫn chạy sau → signal quá rộng SL có thể bị reject nếu
  TP target không đủ xa.

---

### CHG-FX-028 | Auto-reconnect sau IB Gateway daily restart (~00:30 UTC)

- **Thời gian:** 2026-06-16 Conv 12
- **Trạng thái:** ✅ Code xong, `py_compile` OK. Chưa deploy/verify trên VPS.
- **Bối cảnh:** IBC restart IB Gateway mỗi ngày lúc ~00:30 UTC. ib_insync
  connection drop nhưng Python process (forex-bot, forex-dashboard) vẫn alive
  (systemd không restart) → toàn bộ IB method call fail `Not connected` cho đến
  khi restart tay. Dashboard trả `{"balance": null, "positions": [], ...}`.
- **Root cause:** `IBKROrderManager` không có auto-reconnect — mỗi method gọi
  `self._ib.*` trực tiếp, không kiểm tra connection trước. Sau khi IB GW restart,
  `self._ib.isConnected()` → False, mọi call throw nội bộ hoặc trả empty.
- **Fix:** `phase9_live/ibkr_order_manager.py`
  - Thêm method `ensure_connected()` sau `_connect()`:
    ```python
    async def ensure_connected(self) -> bool:
        if self._ib is None:
            from ib_insync import IB
            self._ib = IB()
        if self._ib.isConnected():
            return True
        logger.warning("[IBKROrderManager] Not connected — attempting auto-reconnect...")
        try:
            await self._connect()
            logger.info("[IBKROrderManager] Auto-reconnect thành công")
            return True
        except Exception as e:
            logger.error(f"[IBKROrderManager] Auto-reconnect failed: {e}")
            return False
    ```
  - Thêm `if not await self.ensure_connected(): return None/[]/False` ở đầu
    `try` block của 8 method: `get_account_balance`, `get_account_summary`,
    `get_open_trades`, `place_order`, `close_trade`, `get_position`,
    `get_all_positions`, `cancel_order`, `get_closed_trades`, `get_current_price`.
- **Lưu ý:** `_connect()` đã có retry 3 lần, delay 5s — `ensure_connected()` kế
  thừa retry logic đó. ib_insync `IB()` object hỗ trợ `connectAsync()` lại sau
  disconnect mà không cần tạo object mới.
- **Ảnh hưởng:** `ibkr_order_manager.py` — sau IB GW restart, lần gọi đầu tiên
  tự reconnect trong ~15s, các lần sau bình thường. Dashboard tự phục hồi data
  sau restart mà không cần `systemctl restart forex-dashboard`.

---

## Conv 9 — Fix root cause thật: is_weekend_candle() dùng sai timezone (2026-06-15)

---

### CHG-FX-009 | `is_weekend_candle()` dùng hour/weekday theo giờ Eastern (-04:00) thay vì UTC → candle ngay sau market reopen bị validate_candle() loại bỏ âm thầm
- **Thời gian:** 2026-06-15 Conv 9
- **Tại sao:** Sau khi deploy CHG-FX-008, vẫn không có "Candle saved" cho batch
  "Bar closed" đầu tiên sau restart lúc 22:15:05 UTC (4 symbol, candle
  `@ 2026-06-14 18:00:00-04:00` = 22:00 UTC Sunday — đã mở thị trường được 1h).
  Không có exception/`_process_candle task failed` nào — vì `validate_candle()`
  return False KHÔNG log gì khi nguyên nhân là weekend filter (chỉ
  `logger.debug`, không phải warning/error).
  Root cause: `open_time` từ IBKR có `tzinfo=-04:00` (giờ Eastern), nhưng
  `is_weekend_candle()` gọi `.weekday()`/`.hour` trực tiếp trên giá trị đó mà
  không convert UTC. Với candle 22:00 UTC Sunday = 18:00 -04:00 Sunday:
  `weekday()==6 (Sunday) and hour(18) < 21` → bị tính là weekend candle → bị
  loại. Thực tế bug này filter sai TOÀN BỘ khoảng UTC Sunday 21:00 → Monday
  00:00 (3 giờ đầu mỗi tuần mở lại thị trường) cho MỌI symbol/timeframe — không
  chỉ candle live streaming, mà cả `fetch_range()`/backfill cũng gọi
  `validate_candles()` ở cuối nên cũng bị filter sạch → đây cũng là lý do
  "Backfill complete: 0 candles" lúc 22:07-22:08 (KHÔNG phải do IBKR thiếu
  data như suy đoán ban đầu).
- **File:** `phase1_data/validator.py` — `is_weekend_candle()`
- **Fix:** Thêm `if open_time.tzinfo is not None: open_time =
  open_time.astimezone(timezone.utc)` ngay đầu hàm, trước khi check
  `weekday()`/`hour`.
- **Ảnh hưởng:**
  - Deploy + restart `forex-bot.service`. Live streaming sẽ lưu được candle
    ngay từ batch tiếp theo (22:30 UTC trở đi, và mọi tuần sau này trong
    khoảng 21:00 UTC Sun → 00:00 UTC Mon).
  - Periodic backfill (1h sau) hoặc restart sẽ tự fill lại 4 candle 15m +
    1 candle 1h (21:00-21:45 UTC Sunday) đã bị mất cho EURUSD/GBPUSD/USDJPY/
    XAUUSD, vì giờ `fetch_range()` không còn filter sai nữa (miễn IBKR
    historical API có data — cần kiểm tra lại).
  - Đây là bug có từ khi port sang IBKR (ảnh hưởng mọi tuần, không chỉ tuần
    này) — historical download trước đây cũng có thể đã thiếu 3h đầu mỗi
    tuần cho mọi symbol/timeframe. Có thể cần chạy lại
    `python main.py download` (incremental) sau khi deploy để backfill các
    gap cũ trong lịch sử nếu cần dữ liệu đầy đủ cho backtest.

---

## Conv 8 — Fix candle save bị rớt sau reconnect (2026-06-14)

---

### CHG-FX-008 | `_process_candle` task bị "mất" sau lần Bar-closed đầu tiên kể từ reconnect → candle mới không được lưu vào DB
- **Thời gian:** 2026-06-14 Conv 8
- **Tại sao:** Sau watchdog force-reconnect lúc 21:00:01 UTC (Sun→Mon market reopen),
  `_process_candle` chỉ chạy thành công cho lần `has_new_bar=True` ĐẦU TIÊN của mỗi
  symbol/timeframe (log "Candle saved" xuất hiện cho candle Friday re-delivered lúc
  21:15:05). Từ lần thứ 2 trở đi (21:30, 21:45, 22:00 UTC — candle 21:15/21:30/21:45 UTC
  của EURUSD/GBPUSD/USDJPY), "Bar closed" vẫn log đều nhưng "Candle saved" KHÔNG xuất hiện,
  DB hoàn toàn không có row mới cho các open_time này — không có exception/error nào
  trong scalper.log, paper.log, hoặc journalctl. Root cause: logic schedule task quá phức
  tạp `loop = asyncio.get_event_loop(); ... run_coroutine_threadsafe(...) if not
  loop._thread_id == asyncio.get_event_loop()._thread_id else loop.create_task(...)` —
  từ lần gọi thứ 2, branch/loop reference bị sai → task được queue vào loop không chạy →
  `_process_candle` không bao giờ thực thi, im lặng vĩnh viễn.
- **File:** `phase1_data/ibkr_collector.py` — `_make_handler()` → `handler()`
- **Fix:**
  - Bỏ toàn bộ logic thread-check phức tạp, thay bằng `asyncio.ensure_future(
    self._process_candle(candle))` — `handler()` luôn chạy trên cùng thread với main
    loop (ib_insync dispatch `updateEvent` đồng bộ trên loop đó) nên `ensure_future` là
    đủ và đúng.
  - Thêm `task.add_done_callback(self._log_task_error)` + method `_log_task_error()` mới
    để mọi exception trong `_process_candle` từ giờ được log qua
    `logger.error(..., exc_info=True)` thay vì biến mất im lặng.
- **Ảnh hưởng:** Cần deploy + restart `forex-bot.service`. Sau restart, candle mới của
  TẤT CẢ symbol/timeframe sẽ được lưu liên tục (không chỉ lần đầu sau mỗi reconnect).
  Candle 21:15 và 21:30 UTC (2026-06-14) của EURUSD/GBPUSD/USDJPY bị mất vĩnh viễn (không
  backfill được vì IBKR live data đã trôi qua) — chấp nhận gap 30 phút này, không ảnh
  hưởng lớn vì rơi vào giờ thanh khoản thấp nhất đầu tuần.

---

### CHG-FX-007 | Setup logrotate cho `logs/*.log` — tránh đầy disk
- **Thời gian:** 2026-06-13 Conv 6
- **Tại sao:** `logs/scalper.log`, `logs/scalper_errors.log`, `logs/paper.log` (systemd
  `StandardOutput/StandardError`) tăng vô hạn, không tự xoay. Trước khi setup:
  paper.log=19MB, scalper.log=2.9MB, scalper_errors.log=2.1MB (mới ~2 ngày chạy) — có thể
  đầy disk sau vài tháng, làm crash cả Postgres + bot.
- **File mới:** `systemd/forex-bot-logrotate` → deploy thành `/etc/logrotate.d/forex-bot`
- **Config:** `daily`, `rotate 14` (giữ 14 bản), `maxsize 100M`, `compress` +
  `delaycompress`, `copytruncate` (không cần restart bot khi rotate vì process giữ file
  descriptor mở liên tục).
- **Test trên VPS:** `logrotate -f /etc/logrotate.d/forex-bot` → 3 file được rotate
  thành `.1` (paper.log.1=18.8MB, scalper_errors.log.1=2.1MB, scalper.log.1=3.0MB), file
  gốc truncate về 0, bot tiếp tục ghi log bình thường (không restart).
- **Ảnh hưởng:** Cron `/etc/cron.daily/logrotate` (có sẵn Ubuntu) sẽ tự xoay log mỗi
  ngày từ giờ, không cần làm gì thêm.

---

## Conv 6 — Fix weekend backfill spam + crash-loop alert (2026-06-13)

---

### CHG-FX-002 | `is_weekend_candle()` không khớp giờ đóng cửa thật của IBKR → backfill spam "0 candles"
- **Thời gian:** 2026-06-13 Conv 6
- **Tại sao:** `find_missing_candles()` coi Forex đóng cửa Sat/Sun (theo comment cũ), nhưng
  IBKR IDEALPRO thực tế đóng từ **Thứ 6 ~21:00 UTC** (nến 15m cuối cùng quan sát được là
  20:45 UTC). Do đó mỗi lần `_periodic_backfill_loop` chạy vào cuối tuần, 12×15m + 3×1h
  candle/symbol bị coi là "missing" (nhưng IBKR không có data vì market đóng) →
  `fetch_range()` trả về rỗng → `filled=0` → Telegram spam "✅ Backfill done: ... — 0
  candles" + "⚠️ Missing Candle" mỗi giờ.
- **File:**
  - `phase1_data/validator.py` — `is_weekend_candle()`: thêm điều kiện Thứ 6 từ 21:00 UTC
    là weekend (trước đó chỉ check Sat/Sun)
  - `phase1_data/ibkr_collector.py` — `_forex_market_likely_open()`: đổi cutoff Thứ 6
    từ 22:00 → 21:00 UTC để khớp với `validator.py`
- **Fix:** `is_weekend_candle()` giờ trả `True` cho Fri >= 21:00 UTC, Sat cả ngày, Sun <
  21:00 UTC → `find_missing_candles` không còn flag các candle thuộc khoảng đóng cửa thật
  là "missing".
- **Ảnh hưởng:** Hết spam "Backfill done: 0 candles" + "Missing Candle" lúc cuối tuần.

---

### CHG-FX-003 | `_watchdog()` báo "IBKR data delay" giả lúc cuối tuần
- **Thời gian:** 2026-06-13 Conv 6
- **Tại sao:** `DATA_DELAY_THRESHOLD` check trong `_watchdog()` không biết market đang
  đóng cuối tuần → `_last_bar_time` tự nhiên "stale" (không có bar mới) → gửi
  "⚠️ IBKR data delay: Xs since last bar" mỗi `WARN_INTERVAL` dù không có gì bất thường.
- **File:** `phase1_data/ibkr_collector.py` — `_watchdog()`
- **Fix:** Thêm điều kiện `_forex_market_likely_open(datetime.now(tz=timezone.utc))` vào
  check `DATA_DELAY_THRESHOLD` (tương tự check `STALE_CLOSED_BAR_THRESHOLD` đã có).
- **Ảnh hưởng:** Không còn false alert "IBKR data delay" trong khoảng Fri 21:00 UTC → Sun
  21:00 UTC.

---

### CHG-FX-004 | Deploy: rsync nhiều file riêng lẻ không có `-R` → copy sai vị trí
- **Thời gian:** 2026-06-13 Conv 6
- **Vấn đề:** `rsync -avz file1 file2 file3 dest/` (không có `-R`/`--relative`) chỉ lấy
  basename, copy "phẳng" vào `dest/` — KHÔNG giữ cấu trúc `phase1_data/`, `config/`. Kết
  quả: `config/settings.py` bị copy thành `/root/API_FOREX/settings.py` (sai chỗ), file
  thật trong `config/` không được update → `forex-bot.service` crash-loop với
  `ImportError: cannot import name 'STALE_CLOSED_BAR_THRESHOLD' from 'config.settings'`.
- **Fix:**
  1. Copy thủ công 3 file lạc (`/root/API_FOREX/{settings,ibkr_collector,validator}.py`)
     vào đúng vị trí (`config/`, `phase1_data/`), xoá file lạc, restart → bot chạy OK.
  2. **Khuyến nghị deploy về sau:** luôn sync TOÀN BỘ project bằng rsync với dấu `/` ở
     cuối cả source và dest (giữ nguyên cấu trúc cây), KHÔNG truyền file riêng lẻ không
     có `-R`. Xem GUIDELINE.md mục 12 "Update code lên VPS".
- **Ảnh hưởng:** Tránh lặp lại bug "sync xong nhưng file đích sai vị trí" cho các lần
  deploy sau.

---

### CHG-FX-005 | Thêm Telegram alert khi `forex-bot.service` fail (rate-limited)
- **Thời gian:** 2026-06-13 Conv 6
- **Tại sao:** Khi bot crash ngay lúc import (vd `ImportError`) hoặc bị `systemctl
  restart`/SIGTERM giết, code Python chưa kịp gửi message
  "⚠️ IBKR Streaming Disconnected" (nằm trong `finally` của `_stream()`, không chạy tới)
  → không biết bot đang die mà không có cảnh báo gì.
- **File mới:**
  - `scripts/forex_bot_alert.sh` — gửi Telegram "🔴 forex-bot.service FAILED ..." qua
    curl, có cooldown 10 phút (lưu timestamp tại `/root/API_FOREX/.alert_cooldown`) để
    không spam khi crash-loop.
  - `systemd/forex-bot-alert.service` — `Type=oneshot`, chạy script trên.
- **Wiring:** thêm `OnFailure=forex-bot-alert.service` vào `[Unit]` của
  `/etc/systemd/system/forex-bot.service`, `systemctl daemon-reload`.
- **Test trên VPS:** `systemctl start forex-bot-alert.service` → nhận Telegram lần 1
  (06:16:13 UTC); chạy lại ngay lần 2 → bị cooldown, không nhận thêm. `forex-bot.service`
  không bị ảnh hưởng (vẫn `active (running)`).
- **Ảnh hưởng:** Mọi lần `forex-bot.service` vào trạng thái `failed` (crash, ImportError,
  crash-loop...) sẽ có Telegram báo, tối đa 1 message / 10 phút.

---

### CHG-FX-006 | Full-sync rsync quên `--exclude '.env'` → đè `.env` VPS bằng bản Mac → mất DB
- **Thời gian:** 2026-06-13 Conv 6
- **Tại sao:** Lệnh full-sync (CHG-FX-004) mình đưa ra ban đầu thiếu `--exclude '.env'`,
  rsync transfer cả `.env` từ Mac → VPS. `.env` trên Mac (dev local) có
  `DB_USER=ngocdang`, `DB_PASSWORD=your_password` (placeholder, máy Mac dùng trust auth
  nên không cần password đúng) — khác hoàn toàn VPS (`DB_USER=forexbot`,
  `DB_PASSWORD=forexbot123` theo CHG-VPS-002). Sau restart, bot chạy ~10 phút rồi mới
  fail: `password authentication failed for user "ngocdang"` khi cố connect DB.
- **Fix:** Sửa lại `/root/API_FOREX/.env` trên VPS: `DB_USER=forexbot`,
  `DB_PASSWORD=forexbot123`. Restart `forex-bot`.
- **Phòng ngừa:** GUIDELINE.md mục 12 đã thêm warning bắt buộc `--exclude '.env'` cho mọi
  lần full-sync.

---

## Conv 5 — Fix IBKR collector lưu nến chưa đóng (2026-06-12)

---

### CHG-FX-001 | ibkr_collector.py lưu nến "vừa mở" thay vì nến đã đóng
- **Thời gian:** 2026-06-12 Conv 5
- **Tại sao:** Phát hiện qua DBeaver — bảng `candles` có row open_time=16:45 (15m, chưa
  đóng tới 17:00) đã tồn tại lúc 16:48 với `volume=0` và O≈H≈L≈C (chỉ là tick lúc nến vừa
  mở). `keepUpToDate=True` fire `updateEvent` ngay khi 1 bar mới bắt đầu hình thành, với
  `bars[-1]` = bar vừa mở (placeholder). Handler cũ đọc `bars[-1]` và lưu ngay, set
  `_seen[key] = open_time` → mọi update tiếp theo của CÙNG bar (vẫn `bars[-1]`, cùng
  open_time) bị chặn bởi check "duplicate". Khi bar đóng (period rollover), `bars[-1]`
  chuyển sang bar mới — bar vừa đóng (đầy đủ OHLCV) lùi xuống `bars[-2]` nhưng KHÔNG BAO
  GIỜ được đọc lại → DB chỉ có snapshot rác, không bao giờ có giá trị thật sau khi đóng.
- **File:** `phase1_data/ibkr_collector.py` — `_make_handler()`
- **Fix:** Chỉ xử lý khi `has_new_bar=True` (period rollover) VÀ `len(bars) >= 2`; lưu
  `bars[-2]` (bar vừa đóng, OHLCV final) thay vì `bars[-1]` (bar đang hình thành).
- **Đã check:** `ctrader_collector.py` (API_CTRADER) dùng pattern đúng từ đầu — track
  `_forming[key]`, chỉ lưu bar trước khi `open_time` đổi → không bị lỗi này.
- **Ảnh hưởng:** Candle data từ IBKR streaming collector giờ chỉ lưu nến đã đóng với
  OHLCV thật — strategy (FVG/OB/structure) sẽ tính đúng. Verify `python -m py_compile`
  OK. **Cần chạy lại bot để confirm data mới đúng** (data cũ đã lưu sai vẫn còn trong DB,
  có thể cần xoá/backfill lại các row có volume=0 bất thường).

---

## Conv 3 — VPS Deploy Hoàn Chỉnh + Bug Fixes (2026-06-09)

---

### CHG-009 | Fix paper order timeout quá ngắn — orders không bao giờ fill
- **Thời gian:** 2026-06-09 Conv 3
- **Tại sao:** `paper_engine.py` có timeout 300s (5 phút) cho pending orders. Với ENTRY_TIMEFRAME=15m, candle tiếp theo đến sau 900s. Order bị cancel trước khi candle fill kịp → `paper_trades` table luôn rỗng
- **File:** `phase8_paper/paper_engine.py` — `_process_pending_orders()`
- **Fix:** Timeout = 3 candles = `tf_seconds * 3`. Với 15m → 2700s, 1h → 10800s
- **Ảnh hưởng:** Paper orders được fill đúng → paper_trades có data

---

### CHG-VPS-002 | VPS Deploy hoàn chỉnh — IB Gateway login OK
- **Thời gian:** 2026-06-09 Conv 3
- **Nội dung:**
  - Cài x11vnc trên VPS, tạo VNC password tại `/root/.vnc_pass`
  - Connect VNC từ Mac bằng **RealVNC Viewer** (copy-paste hoạt động tốt hơn built-in Screen Sharing)
  - Login IB Gateway thủ công qua VNC: user=imatinyyy, Paper Trading, port 7497
  - Config API Settings: bỏ Read-Only, socket port 7497, Allow localhost only ✅
  - Transfer code từ Mac → VPS: `rsync -avz /Users/ngocdang/Claude/Projects/API_FOREX/ root@69.12.65.42:/root/API_FOREX/`
  - Setup Python venv: `python3 -m venv .venv && pip install -r requirements.txt`
  - **Fix:** `pip install tzdata` — thiếu package này gây `ZoneInfoNotFoundError: US/Eastern` khi download data
  - Setup PostgreSQL: user=forexbot, db=forex_scalper_db, password=forexbot123
  - Download data EURUSD/GBPUSD/USDJPY/XAUUSD thành công
  - Backtest all symbols 15m chạy OK
  - Paper trading chạy OK: `python3 main.py paper`
  - Kết nối test: `Connected: ['DUQ686904']` ✅
- **RAM phân tích:** IB Gateway 316MB + PostgreSQL 200MB + bots 91MB = 804MB/961MB, swap 399MB → nên nâng 2GB

---

### CHG-DOC-001 | Cập nhật GUIDELINE.md — VPS start instructions
- **Thời gian:** 2026-06-09 Conv 3
- **File:** `GUIDELINE.md` — section 3 + section 14
- **Thêm:**
  - Hướng dẫn chi tiết start IB Gateway trên VPS headless (Xvfb + x11vnc)
  - 3 cách connect VNC từ Mac
  - Tip copy-paste cho Java app
  - Note PostgreSQL dùng chung 1 service, 2 DB riêng (OKX + Forex)
  - Warning `tzdata` bắt buộc trên Ubuntu 24.04

---

### CHG-ENV-001 | Điền Telegram token + chat_id vào .env
- **Thời gian:** 2026-06-09 Conv 3
- **File:** `.env` (Mac + VPS), `/root/API_OKX/.env` (VPS)
- **Fix:** `TELEGRAM_BOT_TOKEN=8821195660:...`, `TELEGRAM_CHAT_ID=7457950702`
- **Ảnh hưởng:** Bot gửi alert khi vào lệnh, đóng lệnh, lỗi

---

## Tổng kết thay đổi theo file (Conv 3)

| File | Thay đổi | Loại |
|---|---|---|
| `GUIDELINE.md` | Thêm VPS start instructions + tzdata note | Docs |
| `BACKUP_CONTEXT.md` | Update trạng thái VPS deploy hoàn chỉnh | Docs |
| VPS `/root/API_FOREX/` | Code mới transfer lên | Deploy |
| VPS PostgreSQL | forex_scalper_db tạo xong | Deploy |

---

## Conv 2 — Paper Trading Fixes + VPS Deploy Attempt (2026-06-09)

---

### CHG-005 | Fix 1h không được preload vào paper engine buffer
- **Thời gian:** 2026-06-09 Conv 2
- **Tại sao:** `run_paper()` chỉ preload `[ENTRY_TIMEFRAME]` = `["15m"]`. Buffer 1h khởi đầu rỗng → `structure.update([1 candle])` → trend = RANGE → `mtf_bias = NEUTRAL` → L1 fail mãi → **không bao giờ có signal**
- **File:** `main.py` — `run_paper()`
- **Fix:** Preload cả `{ENTRY_TIMEFRAME, "1h"}` thay vì chỉ `[ENTRY_TIMEFRAME]`
- **Ảnh hưởng:** MTF bias có data ngay từ đầu → L1 hoạt động đúng

---

### CHG-006 | Fix timezone bug trong session filter
- **Thời gian:** 2026-06-09 Conv 2
- **Tại sao:** IBKR trả về bars với timezone EDT (-04:00). `session_filter.is_trading_session()` dùng `dt.hour` mà không convert sang UTC → candle lúc 04:00 EDT (= 08:00 UTC, London open hợp lệ) bị reject là "pre_session"
- **File:** `utils/session_filter.py` — `is_trading_session()`, `session_stop_reason()`
- **Fix:** Thêm `dt = dt.astimezone(timezone.utc)` trước khi check `dt.hour`
- **Ảnh hưởng:** Session filter đánh giá đúng theo UTC → không reject nhầm London/NY session

---

### CHG-007 | Fix MTFBias dùng chung cho tất cả symbols
- **Thời gian:** 2026-06-09 Conv 2
- **Tại sao:** `_make_strategy_runner()` dùng 1 object `MTFBias()` duy nhất cho tất cả 4 symbols. Khi EURUSD 1h update `mtf.update("1h", "UPTREND")` rồi GBPUSD 1h update `mtf.update("1h", "DOWNTREND")` → bias bị overwrite → GBPUSD dùng bias của EURUSD
- **File:** `main.py` — `_make_strategy_runner()`
- **Fix:**
  - Thêm `"mtf": MTFBias()` và `"structure_1h": StructureEngine(symbol, "1h")` vào `engines[symbol]` dict
  - Mỗi symbol có MTFBias riêng
  - 1h candle update `eng["structure_1h"]` và `eng["mtf"]` riêng
  - 15m candle update `eng["structure"]` và `eng["mtf"]` riêng
- **Ảnh hưởng:** MTF bias chính xác per-symbol, không cross-pollute giữa EURUSD/GBPUSD/USDJPY/XAUUSD

---

### CHG-008 | Fix TAKER_FEE trong paper portfolio tracker
- **Thời gian:** 2026-06-09 Conv 2
- **Tại sao:** `portfolio_tracker.py` có `TAKER_FEE = 0.0004` copy từ OKX (0.04%). Forex không có exchange fee — chi phí chỉ là spread (đã tính trong fill price simulation)
- **File:** `phase8_paper/portfolio_tracker.py`
- **Fix:** `TAKER_FEE = 0.0`
- **Ảnh hưởng:** PnL paper trades không bị trừ nhầm 0.04% fee → con số chính xác hơn

---

### CHG-VPS-001 | VPS Setup (chưa hoàn thành)
- **Thời gian:** 2026-06-09 Conv 2
- **VPS:** 69.12.65.42 (RackNerd, Ubuntu 24.04, 1GB RAM)
- **Đã cài:** Java 11, Xvfb, IB Gateway 10.45 (`/root/ibgateway/`), IBC 3.19.0 (`/opt/ibc/`)
- **IB Gateway start thủ công:** hoạt động (`export DISPLAY=:1 && /root/ibgateway/ibgateway &`)
- **IBC auto-login:** CHƯA hoạt động — lỗi "vmoptions not found"
  - Nguyên nhân: IB Gateway standalone dùng install4j launcher, không có versioned subfolder
  - IBC tìm: `/root/ibgateway/1045/ibgateway.vmoptions` nhưng file ở `/root/ibgateway/ibgateway.vmoptions`
  - Đã thử: symlinks, thay đổi TWS_PATH/TWS_MAJOR_VRSN — chưa fix được
- **Vấn đề 2FA:** cần VNC login 1 lần để trust device trước khi IBC auto-login
- **Pending decision:** A) Fix IBC + VNC, hoặc B) Switch sang OANDA REST API

---

## Tổng kết thay đổi theo file (Conv 2)

| File | Thay đổi | Loại |
|---|---|---|
| `main.py` | Preload 1h + MTFBias per-symbol + structure_1h per-symbol | Bug fix |
| `utils/session_filter.py` | Convert EDT→UTC trước khi check hour | Bug fix |
| `phase8_paper/portfolio_tracker.py` | TAKER_FEE = 0.0 | Bug fix |
| `VPS_DEPLOY.md` | Tạo mới — guide deploy VPS đầy đủ 11 bước | Docs |

---

## Conv 1 — Initial Build (2026-06-08/09)

---

### CHG-001 | Clone từ API_OKX, thay API layer sang IBKR
- **Thời gian:** 2026-06-08 Conv 1
- **Tại sao:** OKX là crypto, cần Forex. OANDA fxTrade bị chặn ở VN → dùng IBKR
- **Files mới:**
  - `phase1_data/ibkr_downloader.py` — IBKR historical data via ib_insync
  - `phase1_data/ibkr_collector.py` — IBKR real-time 5s bars → candle aggregator
  - `phase9_live/ibkr_order_manager.py` — IBKR order execution (IDEALPRO)
  - `utils/session_filter.py` — Forex session filter (London/NY hours)
- **Files adapt:**
  - `config/settings.py` — IBKR config, Forex symbols, pip sizes, lot sizes
  - `phase1_data/validator.py` — thêm weekend candle filter
  - `phase1_data/database.py` — bỏ funding_rates/OI tables, weekend-aware gap detection
  - `phase6_risk/risk_engine.py` — pip-based SL, IBKR units sizing, Forex PnL calc
  - `phase7_backtest/backtest_engine.py` — spread cost thay exchange fees, symbol param
  - `phase9_live/live_engine.py` — switch sang IBKR classes
  - `phase5_entry/entry_engine.py` — thêm session filter + Forex volume layer fix
- **Files copy nguyên:** phase2, phase3, phase4 (SMC logic generic)
- **Ảnh hưởng:** Toàn bộ API layer, giữ nguyên strategy logic

---

### CHG-002 | Session Filter cho Forex
- **Thời gian:** 2026-06-09 Conv 1
- **Tại sao:** Không có session filter → bot có thể vào lệnh lúc 3AM Tokyo session khi spread rộng, volume thấp → nhiều false signal
- **File:** `utils/session_filter.py` (mới), `phase5_entry/entry_engine.py`, `config/settings.py`
- **Fix:**
  - EURUSD/GBPUSD/XAUUSD: chỉ trade 08:00–22:00 UTC (London + NY)
  - USDJPY: trade 00:00–22:00 UTC (thêm Tokyo session)
  - Dead zone 22:00–00:00 UTC: tất cả skip
  - Weekend: tự động skip
  - `SESSION_FILTER_ENABLED=false` để tắt (debug/backtest)
- **Ảnh hưởng:** Entry engine — giảm số signal ngoài giờ, tăng signal quality

---

### CHG-003 | Fix Volume Layer cho tick-based data
- **Thời gian:** 2026-06-09 Conv 1
- **Tại sao:** IBKR Forex trả về tick count thay vì real volume → threshold 50% quá cao, filter nhiều signal hợp lệ
- **File:** `phase5_entry/entry_engine.py` — `_check_volume()`
- **Fix:**
  - Giảm threshold từ 50% xuống 30% (tick volume noisy hơn real volume)
  - Nếu volume = 0 (candle thiếu data) → fallback dùng candle body size (body ≥ 30% ATR = có momentum)
- **Ảnh hưởng:** Layer 4 ít reject signal hợp lệ hơn trên Forex

---

### CHG-004 | Thêm IBKR config vào settings.py
- **Thời gian:** 2026-06-09 Conv 1
- **Tại sao:** Cần config IB Gateway connection parameters
- **File:** `config/settings.py`
- **Fix:** Thêm `IB_HOST`, `IB_PORT`, `IB_PORT_PAPER=7497`, `IB_PORT_LIVE=7496`, `IB_CLIENT_ID`, `IB_PAPER_MODE`, `IB_REQUEST_DELAY`, `IB_MAX_DURATION`, `IBKR_TF_MAP`, `IBKR_SYMBOL_MAP`
- **Ảnh hưởng:** Config only

---

## Tổng kết thay đổi theo file (Conv 1)

| File | Thay đổi | Loại |
|---|---|---|
| `phase1_data/ibkr_downloader.py` | Mới | Feature |
| `phase1_data/ibkr_collector.py` | Mới | Feature |
| `phase9_live/ibkr_order_manager.py` | Mới | Feature |
| `utils/session_filter.py` | Mới | Feature |
| `config/settings.py` | Adapt + IBKR config | Feature |
| `phase6_risk/risk_engine.py` | Rewrite cho Forex | Feature |
| `phase5_entry/entry_engine.py` | Session filter + Volume fix | Bug fix + Feature |
| `phase7_backtest/backtest_engine.py` | Spread cost, symbol param | Adapt |
| `phase9_live/live_engine.py` | Switch sang IBKR | Adapt |
| `phase1_data/validator.py` | Weekend filter | Feature |
| `phase1_data/database.py` | Weekend-aware gaps | Adapt |

---

*CHANGED.md — tạo: 2026-06-09 (Conv 1 — Forex)*
