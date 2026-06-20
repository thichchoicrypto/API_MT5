# API Sources — Forex SMC Scalper

## 1. OANDA v20 REST API (Primary)
- Historical candles: `GET /v3/instruments/{instrument}/candles`
- Account info + balance: `GET /v3/accounts/{accountID}`
- Order execution: `POST /v3/accounts/{accountID}/orders`
- Positions: `GET /v3/accounts/{accountID}/positions`
- Practice URL: `https://api-fxpractice.oanda.com`
- Live URL: `https://api-fxtrade.oanda.com`
- Docs: https://developer.oanda.com/rest-live-v20/introduction/

## 2. OANDA v20 Streaming API (Real-time)
- Price stream (SSE): `GET /v3/accounts/{accountID}/pricing/stream`
- Used to build real-time candles (tick → OHLCV aggregation)
- Same base URL as REST

## 3. MetaTrader 5 Python API (Secondary / Backup)
- Historical candles via `MetaTrader5` Python package
- Windows-only (requires MT5 terminal running locally)
- Used as fallback data source or for additional historical depth
- Docs: https://www.mql5.com/en/docs/python_metatrader5
- Install: `pip install MetaTrader5`

## Notes
- No Coinglass/funding rate data (Forex has no funding rates)
- Spread is embedded in bid/ask prices — use mid-price for SMC analysis
- Market hours: Mon 00:00 UTC – Fri 22:00 UTC (approximate, varies by broker)
- Weekend gaps must be filtered in candle validation
