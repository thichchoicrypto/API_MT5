"""
Standalone test runner — no pytest dependency.
Stubs out loguru and aiohttp so tests run without those packages.
Usage: python3 tests/run_tests.py
"""
import sys
import types
import traceback
from datetime import datetime, timezone, timedelta

# ── Stubs ─────────────────────────────────────────────────────────
_loguru = types.ModuleType('loguru')
class _L:
    def info(self,*a,**k): pass
    def debug(self,*a,**k): pass
    def warning(self,*a,**k): pass
    def error(self,*a,**k): pass
    def remove(self): pass
    def add(self,*a,**k): pass
_loguru.logger = _L()
sys.modules['loguru'] = _loguru

_aiohttp = types.ModuleType('aiohttp')
class _CS:
    async def __aenter__(self): return self
    async def __aexit__(self, *a): pass
    def get(self, *a, **k): return _CS()
    def post(self, *a, **k): return _CS()
    async def json(self): return {}
    status = 200
    async def close(self): pass
_aiohttp.ClientSession = lambda **k: _CS()
_aiohttp.ClientTimeout = lambda **k: None
_aiohttp.ClientConnectorError = Exception
sys.modules['aiohttp'] = _aiohttp

_dotenv = types.ModuleType('dotenv')
_dotenv.load_dotenv = lambda: None
sys.modules['dotenv'] = _dotenv

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ─────────────────────────────────────────────
PASS = 0
FAIL = 0
ERRORS = []


def ok(name):
    global PASS
    PASS += 1
    print(f"  ✅  {name}")


def fail(name, exc):
    global FAIL
    FAIL += 1
    ERRORS.append((name, exc))
    print(f"  ❌  {name}")
    print(f"        {type(exc).__name__}: {exc}")


def run(name, fn):
    try:
        fn()
        ok(name)
    except Exception as e:
        fail(name, e)


def t(h):
    return datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=h)


def c(o, h, l, cl, i=0, vol=1000.0):
    return {'open':o,'high':h,'low':l,'close':cl,'volume':vol,
            'open_time':t(i),'symbol':'BTCUSDT','timeframe':'1h'}


def candles_up(n=60, base=100.0, step=0.5):
    result = []
    price = base
    for i in range(n):
        if i % 10 < 7:
            price += step
        else:
            price -= step * 0.2
        result.append(c(price-0.1, price+0.3, price-0.5, price, i=i))
    return result


# ════════════════════════════════════════════════════════════════
# PHASE 2 — STRUCTURE
# ════════════════════════════════════════════════════════════════
print("\n📐 Phase 2 — Structure")

from phase2_structure.swing_detector import detect_swing_highs, detect_swing_lows
from phase2_structure.bos_detector import detect_bos, StructureStateMachine
from phase2_structure.market_structure import classify_structure
from phase2_structure.structure_engine import StructureEngine

def test_swing_high_basic():
    candles = [c(10,h,9,10) for h in [10,10,15,10,10]]
    h = detect_swing_highs(candles, n=1)
    assert len(h)==1 and h[0]['price']==15
run("swing_high detected", test_swing_high_basic)

def test_swing_low_basic():
    candles = [c(10,11,l,10) for l in [9,9,5,9,9]]
    l = detect_swing_lows(candles, n=1)
    assert len(l)==1 and l[0]['price']==5
run("swing_low detected", test_swing_low_basic)

def test_no_swings_flat():
    candles = [c(10,10,10,10)]*10
    assert detect_swing_highs(candles, n=2)==[]
    assert detect_swing_lows(candles, n=2)==[]
run("no swing on flat candles", test_no_swings_flat)

def test_bos_up():
    candle = c(100,105,98,101)
    bos = detect_bos(candle, 100.0, 90.0)
    assert bos and bos['type']=='BOS_UP'
run("BOS_UP detected", test_bos_up)

def test_bos_down():
    candle = c(100,102,88,89)
    bos = detect_bos(candle, 110.0, 90.0)
    assert bos and bos['type']=='BOS_DOWN'
run("BOS_DOWN detected", test_bos_down)

def test_bos_no_swing():
    assert detect_bos(c(100,105,98,101), None, None) is None
run("BOS returns None with no swings", test_bos_no_swing)

