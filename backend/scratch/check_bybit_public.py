import urllib.request
import json

def check_symbol(symbol):
    try:
        url = f"https://www.okx.com/api/v5/market/candles?instId={symbol}&bar=1m&limit=1"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            if data.get("retCode") == 0:
                klines = data.get("result", {}).get("list", [])
                print(f"{symbol}: {len(klines)} klines")
            else:
                print(f"{symbol}: Error {data.get('retCode')} - {data.get('retMsg')}")
    except Exception as e:
        print(f"{symbol}: Exception {e}")

if __name__ == "__main__":
    check_symbol("FETUSDT")
    check_symbol("ASIUSDT")
    check_symbol("OPUSDT")
