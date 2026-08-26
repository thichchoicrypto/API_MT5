"""
Phase 1.4 — PostgreSQL Database Layer.
Handles candle storage, retrieval, and gap detection.

Forex vs OKX differences:
- No funding_rates or open_interest tables (Forex has no funding rates)
- DB name: forex_scalper_db (see settings.py)
- Weekend candle awareness in find_missing_candles
"""
import asyncio
from datetime import datetime, timezone
from typing import List, Optional
import asyncpg
from utils.logger import logger
from config.settings import DATABASE_URL


CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS candles (
    id          BIGSERIAL PRIMARY KEY,
    symbol      VARCHAR(20) NOT NULL,
    timeframe   VARCHAR(5)  NOT NULL,
    open_time   TIMESTAMPTZ NOT NULL,
    open        DOUBLE PRECISION NOT NULL,
    high        DOUBLE PRECISION NOT NULL,
    low         DOUBLE PRECISION NOT NULL,
    close       DOUBLE PRECISION NOT NULL,
    volume      DOUBLE PRECISION NOT NULL,
    UNIQUE (symbol, timeframe, open_time)
);

CREATE INDEX IF NOT EXISTS idx_candles_symbol_tf_time
    ON candles (symbol, timeframe, open_time DESC);

CREATE TABLE IF NOT EXISTS live_trades (
    id          BIGSERIAL PRIMARY KEY,
    order_id    VARCHAR(60)  NOT NULL UNIQUE,
    symbol      VARCHAR(20)  NOT NULL,
    side        VARCHAR(10)  NOT NULL,
    entry_price DOUBLE PRECISION,
    exit_price  DOUBLE PRECISION,
    sl          DOUBLE PRECISION,
    tp          DOUBLE PRECISION,
    size        DOUBLE PRECISION NOT NULL,   -- units (OANDA)
    pnl         DOUBLE PRECISION,
    status      VARCHAR(20),
    opened_at   TIMESTAMPTZ NOT NULL,
    closed_at   TIMESTAMPTZ,
    balance_after DOUBLE PRECISION,
    note        TEXT
);

CREATE INDEX IF NOT EXISTS idx_live_trades_symbol
    ON live_trades (symbol, opened_at DESC);

CREATE TABLE IF NOT EXISTS paper_trades (
    id          BIGSERIAL PRIMARY KEY,
    order_id    VARCHAR(60)  NOT NULL UNIQUE,
    symbol      VARCHAR(20)  NOT NULL,
    side        VARCHAR(10)  NOT NULL,
    entry_price DOUBLE PRECISION NOT NULL,
    exit_price  DOUBLE PRECISION,
    sl          DOUBLE PRECISION,
    tp          DOUBLE PRECISION,
    size        DOUBLE PRECISION NOT NULL,
    pnl         DOUBLE PRECISION,
    status      VARCHAR(20),
    opened_at   TIMESTAMPTZ NOT NULL,
    closed_at   TIMESTAMPTZ,
    mode        VARCHAR(10)  DEFAULT 'paper'
);

CREATE INDEX IF NOT EXISTS idx_paper_trades_symbol
    ON paper_trades (symbol, opened_at DESC);

CREATE TABLE IF NOT EXISTS candle_tracker_backtest (
    id              BIGSERIAL PRIMARY KEY,
    symbol          VARCHAR(20)  NOT NULL,
    timeframe       VARCHAR(5)   NOT NULL,
    candle_time     TIMESTAMPTZ  NOT NULL,
    side            VARCHAR(10),
    trend           VARCHAR(20),
    last_swing_high DOUBLE PRECISION,
    last_swing_low  DOUBLE PRECISION,
    bos_type        VARCHAR(20),
    sweep_type      VARCHAR(30),
    choch_type      VARCHAR(30),
    mtf_bias        VARCHAR(10),
    zone_type       VARCHAR(20),
    zone_low        DOUBLE PRECISION,
    zone_high       DOUBLE PRECISION,
    l1_trend        BOOLEAN,
    l2_zone_touch   BOOLEAN,
    l3_liquidity    BOOLEAN,
    l4_volume       BOOLEAN,
    l5_trigger      VARCHAR(30),
    l6_risk         BOOLEAN,
    sl              DOUBLE PRECISION,
    tp1             DOUBLE PRECISION,
    rr              DOUBLE PRECISION,
    signal_side     VARCHAR(10),
    order_placed    BOOLEAN DEFAULT FALSE,
    order_type      VARCHAR(10),
    entry_price     DOUBLE PRECISION,
    trade_closed    BOOLEAN DEFAULT FALSE,
    exit_price      DOUBLE PRECISION,
    pnl             DOUBLE PRECISION,
    exit_reason     VARCHAR(10),
    stop_reason     VARCHAR(50),
    eligible        BOOLEAN DEFAULT FALSE,
    balance         DOUBLE PRECISION,
    risk_pct        DOUBLE PRECISION,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (symbol, timeframe, candle_time, side)
);

