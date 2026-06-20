"""
Phase 9.7 — Web Dashboard (MT5 Edition).

Giám sát + thao tác tay: xem balance, positions, cancel/close.
MT5OrderManager thay IBKROrderManager — không cần event loop riêng vì
MT5 gọi sync trong executor.

Chạy: uvicorn phase9_live.web_dashboard:app --host 0.0.0.0 --port 8000
"""
import asyncio
import secrets
import threading
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

from utils.logger import logger
from phase9_live.mt5_order_manager import MT5OrderManager
from config.settings import DASHBOARD_USER, DASHBOARD_PASS

security = HTTPBasic()
_om: Optional[MT5OrderManager] = None
_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _om
    _om = MT5OrderManager()
    logger.info("[Dashboard] MT5OrderManager ready")
    yield
    logger.info("[Dashboard] shutdown")


app = FastAPI(title="MT5 Scalper Dashboard", lifespan=lifespan)


def check_auth(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    ok_user = secrets.compare_digest(
        credentials.username.encode("utf-8"), DASHBOARD_USER.encode("utf-8")
    )
    ok_pass = secrets.compare_digest(
        credentials.password.encode("utf-8"), DASHBOARD_PASS.encode("utf-8")
    )
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=401, detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


class CloseRequest(BaseModel):
    ticket: int
    symbol: str
    volume: Optional[float] = None


class CancelRequest(BaseModel):
    ticket: int


# ─────────────────────────────────────────────
# API
# ─────────────────────────────────────────────
@app.get("/api/state")
async def api_state(user: str = Depends(check_auth)):
    async with _lock:
        balance    = await _om.get_account_balance()
        positions  = await _om.get_all_positions()
        pending    = await _om.get_pending_orders()
        closed     = await _om.get_last_closed_trade("") if hasattr(_om, "_last_closed_all") else []

    return JSONResponse({
        "balance":        balance,
        "positions":      positions,
        "pending_orders": pending,
    })


@app.post("/api/close")
async def api_close(req: CloseRequest, user: str = Depends(check_auth)):
    logger.info(f"[Dashboard] {user} close ticket={req.ticket} {req.symbol}")
    async with _lock:
        ok = await _om.close_position(req.ticket, req.symbol, req.volume)
    if not ok:
        raise HTTPException(status_code=400, detail="close_position failed")
    return {"ok": True, "ticket": req.ticket}


@app.post("/api/cancel")
async def api_cancel(req: CancelRequest, user: str = Depends(check_auth)):
    logger.info(f"[Dashboard] {user} cancel ticket={req.ticket}")
    async with _lock:
        ok = await _om.cancel_order(req.ticket)
    if not ok:
        raise HTTPException(status_code=400, detail="cancel_order failed")
    return {"ok": True, "ticket": req.ticket}


@app.post("/api/close_all")
async def api_close_all(user: str = Depends(check_auth)):
    logger.info(f"[Dashboard] {user} close ALL positions")
    async with _lock:
        n = await _om.close_all_positions()
    return {"closed": n}


# ─────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────
HTML_PAGE = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MT5 Scalper Dashboard</title>
<style>
  body { font-family: -apple-system, Arial, sans-serif; background:#0f1115; color:#e6e6e6; margin:0; padding:16px; }
  h1 { font-size:18px; margin:0 0 12px; }
  h2 { font-size:14px; color:#9aa; margin:18px 0 6px; }
  table { width:100%; border-collapse:collapse; font-size:13px; margin-bottom:8px; }
  th, td { padding:6px 8px; border-bottom:1px solid #2a2d35; text-align:left; }
  th { color:#9aa; font-weight:normal; }
  .buy  { color:#4caf50; }
  .sell { color:#f44336; }
  button { background:#c0392b; color:#fff; border:none; padding:5px 10px; border-radius:4px; cursor:pointer; font-size:12px; }
  button.cancel { background:#555; }
  button:hover { opacity:0.85; }
  .balance { font-size:22px; font-weight:bold; color:#4caf50; }
  .status  { color:#888; font-size:12px; margin-top:10px; }
  .empty   { color:#666; font-size:13px; padding:6px 0; }
</style>
</head>
<body>
  <h1>MT5 Scalper — Live Dashboard</h1>
  <div>Balance: <span class="balance" id="balance">--</span></div>

  <h2>Positions đang mở
    <button onclick="closeAll()" style="margin-left:8px;background:#922">Close All</button>
  </h2>
  <table id="positions"><tbody></tbody></table>
  <div class="empty" id="positions-empty" style="display:none">Không có position.</div>

  <h2>Pending orders (LIMIT chưa fill)</h2>
  <table id="pending"><tbody></tbody></table>
  <div class="empty" id="pending-empty" style="display:none">Không có pending order.</div>

  <div class="status" id="status">Đang tải...</div>

<script>
async function fetchState() {
  try {
    const r = await fetch('/api/state');
    if (!r.ok) { document.getElementById('status').textContent = 'Auth error'; return; }
    const d = await r.json();

    document.getElementById('balance').textContent =
      d.balance != null ? '$' + d.balance.toFixed(2) : '--';

    // Positions
    const ptbody = document.querySelector('#positions tbody');
    ptbody.innerHTML = '';
    const pos = d.positions || [];
    document.getElementById('positions-empty').style.display = pos.length ? 'none' : '';
    pos.forEach(p => {
      const pnl = p.profit != null ? (p.profit >= 0 ? '+' : '') + p.profit.toFixed(2) : '--';
      const row = `<tr>
        <td><b class="${p.side.toLowerCase()}">${p.side}</b> ${p.symbol}</td>
        <td>${p.volume}L</td>
        <td>@${p.entry}</td>
        <td>SL: ${p.sl || '--'}</td>
        <td>TP: ${p.tp || '--'}</td>
        <td class="${p.profit>=0?'buy':'sell'}">${pnl}</td>
        <td><button onclick="closePos(${p.ticket},'${p.symbol}')">Close</button></td>
      </tr>`;
      ptbody.insertAdjacentHTML('beforeend', row);
    });

    // Pending
    const otbody = document.querySelector('#pending tbody');
    otbody.innerHTML = '';
    const orders = d.pending_orders || [];
    document.getElementById('pending-empty').style.display = orders.length ? 'none' : '';
    orders.forEach(o => {
      const row = `<tr>
        <td>${o.type} ${o.symbol}</td>
        <td>${o.volume}L @ ${o.price}</td>
        <td>SL:${o.sl||'--'} TP:${o.tp||'--'}</td>
        <td><button class="cancel" onclick="cancelOrder(${o.ticket})">Cancel</button></td>
      </tr>`;
      otbody.insertAdjacentHTML('beforeend', row);
    });

    document.getElementById('status').textContent = 'Updated ' + new Date().toLocaleTimeString();
  } catch(e) {
    document.getElementById('status').textContent = 'Error: ' + e;
  }
}

async function closePos(ticket, symbol) {
  if (!confirm('Đóng position ticket=' + ticket + ' ' + symbol + '?')) return;
  const r = await fetch('/api/close', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ticket, symbol})
  });
  alert(r.ok ? 'Đã close' : 'Lỗi close');
  fetchState();
}

async function cancelOrder(ticket) {
  if (!confirm('Cancel order ticket=' + ticket + '?')) return;
  const r = await fetch('/api/cancel', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ticket})
  });
  alert(r.ok ? 'Đã cancel' : 'Lỗi cancel');
  fetchState();
}

async function closeAll() {
  if (!confirm('Close TẤT CẢ positions?')) return;
  const r = await fetch('/api/close_all', {method:'POST'});
  const d = await r.json();
  alert('Closed ' + d.closed + ' position(s)');
  fetchState();
}

fetchState();
setInterval(fetchState, 15000);
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def dashboard(user: str = Depends(check_auth)):
    return HTML_PAGE