def test_state_machine():
    sm = StructureStateMachine()
    sm.process_bos({'type':'BOS_UP','price':100,'time':None,'swing_level':95})
    assert sm.state == 'UPTREND'
    sm.process_bos({'type':'BOS_DOWN','price':90,'time':None,'swing_level':95})
    assert sm.state == 'DOWNTREND'
run("StructureStateMachine transitions", test_state_machine)

def test_uptrend():
    def sw(prices, kind):
        return [{'price':p,'type':f'swing_{kind}','index':i,'time':t(i)} for i,p in enumerate(prices)]
    result = classify_structure(sw([100,110,120],'high'), sw([90,95,100],'low'))
    assert result['trend']=='UP'
run("classify_structure UPTREND", test_uptrend)

def test_downtrend():
    def sw(prices, kind):
        return [{'price':p,'type':f'swing_{kind}','index':i,'time':t(i)} for i,p in enumerate(prices)]
    result = classify_structure(sw([120,110,100],'high'), sw([100,95,90],'low'))
    assert result['trend']=='DOWN'
run("classify_structure DOWNTREND", test_downtrend)

def test_structure_engine_smoke():
    engine = StructureEngine("BTCUSDT", "1h")
    out = engine.update(candles_up(30))
    assert 'trend' in out and 'last_swing_high' in out
run("StructureEngine.update smoke", test_structure_engine_smoke)

def test_bos_events_capped():
    engine = StructureEngine("BTCUSDT", "1h")
    for _ in range(50):
        engine.update(candles_up(30))
    assert len(engine._bos_events) <= 20
run("BOS events capped at 20", test_bos_events_capped)


# ════════════════════════════════════════════════════════════════
# PHASE 3 — LIQUIDITY
# ════════════════════════════════════════════════════════════════
print("\n💧 Phase 3 — Liquidity")

from phase3_liquidity.sweep_detector import detect_sweep
from phase3_liquidity.choch_detector import detect_choch
from phase3_liquidity.liquidity_engine import detect_equal_highs, detect_equal_lows, build_liquidity_zones

def test_bullish_sweep():
    candle = c(94,96,93,96)
    sweep = detect_sweep(candle, 110.0, 95.0)
    assert sweep and sweep['type']=='BUY_SIDE_SWEEP'
run("bullish sweep detected", test_bullish_sweep)

def test_bearish_sweep():
    candle = c(104,112,103,103)
    sweep = detect_sweep(candle, 110.0, 90.0)
    assert sweep and sweep['type']=='SELL_SIDE_SWEEP'
run("bearish sweep detected", test_bearish_sweep)

def test_no_sweep_no_wick():
    candle = c(100,102,98,101)
    assert detect_sweep(candle, 110.0, 90.0) is None
run("no sweep when no wick beyond level", test_no_sweep_no_wick)

def test_sweep_no_crash_none_swings():
    assert detect_sweep(c(100,102,88,89), None, None) is None
run("sweep returns None with None swings", test_sweep_no_crash_none_swings)

def test_choch_bullish():
    bos = {'type':'BOS_UP','price':105.0,'time':t(0),'swing_level':100.0}
    choch = detect_choch('DOWNTREND', bos)
    assert choch and choch['type']=='BULLISH_CHOCH'
run("BULLISH_CHOCH from DOWNTREND+BOS_UP", test_choch_bullish)

def test_choch_bearish():
    bos = {'type':'BOS_DOWN','price':90.0,'time':t(0),'swing_level':95.0}
    choch = detect_choch('UPTREND', bos)
    assert choch and choch['type']=='BEARISH_CHOCH'
run("BEARISH_CHOCH from UPTREND+BOS_DOWN", test_choch_bearish)

def test_choch_none_aligned():
    bos = {'type':'BOS_UP','price':110.0,'time':t(0),'swing_level':105.0}
    assert detect_choch('UPTREND', bos) is None
run("no CHoCH when BOS aligns with trend", test_choch_none_aligned)

def test_equal_highs_detected():
    highs = [{'price':100.0,'type':'swing_high','index':0,'time':t(0)},
             {'price':100.05,'type':'swing_high','index':1,'time':t(1)}]
    zones = detect_equal_highs(highs, threshold=0.001)
    assert len(zones)>=1