CREATE INDEX IF NOT EXISTS idx_ct_backtest_symbol
    ON candle_tracker_backtest (symbol, timeframe, candle_time DESC);

CREATE TABLE IF NOT EXISTS candle_tracker_live (
    id              BIGSERIAL PRIMARY KEY,
    symbol          VARCHAR(20)  NOT NULL,
    timeframe       VARCHAR(5)   NOT NULL,
    candle_time     TIMESTAMPTZ  NOT NULL,
    side            VARCHAR(10),
    trend           VARCHAR(20),
    last_swing_high DOUBLE PRECISION,
    last_swing_low  DOUBLE PRECISION,
    bos_type        VARCHAR(20),
    sweep_type      VARCHAR(30),
    choch_type      VARCHAR(30),
    mtf_bias        VARCHAR(10),
    zone_type       VARCHAR(20),
    zone_low        DOUBLE PRECISION,
    zone_high       DOUBLE PRECISION,
    l1_trend        BOOLEAN,
    l2_zone_touch   BOOLEAN,
    l3_liquidity    BOOLEAN,
    l4_volume       BOOLEAN,
    l5_trigger      VARCHAR(30),
    l6_risk         BOOLEAN,
    sl              DOUBLE PRECISION,
    tp1             DOUBLE PRECISION,
    rr              DOUBLE PRECISION,
    signal_side     VARCHAR(10),
    order_placed    BOOLEAN DEFAULT FALSE,
    order_type      VARCHAR(10),
    entry_price     DOUBLE PRECISION,
    trade_closed    BOOLEAN DEFAULT FALSE,
    exit_price      DOUBLE PRECISION,
    pnl             DOUBLE PRECISION,
    exit_reason     VARCHAR(10),
    stop_reason     VARCHAR(50),
    eligible        BOOLEAN DEFAULT FALSE,
    balance         DOUBLE PRECISION,
    risk_pct        DOUBLE PRECISION,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (symbol, timeframe, candle_time, side)
);

CREATE INDEX IF NOT EXISTS idx_ct_live_symbol
    ON candle_tracker_live (symbol, timeframe, candle_time DESC);

