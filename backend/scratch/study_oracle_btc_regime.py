import json
import time
from bisect import bisect_right

import requests


BASE_URL = "https://www.okx.com/api/v5/market/history-candles"
INST_ID = "BTC-USDT-SWAP"
PERIOD = 14
LOOKBACK_DAYS = 35
PAGE_LIMIT = 100

BASE_THRESHOLDS = {"dead": 22.0, "trend": 25.0, "strong": 30.0}

THRESHOLD_CONFIGS = [
    {"dead": 22, "trend": 25, "strong": 30},
]

# Cached candle data
_candles_1h = []
_candles_4h = []
_candles_15m = []
_ts_4h = []
_ts_15m = []
_cutoff_ms = 0


def fetch_candles(bar: str, min_ts_ms: int, limit: int = PAGE_LIMIT):
    session = requests.Session()
    rows = []
    after = None
    while True:
        params = {"instId": INST_ID, "bar": bar, "limit": str(limit)}
        if after is not None:
            params["after"] = str(after)
        response = session.get(BASE_URL, params=params, timeout=20)
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data", [])
        if not data:
            break
        rows.extend(data)
        oldest_ts = int(data[-1][0])
        if oldest_ts <= min_ts_ms:
            break
        after = oldest_ts
        time.sleep(0.05)
    unique = {int(row[0]): row for row in rows}
    ordered = [unique[ts] for ts in sorted(unique)]
    return [row for row in ordered if int(row[0]) >= min_ts_ms]


def calculate_adx(candles):
    if len(candles) < PERIOD * 3:
        return 0.0
    highs = [float(c[2]) for c in candles]
    lows = [float(c[3]) for c in candles]
    closes = [float(c[4]) for c in candles]
    tr_values, plus_dm_values, minus_dm_values = [], [], []
    for idx in range(1, len(candles)):
        high_diff = highs[idx] - highs[idx - 1]
        low_diff = lows[idx - 1] - lows[idx]
        tr = max(highs[idx] - lows[idx], abs(highs[idx] - closes[idx - 1]), abs(lows[idx] - closes[idx - 1]))
        tr_values.append(tr)
        plus_dm_values.append(high_diff if high_diff > low_diff and high_diff > 0 else 0.0)
        minus_dm_values.append(low_diff if low_diff > high_diff and low_diff > 0 else 0.0)
    atr = sum(tr_values[:PERIOD]) / PERIOD
    plus_smoothed = sum(plus_dm_values[:PERIOD]) / PERIOD
    minus_smoothed = sum(minus_dm_values[:PERIOD]) / PERIOD
    dx_values = []
    for idx in range(PERIOD, len(tr_values)):
        atr = ((atr * (PERIOD - 1)) + tr_values[idx]) / PERIOD
        plus_smoothed = ((plus_smoothed * (PERIOD - 1)) + plus_dm_values[idx]) / PERIOD
        minus_smoothed = ((minus_smoothed * (PERIOD - 1)) + minus_dm_values[idx]) / PERIOD
        plus_di = (plus_smoothed / atr * 100) if atr else 0.0
        minus_di = (minus_smoothed / atr * 100) if atr else 0.0
        dx_values.append(abs(plus_di - minus_di) / (plus_di + minus_di) * 100 if (plus_di + minus_di) else 0.0)
    adx = sum(dx_values[:PERIOD]) / PERIOD
    for idx in range(PERIOD, len(dx_values)):
        adx = ((adx * (PERIOD - 1)) + dx_values[idx]) / PERIOD
    return adx


def pct_variation(last_two_candles):
    if len(last_two_candles) < 2:
        return 0.0
    prev_close = float(last_two_candles[-2][4])
    last_close = float(last_two_candles[-1][4])
    return ((last_close - prev_close) / prev_close) * 100 if prev_close else 0.0


def classify_regime(m_adx: float, th: dict) -> str:
    if m_adx >= th["strong"]:
        return "ROARING"
    if m_adx >= th["trend"]:
        return "TRENDING"
    if m_adx >= th["dead"]:
        return "TRANSITION"
    return "RANGING"


def classify_direction(m_adx: float, var_1h: float, var_15m: float, dead: float) -> str:
    if m_adx < dead:
        return "LATERAL"
    if var_1h > 0 and var_15m > 0:
        return "UP"
    if var_1h < 0 and var_15m < 0:
        return "DOWN"
    return "LATERAL"


def summarize_zone(samples, zone_name: str):
    zone_samples = [sample for sample in samples if sample["zone"] == zone_name]
    if not zone_samples:
        return None
    next_moves = [abs(sample["next_4h_move"]) for sample in zone_samples if sample["next_4h_move"] is not None]
    return {
        "count": len(zone_samples),
        "pct": round((len(zone_samples) / len(samples)) * 100, 2),
        "avg_madx": round(sum(sample["m_adx"] for sample in zone_samples) / len(zone_samples), 2),
        "avg_abs_next_4h_move_pct": round(sum(next_moves) / len(next_moves), 3) if next_moves else None,
        "direction_mix": {
            "UP": sum(1 for sample in zone_samples if sample["direction"] == "UP"),
            "DOWN": sum(1 for sample in zone_samples if sample["direction"] == "DOWN"),
            "LATERAL": sum(1 for sample in zone_samples if sample["direction"] == "LATERAL"),
        },
    }