run("equal highs detected within threshold", test_equal_highs_detected)

def test_equal_highs_zero_no_crash():
    highs = [{'price':0.0,'type':'swing_high','index':0,'time':None},
             {'price':100.0,'type':'swing_high','index':1,'time':None}]
    zones = detect_equal_highs(highs)
    assert isinstance(zones, list)
run("equal_highs zero price no ZeroDivisionError", test_equal_highs_zero_no_crash)

def test_equal_lows_zero_no_crash():
    lows = [{'price':0.0,'type':'swing_low','index':0,'time':None},
            {'price':90.0,'type':'swing_low','index':1,'time':None}]
    zones = detect_equal_lows(lows)
    assert isinstance(zones, list)
run("equal_lows zero price no ZeroDivisionError", test_equal_lows_zero_no_crash)


# ════════════════════════════════════════════════════════════════
# PHASE 4 — FVG + OB
# ════════════════════════════════════════════════════════════════
print("\n📦 Phase 4 — FVG + OB")

from phase4_fvg_ob.fvg_engine import detect_fvg, update_fvg_fills
from phase4_fvg_ob.orderblock_engine import detect_order_block, update_ob_mitigation
from phase4_fvg_ob.zone_builder import build_entry_zone, find_confluence_zones

def test_bullish_fvg():
    candles = [c(100,102,98,101,0), c(103,105,103,104,1), c(106,108,104,107,2)]
    fvgs = detect_fvg(candles)
    assert any(f['type']=='BULLISH_FVG' for f in fvgs)
run("BULLISH_FVG detected", test_bullish_fvg)

def test_bearish_fvg():
    candles = [c(108,110,106,107,0), c(105,106,103,104,1), c(102,104,100,103,2)]
    fvgs = detect_fvg(candles)
    assert any(f['type']=='BEARISH_FVG' for f in fvgs)
run("BEARISH_FVG detected", test_bearish_fvg)

def test_fvg_empty():
    assert detect_fvg([]) == []
run("detect_fvg empty list", test_fvg_empty)

def test_fvg_fill_by_close():
    fvg = {'type':'BULLISH_FVG','zone':[102.0,104.0],'filled':False,'midpoint':103.0,'size':2.0,'index':1,'time':None}
    candle_close = c(101,105,100,103)  # close=103 inside zone
    update_fvg_fills([fvg], candle_close)
    assert fvg['filled'] is True
run("FVG filled when close inside zone", test_fvg_fill_by_close)

def test_fvg_wick_only_not_filled():
    fvg = {'type':'BULLISH_FVG','zone':[102.0,104.0],'filled':False,'midpoint':103.0,'size':2.0,'index':1,'time':None}
    candle_wick = c(101,103.5,100,101)  # wick enters zone, close=101 outside
    update_fvg_fills([fvg], candle_wick)
    assert fvg['filled'] is False  # zone still active for confirmation candle
run("FVG wick-only NOT filled (zone survives for confirmation)", test_fvg_wick_only_not_filled)

def test_fvg_not_filled_when_far():
    fvg = {'type':'BULLISH_FVG','zone':[110.0,115.0],'filled':False,'midpoint':112.5,'size':5.0,'index':1,'time':None}
    update_fvg_fills([fvg], c(100,105,98,102))
    assert fvg['filled'] is False
run("FVG not filled when candle far below", test_fvg_not_filled_when_far)

def test_ob_mitigation_by_close():
    ob = {'type':'BULLISH_OB','zone':[99.0,101.0],'mitigated':False,'midpoint':100.0,'index':0,'time':None}
    update_ob_mitigation([ob], c(102,103,98,100))  # close=100 inside zone
    assert ob['mitigated'] is True
run("OB mitigated when close inside zone", test_ob_mitigation_by_close)

def test_ob_wick_only_not_mitigated():
    ob = {'type':'BULLISH_OB','zone':[99.0,101.0],'mitigated':False,'midpoint':100.0,'index':0,'time':None}
    update_ob_mitigation([ob], c(102,103,99.5,102.5))  # wick enters, close=102.5 outside
    assert ob['mitigated'] is False  # zone still active
run("OB wick-only NOT mitigated (zone survives for confirmation)", test_ob_wick_only_not_mitigated)

