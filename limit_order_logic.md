# SMC Pending Limit Order Lifecycle Specification

## Mục tiêu

Đối với chiến lược Smart Money Concepts (SMC), **Pending LIMIT Order không nên hết hạn theo thời gian cố định** (ví dụ 3 nến hoặc 5 nến).

Thay vào đó, lệnh chỉ nên bị hủy khi **premise (giả định giao dịch ban đầu) không còn hợp lệ**.

---

# Core Principle

> **Một Pending LIMIT Order vẫn hợp lệ miễn là cấu trúc thị trường hỗ trợ ý tưởng giao dịch ban đầu.**

Do đó:

* Không sử dụng `expire_after_n_candles`
* Không sử dụng `expire_after_x_minutes`
* Chỉ hủy khi có bằng chứng khách quan rằng setup đã mất hiệu lực.

---

# Pending Order States

```
NEW
  │
  ▼
PENDING_LIMIT
  │
  ├──────────────► FILLED
  │
  ├──────────────► CANCELLED
  │
  └──────────────► KEEP_WAITING
```

---

# Conditions to KEEP Pending Order

Pending LIMIT Order tiếp tục tồn tại nếu **tất cả** điều kiện sau đều đúng:

## 1. Market Structure vẫn hợp lệ

* Chưa xuất hiện phá vỡ cấu trúc làm vô hiệu setup.
* Swing High / Swing Low bảo vệ setup vẫn còn nguyên.

---

## 2. Entry Zone còn hợp lệ

Order Block (OB) hoặc Fair Value Gap (FVG):

* Chưa bị invalidate.
* Chưa bị phá xuyên theo quy tắc của strategy.

---

## 3. Chưa có BOS ngược chiều

Không xuất hiện Break of Structure xác nhận thay đổi xu hướng ngược với hướng giao dịch.

Ví dụ:

Long setup:

* BOS tăng → hợp lệ
* BOS giảm → hủy setup

Short setup:

* BOS giảm → hợp lệ
* BOS tăng → hủy setup

---

## 4. Session còn hiệu lực

Nếu strategy chỉ giao dịch trong một phiên cụ thể:

* London Session
* New York Session

thì Pending Order chỉ tồn tại trong phiên đó.

Hết phiên mà chưa khớp → hủy.

---

## 5. Setup Context chưa thay đổi

HTF bias, liquidity narrative hoặc điều kiện xác nhận ban đầu vẫn còn đúng.

Nếu framework của strategy xác định context đã thay đổi thì Pending Order phải bị hủy.

---

# Conditions to CANCEL Pending Order

## Rule 1 — Structure Broken

Nếu giá **đóng cửa vượt qua vùng bảo vệ của setup (SL structure)** trước khi LIMIT được fill:

```
BUY:
Close < SL Structure

=> CANCEL
```

```
SELL:
Close > SL Structure

=> CANCEL
```

---

## Rule 2 — Opposite BOS

Xuất hiện Break of Structure xác nhận đảo chiều ngược hướng trade.

Ví dụ:

Long Pending:

```
Higher High
Higher Low

↓

Lower Low confirmed

=> CANCEL
```

---

## Rule 3 — Order Block Invalidated

OB không còn giá trị.

Ví dụ:

Long OB:

```
Price closes decisively below OB

=> CANCEL
```

Short OB:

```
Price closes decisively above OB

=> CANCEL
```

Tiêu chí "invalidate" phải được định nghĩa rõ trong strategy (body close, wick, số pip vượt quá...).

---

## Rule 4 — Session Expired

Nếu:

```
Current Session != Setup Session
```

và chưa fill lệnh:

```
=> CANCEL
```

Ví dụ:

* Setup tạo trong London.
* Sang Asian session vẫn chưa fill.

=> Hủy.

---

## Rule 5 — Higher Timeframe Bias Changed

Nếu bias khung thời gian lớn thay đổi và không còn ủng hộ setup:

```
HTF Bullish
    ↓
HTF Bearish confirmed

=> CANCEL Long
```

---

# Optional Rule (Backtest Required)

## Excessive Displacement

Có thể cân nhắc hủy nếu giá di chuyển quá xa khỏi vùng entry trước khi quay lại.

Ví dụ:

```
distance(current_price, entry)
    >
2 × initial_risk
```

Tuy nhiên:

* Không nên mặc định sử dụng.
* Chỉ áp dụng nếu backtest chứng minh cải thiện hiệu quả.
* Đây là điều kiện phụ, không phải điều kiện cốt lõi.

---

# Recommended Evaluation Loop

Thực hiện kiểm tra sau mỗi nến M15 đóng cửa:

```
for every closed candle:

    if order_filled:
        move_to_trade_management()

    elif structure_broken:
        cancel_order()

    elif opposite_BOS_confirmed:
        cancel_order()

    elif order_block_invalidated:
        cancel_order()

    elif session_expired:
        cancel_order()

    elif higher_timeframe_bias_changed:
        cancel_order()

    else:
        keep_pending_order()
```

---

# Best Practices

## Nên

* Đánh giá khi nến đóng để tránh nhiễu intrabar.
* Định nghĩa rõ BOS, OB invalidation và HTF bias bằng quy tắc có thể lập trình.
* Tách riêng module Signal Detection và Pending Order Management.
* Ghi log lý do hủy lệnh (`cancel_reason`) để dễ thống kê và tối ưu.

Ví dụ:

```
cancel_reason = STRUCTURE_BROKEN
cancel_reason = OPPOSITE_BOS
cancel_reason = SESSION_EXPIRED
cancel_reason = OB_INVALIDATED
cancel_reason = HTF_BIAS_CHANGED
```

## Không nên

* Hủy lệnh chỉ vì đã chờ 3 hoặc 5 nến.
* Hủy dựa trên cảm tính hoặc quan sát thủ công.
* Thêm quá nhiều điều kiện phụ chưa được kiểm chứng bằng backtest.

---

# Design Philosophy

> **Pending LIMIT Order nên sống theo "validity of market structure", không phải theo "elapsed time".**

Một setup tốt có thể được fill sau nhiều nến nếu premise ban đầu vẫn còn nguyên.

Ngược lại, một setup phải bị hủy ngay khi cấu trúc thị trường chứng minh rằng ý tưởng giao dịch đã mất hiệu lực, dù mới chỉ tồn tại trong một nến.
