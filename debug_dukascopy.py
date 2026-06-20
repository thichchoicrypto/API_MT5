"""Debug Dukascopy API — chạy trực tiếp để xem raw response."""
import urllib.request
import time
import json

now_ms   = int(time.time() * 1000)
start_ms = now_ms - 7 * 86400 * 1000  # 7 ngày trước

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer":    "https://www.dukascopy.com/",
    "Accept":     "application/json, text/plain, */*",
}

tests = {
    "freeserv_P_end":    f"https://freeserv.dukascopy.com/2.0/?path=chart/json&instrument=EURUSD&offer_side=B&interval=MIN15&splits=false&stocks=false&auth_token=&time_direction=P&end={now_ms}&count=5",
    "freeserv_F_start":  f"https://freeserv.dukascopy.com/2.0/?path=chart/json&instrument=EURUSD&offer_side=B&interval=MIN15&splits=false&stocks=false&auth_token=&time_direction=F&start={start_ms}&count=5",
    "freeserv_startend": f"https://freeserv.dukascopy.com/2.0/?path=chart/json&instrument=EURUSD&offer_side=B&interval=MIN15&splits=false&stocks=false&auth_token=&start={start_ms}&end={now_ms}&count=5",
    "datafeed_chart":    f"https://datafeed.dukascopy.com/datafeed/chart/1.0/EURUSD/MIN15/BID/from={start_ms}/to={now_ms}/limit=5",
}

for name, url in tests.items():
    print(f"\n{'='*60}")
    print(f"[{name}]")
    print(f"URL: {url[:100]}...")
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read().decode()
            print(f"Status : {r.status}")
            print(f"Headers: {dict(r.headers)}")
            print(f"Body   : {body[:500]}")
            try:
                parsed = json.loads(body)
                print(f"JSON   : {type(parsed)} len={len(parsed) if isinstance(parsed, (list,dict)) else 'N/A'}")
            except Exception:
                print("Body is not JSON")
    except Exception as e:
        print(f"ERROR  : {e}")