def run_study(thresholds: dict) -> dict:
    samples = []
    for idx_1h, candle_1h in enumerate(_candles_1h):
        ts = int(candle_1h[0])
        if ts < _cutoff_ms or idx_1h < 60:
            continue
        idx_4h = bisect_right(_ts_4h, ts) - 1
        idx_15m = bisect_right(_ts_15m, ts) - 1
        if idx_4h < 60 or idx_15m < 60:
            continue
        adx_1h = calculate_adx(_candles_1h[max(0, idx_1h - 143):idx_1h + 1])
        adx_4h = calculate_adx(_candles_4h[max(0, idx_4h - 143):idx_4h + 1])
        adx_15m = calculate_adx(_candles_15m[max(0, idx_15m - 143):idx_15m + 1])
        m_adx = (adx_4h * 0.40) + (adx_1h * 0.40) + (adx_15m * 0.20)
        var_1h = pct_variation(_candles_1h[idx_1h - 1:idx_1h + 1])
        var_15m = pct_variation(_candles_15m[idx_15m - 1:idx_15m + 1])
        direction = classify_direction(m_adx, var_1h, var_15m, thresholds["dead"])
        next_4h_move = None
        if idx_1h + 4 < len(_candles_1h):
            current_close = float(candle_1h[4])
            future_close = float(_candles_1h[idx_1h + 4][4])
            next_4h_move = ((future_close - current_close) / current_close) * 100 if current_close else 0.0
        samples.append({
            "ts": ts, "m_adx": round(m_adx, 2),
            "zone": classify_regime(m_adx, thresholds), "direction": direction,
            "var_1h": round(var_1h, 4), "var_15m": round(var_15m, 4),
            "next_4h_move": round(next_4h_move, 4) if next_4h_move is not None else None,
        })
    return {
        "thresholds": thresholds,
        "sample_count": len(samples),
        "current_snapshot": samples[-1] if samples else None,
        "zones": {z: summarize_zone(samples, z) for z in ["RANGING", "TRANSITION", "TRENDING", "ROARING"]},
    }


def main():
    global _candles_1h, _candles_4h, _candles_15m, _ts_4h, _ts_15m, _cutoff_ms
    now_ms = int(time.time() * 1000)
    _cutoff_ms = now_ms - (LOOKBACK_DAYS * 24 * 60 * 60 * 1000)
    print(f"Buscando {LOOKBACK_DAYS} dias de dados BTC OKX...")
    _candles_1h = fetch_candles("1H", _cutoff_ms - (200 * 60 * 60 * 1000))
    _candles_4h = fetch_candles("4H", _cutoff_ms - (200 * 4 * 60 * 60 * 1000))
    _candles_15m = fetch_candles("15m", _cutoff_ms - (200 * 15 * 60 * 1000))
    _ts_4h = [int(row[0]) for row in _candles_4h]
    _ts_15m = [int(row[0]) for row in _candles_15m]

    print(f"\n{'='*80}")
    print(f"ORACLE ADX CALIBRATION STUDY — {LOOKBACK_DAYS} dias BTC OKX")
    print(f"{'='*80}\n")

    results = []
    for config in THRESHOLD_CONFIGS:
        report = run_study(config)
        zones = report["zones"]
        results.append(report)
        print(f"[CFG] ADX: dead={config['dead']}, trend={config['trend']}, strong={config['strong']}")
        print(f"{'-'*75}")
        print(f"{'Zona':<15} {'%tempo':<10} {'ADX':<8} {'Mov4h':<10} {'UP/DOWN/LAT':<18}")
        print(f"{'-'*75}")
        for zn in ["RANGING", "TRANSITION", "TRENDING", "ROARING"]:
            z = zones.get(zn)
            if z:
                dm = z["direction_mix"]
                mov = f"{z['avg_abs_next_4h_move_pct']:.3f}%" if z['avg_abs_next_4h_move_pct'] else "N/A"
                print(f"  {zn:<13} {z['pct']:<8.1f}% {z['avg_madx']:<6.1f} {mov:<9} {dm['UP']}/{dm['DOWN']}/{dm['LATERAL']}")
        print(f"{'-'*75}")

    print(f"\n{'='*80}")
    print("COMPARATIVO: Movimento médio 4h por threshold")
    print(f"{'='*80}")
    print(f"{'Config':<30} {'RANGING':<12} {'TRANSITION':<14} {'TRENDING':<12} {'ROARING':<12}")
    print(f"{'-'*80}")
    for r in results:
        cfg = r["thresholds"]
        label = f"dead={cfg['dead']}/trend={cfg['trend']}/strong={cfg['strong']}"
        zs = r["zones"]
        vals = []
        for zn in ["RANGING", "TRANSITION", "TRENDING", "ROARING"]:
            z = zs.get(zn)
            vals.append(f"{z['avg_abs_next_4h_move_pct']:.3f}%" if z and z['avg_abs_next_4h_move_pct'] else "N/A     ")
        print(f"  {label:<28} {vals[0]:<10} {vals[1]:<12} {vals[2]:<10} {vals[3]:<10}")

    print(f"\nAmostras por config: {results[0]['sample_count']}")
    print(f"ADX atual: {results[0]['current_snapshot']['m_adx']} ({results[0]['current_snapshot']['zone']})")
    print()


if __name__ == "__main__":
    main()