def test_ob_not_mitigated_when_far():
    ob = {'type':'BULLISH_OB','zone':[80.0,85.0],'mitigated':False,'midpoint':82.5,'index':0,'time':None}
    update_ob_mitigation([ob], c(100,105,98,102))
    assert ob['mitigated'] is False
run("OB not mitigated when far above", test_ob_not_mitigated_when_far)

def _fvg(lo,hi,d='BULLISH'):
    return {'type':f'{d}_FVG','zone':[lo,hi],'midpoint':(lo+hi)/2,'filled':False,'size':hi-lo,'index':0,'time':None}
def _ob(lo,hi,d='BULLISH'):
    return {'type':f'{d}_OB','zone':[lo,hi],'midpoint':(lo+hi)/2,'mitigated':False,'index':0,'time':None}

def test_zone_confluence_priority():
    fvg = _fvg(100,105); ob = _ob(102,107)
    conf = find_confluence_zones([fvg],[ob])
    zone = build_entry_zone('LONG',[fvg],[ob],conf,current_price=103.0,atr=5.0)
    assert zone and zone['source']=='CONFLUENCE'
run("zone builder: confluence priority over OB/FVG", test_zone_confluence_priority)

def test_zone_ob_fallback():
    ob = _ob(103,108)
    zone = build_entry_zone('LONG',[],[ob],[],current_price=110.0,atr=15.0)
    assert zone and zone['source']=='ORDER_BLOCK'
run("zone builder: OB fallback", test_zone_ob_fallback)

def test_zone_none_when_empty():
    assert build_entry_zone('LONG',[],[],[],current_price=100.0,atr=5.0) is None
run("zone builder: None when no zones", test_zone_none_when_empty)

def test_zone_rejected_too_far():
    fvg = _fvg(100,105)
    zone = build_entry_zone('LONG',[fvg],[],[],current_price=200.0,atr=5.0)
    assert zone is None
run("zone builder: rejected when > 3×ATR away", test_zone_rejected_too_far)


# ════════════════════════════════════════════════════════════════
# PHASE 5 — TRIGGER DETECTOR
# ════════════════════════════════════════════════════════════════
print("\n🎯 Phase 5 — Trigger Detector")

from phase5_entry.trigger_detector import (
    is_bullish_trigger, is_bearish_trigger,
    is_engulfing_bullish, is_engulfing_bearish, classify_trigger
)

def test_doji_no_crash():
    doji = c(100,100,100,100)
    assert is_bullish_trigger(doji) == False
    assert is_bearish_trigger(doji) == False
run("doji (h==l) no ZeroDivisionError", test_doji_no_crash)

def test_hammer():
    # body=2, lower_wick=8 ≥ body*2, upper_wick=0.5 < body
    hammer = c(98,100.5,90,100)
    assert is_bullish_trigger(hammer)
run("hammer → bullish trigger", test_hammer)

def test_shooting_star():
    # body=0.5, upper_wick=9.5, lower_wick=0.1 < body=0.5
    shoot = c(100,110,100.4,100.5)
    assert is_bearish_trigger(shoot)
run("shooting star → bearish trigger", test_shooting_star)

def test_strong_bull_body():
    # body=5/range=7 = 71%
    bull = c(95,101,94,100)
    assert is_bullish_trigger(bull)
run("strong bullish body (>50% range) → trigger", test_strong_bull_body)

def test_engulfing_bullish():
    prev = c(100,102,95,96,0)   # bearish
    curr = c(94,103,93,101,1)   # bullish engulfing
    assert is_engulfing_bullish(prev, curr)
run("bullish engulfing pattern", test_engulfing_bullish)

def test_engulfing_bearish():
    prev = c(95,102,94,101,0)   # bullish
    curr = c(102,103,93,94,1)   # bearish engulfing
    assert is_engulfing_bearish(prev, curr)
run("bearish engulfing pattern", test_engulfing_bearish)

def test_classify_empty():
    assert classify_trigger([], 'LONG') is None
run("classify_trigger empty → None", test_classify_empty)


# ════════════════════════════════════════════════════════════════
# PHASE 6 — RISK ENGINE
# ════════════════════════════════════════════════════════════════
print("\n⚖️  Phase 6 — Risk Engine")