-- Migration: add balance column if not exists
ALTER TABLE candle_tracker_backtest ADD COLUMN IF NOT EXISTS balance  DOUBLE PRECISION;
ALTER TABLE candle_tracker_live     ADD COLUMN IF NOT EXISTS balance  DOUBLE PRECISION;
ALTER TABLE candle_tracker_backtest ADD COLUMN IF NOT EXISTS risk_pct DOUBLE PRECISION;
ALTER TABLE candle_tracker_live     ADD COLUMN IF NOT EXISTS risk_pct DOUBLE PRECISION;
ALTER TABLE candle_tracker_backtest ADD COLUMN IF NOT EXISTS sl_dist  DOUBLE PRECISION;
ALTER TABLE candle_tracker_live     ADD COLUMN IF NOT EXISTS sl_dist  DOUBLE PRECISION;
ALTER TABLE candle_tracker_backtest ADD COLUMN IF NOT EXISTS tp_dist  DOUBLE PRECISION;
ALTER TABLE candle_tracker_live     ADD COLUMN IF NOT EXISTS tp_dist  DOUBLE PRECISION;
ALTER TABLE candle_tracker_backtest ADD COLUMN IF NOT EXISTS lots     DOUBLE PRECISION;
ALTER TABLE candle_tracker_live     ADD COLUMN IF NOT EXISTS lots     DOUBLE PRECISION;
"""


class Database:
    def __init__(self, dsn: str = DATABASE_URL):
        self.dsn = dsn
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self, retries: int = 5):
        for attempt in range(retries):
            try:
                self.pool = await asyncpg.create_pool(
                    self.dsn,
                    min_size=2,
                    max_size=10,
                    command_timeout=30,
                    server_settings={"application_name": "forex_smc_scalper"},
                )
                async with self.pool.acquire() as conn:
                    await conn.execute(CREATE_TABLES_SQL)
                logger.info("Database connected and schema ensured")
                return
            except Exception as e:
                wait = 2 ** attempt
                logger.error(f"DB connect failed (attempt {attempt+1}/{retries}): {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(wait)
        raise RuntimeError("Cannot connect to database after multiple retries")

    async def disconnect(self):
        if self.pool:
            await self.pool.close()
            logger.info("Database disconnected")

    # ─────────────────────────────────────────
    # CANDLES
    # ─────────────────────────────────────────
    async def upsert_candle(self, symbol: str, timeframe: str, candle: dict) -> bool:
        sql = """
            INSERT INTO candles (symbol, timeframe, open_time, open, high, low, close, volume)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (symbol, timeframe, open_time) DO UPDATE SET
                open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
                close=EXCLUDED.close, volume=EXCLUDED.volume
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(sql,
                    symbol, timeframe,
                    candle["open_time"], candle["open"], candle["high"],
                    candle["low"], candle["close"], candle["volume"])
            return True
        except Exception as e:
            logger.error(f"upsert_candle error: {e}")
            return False

    async def upsert_candles_bulk(self, symbol: str, timeframe: str, candles: List[dict]) -> int:
        if not candles:
            return 0
        sql = """
            INSERT INTO candles (symbol, timeframe, open_time, open, high, low, close, volume)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (symbol, timeframe, open_time) DO NOTHING
        """
        rows = [(symbol, timeframe,
                 c["open_time"], c["open"], c["high"], c["low"], c["close"], c["volume"])
                for c in candles]
        try:
            async with self.pool.acquire() as conn:
                await conn.executemany(sql, rows)
            logger.debug(f"Bulk inserted {len(rows)} candles for {symbol} {timeframe}")
            return len(rows)
        except Exception as e:
            logger.error(f"upsert_candles_bulk error: {e}")
            return 0

    async def get_candles(self, symbol: str, timeframe: str,
                          limit: int = 500,
                          since: Optional[datetime] = None) -> List[dict]:
        if since:
            sql = """SELECT open_time, open, high, low, close, volume FROM candles
                     WHERE symbol=$1 AND timeframe=$2 AND open_time >= $3
                     ORDER BY open_time ASC LIMIT $4"""
            params = (symbol, timeframe, since, limit)
        else:
            sql = """SELECT open_time, open, high, low, close, volume FROM candles
                     WHERE symbol=$1 AND timeframe=$2
                     ORDER BY open_time DESC LIMIT $3"""
            params = (symbol, timeframe, limit)

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)

        result = [dict(r) for r in rows]
        if not since:
            result.reverse()
        return result

    async def get_latest_open_time(self, symbol: str, timeframe: str) -> Optional[datetime]:
        sql = "SELECT MAX(open_time) FROM candles WHERE symbol=$1 AND timeframe=$2"
        async with self.pool.acquire() as conn:
            val = await conn.fetchval(sql, symbol, timeframe)
        return val

    async def get_earliest_open_time(self, symbol: str, timeframe: str) -> Optional[datetime]:
        sql = "SELECT MIN(open_time) FROM candles WHERE symbol=$1 AND timeframe=$2"
        async with self.pool.acquire() as conn:
            val = await conn.fetchval(sql, symbol, timeframe)
        return val

    async def count_candles(self, symbol: str, timeframe: str) -> int:
        sql = "SELECT COUNT(*) FROM candles WHERE symbol=$1 AND timeframe=$2"
        async with self.pool.acquire() as conn:
            return await conn.fetchval(sql, symbol, timeframe)

    async def find_missing_candles(self, symbol: str, timeframe: str,
                                   start: datetime, end: datetime) -> List[datetime]:
        """Return list of expected open_times missing in DB.
        Skips weekend periods (Forex market closed).
        """
        from phase1_data.validator import tf_to_seconds, is_weekend_candle
        step = tf_to_seconds(timeframe)

        ts_start = int(start.timestamp())
        ts_start = ts_start - (ts_start % step)
        ts_end   = int(end.timestamp())
        ts_end   = ts_end - (ts_end % step) - step

        if ts_end < ts_start:
            return []

        aligned_start = datetime.fromtimestamp(ts_start, tz=timezone.utc)
        aligned_end   = datetime.fromtimestamp(ts_end,   tz=timezone.utc)

        sql = """SELECT open_time FROM candles WHERE symbol=$1 AND timeframe=$2
                 AND open_time BETWEEN $3 AND $4 ORDER BY open_time"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, symbol, timeframe, aligned_start, aligned_end)

        existing = {r["open_time"].replace(tzinfo=timezone.utc) for r in rows}
        expected = set()
        ts = ts_start
        while ts <= ts_end:
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            if not is_weekend_candle(dt):   # skip weekend hours
                expected.add(dt)
            ts += step

        missing = sorted(expected - existing)
        return missing

    # ─────────────────────────────────────────
    # LIVE TRADES
    # ─────────────────────────────────────────
    async def save_live_trade_open(self, order_id: str, symbol: str, side: str,
                                   entry_price: float, sl: float, tp: float,
                                   size: float, balance: float):
        sql = """
            INSERT INTO live_trades
                (order_id, symbol, side, entry_price, sl, tp, size, opened_at, balance_after)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
            ON CONFLICT (order_id) DO NOTHING
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(sql, order_id, symbol, side,
                                   entry_price, sl, tp, size,
                                   datetime.now(tz=timezone.utc), balance)
            logger.debug(f"Live trade saved: {order_id} {side} {symbol}")
        except Exception as e:
            logger.error(f"save_live_trade_open error: {e}")

    async def save_live_trade_close(self, order_id: str, exit_price: float,
                                    pnl: float, status: str, balance: float):
        sql = """
            UPDATE live_trades
            SET exit_price=$1, pnl=$2, status=$3, closed_at=$4, balance_after=$5
            WHERE order_id=$6
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(sql, exit_price, pnl, status,
                                   datetime.now(tz=timezone.utc), balance, order_id)
        except Exception as e:
            logger.error(f"save_live_trade_close error: {e}")

    async def get_open_live_trades(self) -> List[dict]:
        sql = """SELECT * FROM live_trades
                 WHERE closed_at IS NULL
                 AND entry_price IS NOT NULL
                 AND size > 0
                 ORDER BY opened_at ASC"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql)
        return [dict(r) for r in rows]

    async def get_live_trades(self, symbol: str = None, limit: int = 100) -> List[dict]:
        if symbol:
            sql = """SELECT * FROM live_trades WHERE symbol=$1
                     ORDER BY opened_at DESC LIMIT $2"""
            params = (symbol, limit)
        else:
            sql = "SELECT * FROM live_trades ORDER BY opened_at DESC LIMIT $1"
            params = (limit,)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        return [dict(r) for r in rows]

    # ─────────────────────────────────────────
    # PAPER TRADES
    # ─────────────────────────────────────────
    async def save_paper_trade_open(self, position: dict):
        sql = """
            INSERT INTO paper_trades
                (order_id, symbol, side, entry_price, sl, tp, size, opened_at, mode)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'paper')
            ON CONFLICT (order_id) DO NOTHING
        """
        tp_level = position["tp"][0]["level"] if position.get("tp") else None
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(sql,
                    position["id"], position["symbol"], position["side"],
                    position["entry"], position.get("sl"), tp_level,
                    position["size"], position["opened_at"])
        except Exception as e:
            logger.error(f"save_paper_trade_open error: {e}")

    async def save_paper_trade_close(self, position: dict):
        sql = """
            UPDATE paper_trades
            SET exit_price=$1, pnl=$2, status=$3, closed_at=$4
            WHERE order_id=$5
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(sql,
                    position.get("exit"), position.get("pnl"),
                    position.get("status"), position.get("closed_at"),
                    position["id"])
        except Exception as e:
            logger.error(f"save_paper_trade_close error: {e}")

    async def get_paper_trades(self, symbol: str = None, limit: int = 100) -> List[dict]:
        if symbol:
            sql = """SELECT * FROM paper_trades WHERE symbol=$1
                     ORDER BY opened_at DESC LIMIT $2"""
            params = (symbol, limit)
        else:
            sql = "SELECT * FROM paper_trades ORDER BY opened_at DESC LIMIT $1"
            params = (limit,)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        return [dict(r) for r in rows]

    # ─────────────────────────────────────────
    # CANDLE TRACKER
    # ─────────────────────────────────────────
    async def save_candle_tracker(self, record: dict,
                                   table: str = "candle_tracker_backtest"):
        def _bool(v):
            return bool(v) if v is not None else None
        sql = f"""
            INSERT INTO {table} (
                symbol, timeframe, candle_time, side,
                trend, last_swing_high, last_swing_low, bos_type,
                sweep_type, choch_type, mtf_bias,
                zone_type, zone_low, zone_high,
                l1_trend, l2_zone_touch, l3_liquidity, l4_volume, l5_trigger,
                l6_risk, sl, tp1, rr,
                signal_side, order_placed, order_type, entry_price,
                trade_closed, exit_price, pnl, exit_reason,
                stop_reason, eligible, balance, risk_pct,
                sl_dist, tp_dist, lots
            ) VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,
                $12,$13,$14,$15,$16,$17,$18,$19,
                $20,$21,$22,$23,$24,$25,$26,$27,
                $28,$29,$30,$31,$32,$33,$34,$35,
                $36,$37,$38
            )
            ON CONFLICT (symbol, timeframe, candle_time, side)
            DO UPDATE SET
                trend=$5, last_swing_high=$6, last_swing_low=$7, bos_type=$8,
                sweep_type=$9, choch_type=$10, mtf_bias=$11,
                zone_type=$12, zone_low=$13, zone_high=$14,
                l1_trend=$15, l2_zone_touch=$16, l3_liquidity=$17,
                l4_volume=$18, l5_trigger=$19,
                l6_risk=$20, sl=$21, tp1=$22, rr=$23,
                signal_side=$24, order_placed=$25, order_type=$26, entry_price=$27,
                trade_closed=$28, exit_price=$29, pnl=$30, exit_reason=$31,
                stop_reason=$32, eligible=$33, balance=$34, risk_pct=$35,
                sl_dist=$36, tp_dist=$37, lots=$38
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(sql,
                    record.get("symbol"), record.get("timeframe"),
                    record.get("candle_time"), record.get("side"),
                    record.get("trend"), record.get("last_swing_high"),
                    record.get("last_swing_low"), record.get("bos_type"),
                    record.get("sweep_type"), record.get("choch_type"),
                    record.get("mtf_bias"),
                    record.get("zone_type"), record.get("zone_low"),
                    record.get("zone_high"),
                    _bool(record.get("l1_trend")),
                    _bool(record.get("l2_zone_touch")),
                    _bool(record.get("l3_liquidity")),
                    _bool(record.get("l4_volume")),
                    record.get("l5_trigger"),
                    _bool(record.get("l6_risk")),
                    record.get("sl"), record.get("tp1"), record.get("rr"),
                    record.get("signal_side"),
                    _bool(record.get("order_placed", False)),
                    record.get("order_type"), record.get("entry_price"),
                    _bool(record.get("trade_closed", False)),
                    record.get("exit_price"), record.get("pnl"),
                    record.get("exit_reason"), record.get("stop_reason"),
                    _bool(record.get("eligible", False)),
                    record.get("balance"),
                    record.get("risk_pct"),
                    record.get("sl_dist"),
                    record.get("tp_dist"),
                    record.get("lots"),
                )
        except Exception as e:
            logger.error(f"save_candle_tracker error: {e}")

    async def bulk_save_candle_tracker(self, records: list,
                                        table: str = "candle_tracker_backtest"):
        if not records:
            return
        for record in records:
            await self.save_candle_tracker(record, table=table)
        logger.info(f"Saved {len(records)} {table} records")

    async def update_candle_tracker_outcome(self, symbol: str, timeframe: str,
                                            candle_time, side: str,
                                            exit_price: float, pnl: float,
                                            exit_reason: str,
                                            table: str = "candle_tracker_live"):
        sql = f"""
            UPDATE {table}
            SET trade_closed = TRUE,
                exit_price   = $1,
                pnl          = $2,
                exit_reason  = $3
            WHERE symbol       = $4
              AND timeframe    = $5
              AND candle_time  = $6
              AND side         = $7
              AND order_placed = TRUE
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(sql, exit_price, pnl, exit_reason,
                                   symbol, timeframe, candle_time, side)
        except Exception as e:
            logger.error(f"update_candle_tracker_outcome error: {e}")

    async def get_candle_tracker(self, symbol: str, timeframe: str,
                                  limit: int = 200,
                                  table: str = "candle_tracker_backtest") -> List[dict]:
        sql = f"""SELECT * FROM {table}
                 WHERE symbol=$1 AND timeframe=$2
                 ORDER BY candle_time DESC LIMIT $3"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, symbol, timeframe, limit)
        return [dict(r) for r in rows]