from phase6_risk.risk_engine import RiskEngine, _calc_atr

def test_atr_returns_float():
    assert isinstance(_calc_atr([c(100,101,99,100,i=i) for i in range(20)]), float)
run("_calc_atr returns float", test_atr_returns_float)

def test_atr_fallback():
    assert _calc_atr([]) == 1.0
run("_calc_atr empty → 1.0", test_atr_fallback)

def test_sl_long_below_entry():
    risk = RiskEngine(10_000.0)
    sl = risk.calc_sl('LONG', 110.0, 90.0, [c(100,101,99,100,i=i) for i in range(20)])
    assert sl is not None and sl < 100.0
run("SL LONG below swing low", test_sl_long_below_entry)

def test_sl_short_above_entry():
    risk = RiskEngine(10_000.0)
    sl = risk.calc_sl('SHORT', 110.0, 90.0, [c(100,101,99,100,i=i) for i in range(20)])
    assert sl is not None and sl > 100.0
run("SL SHORT above swing high", test_sl_short_above_entry)

def test_tp_long_above_entry():
    risk = RiskEngine(10_000.0)
    tps = risk.calc_tp('LONG', 100.0, 95.0, [])
    assert all(tp['level'] > 100.0 for tp in tps)
run("TP LONG all above entry", test_tp_long_above_entry)

def test_tp_sizes_sum():
    risk = RiskEngine(10_000.0)
    tps = risk.calc_tp('LONG', 100.0, 95.0, [])
    assert abs(sum(tp['size_ratio'] for tp in tps) - 1.0) < 0.001
run("TP size_ratio sum = 1.0", test_tp_sizes_sum)

def test_position_size_positive():
    risk = RiskEngine(10_000.0)
    assert risk.calc_position_size(100.0, 95.0) > 0
run("position size > 0", test_position_size_positive)

def test_position_size_sl_too_close():
    risk = RiskEngine(10_000.0)
    assert risk.calc_position_size(100.0, 99.99) == 0.0
run("position size=0 when SL too close", test_position_size_sl_too_close)

def test_negative_balance_no_size():
    risk = RiskEngine(-1000.0)
    assert risk.calc_position_size(100.0, 95.0) == 0.0
run("negative balance → size=0 (no abs() hiding)", test_negative_balance_no_size)

def test_daily_loss_disables():
    risk = RiskEngine(10_000.0)
    risk.register_pnl(-400.0)
    assert risk.trading_enabled is False
run("daily loss >3% disables trading", test_daily_loss_disables)

def test_max_drawdown_disables():
    risk = RiskEngine(10_000.0)
    risk.register_pnl(-1_600.0)
    assert risk.trading_enabled is False
run("drawdown >15% disables trading", test_max_drawdown_disables)

def test_five_losses_disables():
    risk = RiskEngine(10_000.0)
    for _ in range(5):
        risk.register_pnl(-10.0)
    assert risk.trading_enabled is False
run("5 consecutive losses disables trading", test_five_losses_disables)

def test_reset_daily_reenables():
    risk = RiskEngine(10_000.0)
    risk.trading_enabled = False
    risk._consecutive_losses = 3
    risk.reset_daily()
    assert risk.trading_enabled is True
run("reset_daily re-enables trading", test_reset_daily_reenables)

def test_reset_stays_disabled_on_max_dd():
    risk = RiskEngine(10_000.0)
    risk.register_pnl(-1_600.0)
    risk.reset_daily()
    assert risk.trading_enabled is False
run("reset_daily stays disabled when max DD exceeded", test_reset_stays_disabled_on_max_dd)

def test_breakeven_long():
    risk = RiskEngine(10_000.0)
    pos = {'entry':100.0,'sl':95.0,'side':'LONG'}
    assert risk.check_breakeven(pos, 105.0) == 100.0
run("breakeven LONG at +1R", test_breakeven_long)

def test_breakeven_not_yet():
    risk = RiskEngine(10_000.0)
    pos = {'entry':100.0,'sl':95.0,'side':'LONG'}
    assert risk.check_breakeven(pos, 102.0) is None
run("no breakeven when price < +1R", test_breakeven_not_yet)

def test_trailing_stop_uses_last_close_fallback():
    risk = RiskEngine(10_000.0)
    pos = {'entry':100.0,'sl':95.0,'side':'LONG'}  # no current_price
    candles = [c(108,112,106,110,i=i) for i in range(5)]
    result = risk.check_trailing_stop(pos, candles)
    assert result is None or isinstance(result, float)
run("trailing stop no crash without current_price key", test_trailing_stop_uses_last_close_fallback)

def test_trailing_empty_candles():
    risk = RiskEngine(10_000.0)
    pos = {'entry':100.0,'sl':95.0,'side':'LONG','current_price':110.0}
    assert risk.check_trailing_stop(pos, []) is None
run("trailing stop returns None on empty candles", test_trailing_empty_candles)


# ════════════════════════════════════════════════════════════════
# PHASE 1 — VALIDATOR
# ════════════════════════════════════════════════════════════════
print("\n🗄️  Phase 1 — Validator")

from phase1_data.validator import validate_candle, validate_candles

def test_good_candle():
    good = {'open':100,'high':105,'low':98,'close':103,'volume':1000}
    assert validate_candle(good)
run("valid candle passes", test_good_candle)

def test_high_lt_open_rejected():
    bad = {'open':100,'high':99,'low':98,'close':103,'volume':1000}
    assert not validate_candle(bad)
run("high < open → rejected", test_high_lt_open_rejected)

def test_zero_price_rejected():
    bad = {'open':0,'high':0,'low':0,'close':0,'volume':100}
    assert not validate_candle(bad)
run("zero price → rejected", test_zero_price_rejected)

def test_negative_volume_rejected():
    bad = {'open':100,'high':105,'low':98,'close':103,'volume':-1}
    assert not validate_candle(bad)
run("negative volume → rejected", test_negative_volume_rejected)

def test_missing_keys_rejected():
    assert not validate_candle({})
    assert not validate_candle({'open':100})
run("missing OHLCV keys → rejected", test_missing_keys_rejected)

def test_validate_candles_filters():
    candles = [
        {'open':100,'high':105,'low':98,'close':103,'volume':1000},
        {'open':100,'high':99,'low':98,'close':103,'volume':1000},  # bad
    ]
    valid = validate_candles(candles)
    assert len(valid) == 1
run("validate_candles filters bad candles", test_validate_candles_filters)


# ════════════════════════════════════════════════════════════════
# BACKTEST SMOKE
# ════════════════════════════════════════════════════════════════
print("\n🔬 Backtest Engine")

from phase7_backtest.backtest_engine import BacktestEngine

def test_backtest_smoke():
    engine = BacktestEngine("BTCUSDT", "1h", initial_balance=10_000.0)
    result = engine.run(candles_up(100), warmup=20)
    assert isinstance(result, dict)
    for key in ['total_trades','winrate','profit_factor','net_profit_pct','max_drawdown','sharpe_ratio']:
        assert key in result, f"missing: {key}"
run("backtest completes, all keys present", test_backtest_smoke)

def test_backtest_too_few_candles():
    engine = BacktestEngine("BTCUSDT", "1h")
    result = engine.run([c(100,101,99,100,i=i) for i in range(5)], warmup=50)
    assert result['total_trades'] == 0
run("backtest: 0 trades when fewer candles than warmup", test_backtest_too_few_candles)

def test_backtest_balance_never_negative():
    engine = BacktestEngine("BTCUSDT", "1h", initial_balance=10_000.0)
    engine.run(candles_up(200), warmup=20)
    for eq in engine._equity:
        assert eq['balance'] >= 0, f"balance went negative: {eq['balance']}"
run("backtest: balance never negative", test_backtest_balance_never_negative)


# ════════════════════════════════════════════════════════════════
# SUMMARY
# ════════════════════════════════════════════════════════════════
print(f"\n{'═'*55}")
print(f"  Results: {PASS} passed, {FAIL} failed  (total {PASS+FAIL})")
if ERRORS:
    print(f"\n  Failed tests:")
    for name, exc in ERRORS:
        print(f"    ❌ {name}")
        print(f"         {type(exc).__name__}: {exc}")
        tb = traceback.format_exc()
        for line in tb.strip().split('\n')[-4:]:
            print(f"         {line}")
print(f"{'═'*55}")
sys.exit(0 if FAIL == 0 else 1)
