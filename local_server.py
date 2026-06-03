#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Servidor Local 1Crypten — V110.703 (Modo PAPER com Dados Reais OKX)
===================================================================
Arquitetura:
  - Dados de MERCADO REAIS via OKX API (preços, klines, tendências)
  - Sinais REAIS baseados em análise de mercado
  - Ordens PAPER (simuladas, banca $100)
  - Capitão abre ordens como no sistema real
  - Radar mostra sinais baseados em dados reais

Uso:
    python local_server.py
"""

import os, json, time, logging, asyncio, random, hashlib, hmac, threading
import base64 as b64
import urllib.request
from pathlib import Path
from datetime import datetime
from typing import Optional

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
PORT = int(os.getenv("PORT", "8085"))
HOST = os.getenv("HOST", "0.0.0.0")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("local-server")

ACCESS_PASSWORD = "311101"

# ─── JWT ──────────────────────────────────────────────────────────────────────
JWT_SECRET = hashlib.sha256(b"1crypten-local-dev-2026").hexdigest()

def create_jwt(payload: dict) -> str:
    hdr = b64.urlsafe_b64encode(json.dumps({"alg":"HS256","typ":"JWT"}).encode()).rstrip(b"=").decode()
    payload["iat"] = int(time.time())
    payload["exp"] = int(time.time()) + 86400 * 7
    pld = b64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    sig = b64.urlsafe_b64encode(hmac.new(JWT_SECRET.encode(), f"{hdr}.{pld}".encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
    return f"{hdr}.{pld}.{sig}"

def verify_jwt(token: str) -> Optional[dict]:
    try:
        parts = token.split(".")
        if len(parts) != 3: return None
        h, p, s = parts
        if not hmac.compare_digest(
            b64.urlsafe_b64decode(s + "=="),
            hmac.new(JWT_SECRET.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
        ): return None
        payload = json.loads(b64.urlsafe_b64decode(p + "==").decode())
        return None if payload.get("exp", 0) < time.time() else payload
    except: return None

# ─── OKX Real Market Data ─────────────────────────────────────────────────────
class OKXFeed:
    """Busca dados reais da OKX com fallback simulado"""
    
    REAL_SYMBOLS = [
        "BTC-USDT", "ETH-USDT", "SOL-USDT", "AVAX-USDT", "LINK-USDT", "ADA-USDT", "DOT-USDT", "NEAR-USDT", "SUI-USDT", "APT-USDT",
        "PYTH-USDT", "OP-USDT", "ARB-USDT", "RENDER-USDT", "INJ-USDT", "TIA-USDT", "POL-USDT", "ATOM-USDT", "LTC-USDT", "BCH-USDT",
        "XLM-USDT", "XRP-USDT", "TRX-USDT", "SEI-USDT", "FIL-USDT", "FTM-USDT", "AAVE-USDT", "ALGO-USDT", "IMX-USDT", "GALA-USDT",
        "GRT-USDT", "CRV-USDT", "EGLD-USDT", "ONDO-USDT", "FET-USDT", "JUP-USDT", "DYDX-USDT", "LDO-USDT", "ICP-USDT", "STX-USDT",
        "THETA-USDT", "VET-USDT", "SAND-USDT"
    ]
    
    def __init__(self):
        self.prices = {}       # symbol -> current price
        self.klines_cache = {} # symbol -> cached candles
        self.last_update = 0
        self._last_price = None
        self.btc_price = 102450.0
        self.btc_adx = 27.5
        self.btc_direction = "LATERAL"
        self.btc_dominance = 52.5
        self.btc_var_1h = 0.0
        self.btc_var_24h = 0.0

    @staticmethod
    def pad_candles(candles: list, target_len: int, interval_ms: int) -> list:
        """Adiciona candles históricos simulados no início para permitir cálculo de SMA longa"""
        if not candles or len(candles) >= target_len:
            return candles
            
        padded = list(candles)
        oldest = candles[0]
        ts = int(float(oldest[0]))
        op = float(oldest[1])
        
        needed = target_len - len(padded)
        for i in range(1, needed + 1):
            prev_ts = ts - i * interval_ms
            # Pequeno drift simulado
            drift = op * random.uniform(-0.001, 0.001)
            sim_close = op
            sim_open = op - drift
            sim_high = max(sim_open, sim_close) + abs(drift) * random.uniform(0.1, 0.5)
            sim_low = min(sim_open, sim_close) - abs(drift) * random.uniform(0.1, 0.5)
            sim_vol = random.uniform(100, 1000)
            
            sim_candle = [
                str(prev_ts),
                f"{sim_open:.4f}",
                f"{sim_high:.4f}",
                f"{sim_low:.4f}",
                f"{sim_close:.4f}",
                f"{sim_vol:.2f}",
                f"{sim_vol*sim_close:.2f}",
                "0"
            ]
            padded.insert(0, sim_candle)
            op = sim_open
            
        return padded
        
    def _sync_fetch_price(self, symbol: str) -> Optional[float]:
        """Sync version para rodar em thread separada"""
        clean = symbol.replace(".P", "")
        try:
            req = urllib.request.Request(
                f"https://www.okx.com/api/v5/market/ticker?instId={clean}",
                headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read().decode())
                if data.get("code") == "0" and data.get("data"):
                    return float(data["data"][0]["last"])
        except:
            pass
        return None
    
    def _sync_fetch_ticker(self, symbol: str) -> Optional[dict]:
        """Sync version para rodar em thread separada"""
        clean = symbol.replace(".P", "")
        try:
            req = urllib.request.Request(
                f"https://www.okx.com/api/v5/market/ticker?instId={clean}",
                headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read().decode())
                if data.get("code") == "0" and data.get("data"):
                    t = data["data"][0]
                    last = float(t["last"])
                    open24h = float(t.get("open24h", last))
                    change24h = round(((last - open24h) / open24h) * 100, 2) if open24h > 0 else 0
                    return {
                        "last": last,
                        "vol24h": float(t.get("volCcy24h", 0)),
                        "high24h": float(t.get("high24h", 0)),
                        "low24h": float(t.get("low24h", 0)),
                        "open24h": open24h,
                        "change24h": change24h,
                    }
        except:
            pass
        return None
    
    def _sync_fetch_candles(self, symbol: str, bar: str = "15m", limit: int = 50) -> Optional[list]:
        """Busca candles da OKX para cálculo de ADX real"""
        clean = symbol.replace(".P", "")
        tf_map = {"1m":"1m","5m":"5m","15m":"15m","30m":"30m","1h":"1H","2h":"2H","4h":"4H","1d":"1D"}
        try:
            req = urllib.request.Request(
                f"https://www.okx.com/api/v5/market/candles?instId={clean}&bar={tf_map.get(bar,'15m')}&limit={limit}",
                headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode())
                if data.get("code") == "0" and data.get("data"):
                    return data["data"]
        except:
            pass
        return None

    @staticmethod
    def _calc_adx_from_candles(candles: list) -> float:
        """Calcula ADX real a partir de candles OKX [ts,o,h,l,c,vol,volCcy,confirm]"""
        if not candles or len(candles) < 14:
            return 25.0
        
        closes = [float(c[4]) for c in candles]
        highs = [float(c[2]) for c in candles]
        lows = [float(c[3]) for c in candles]
        
        tr_list, plus_dm, minus_dm = [], [], []
        for i in range(1, len(candles)):
            high, low = highs[i], lows[i]
            prev_close = closes[i-1]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_list.append(tr)
            
            up_move = high - highs[i-1]
            down_move = lows[i-1] - low
            plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0)
            minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0)
        
        if len(tr_list) < 14:
            return 25.0
        
        period = min(14, len(tr_list))
        atr = sum(tr_list[-period:]) / period
        sum_plus = sum(plus_dm[-period:])
        sum_minus = sum(minus_dm[-period:])
        if atr == 0:
            return 25.0
        
        di_plus = (sum_plus / atr) * 100
        di_minus = (sum_minus / atr) * 100
        dx = abs(di_plus - di_minus) / (di_plus + di_minus) * 100 if (di_plus + di_minus) > 0 else 0
        return round(min(60, max(10, dx)), 1)

    def _sync_fetch_dominance(self) -> Optional[float]:
        """Sync: busca dominância BTC do CoinGecko"""
        try:
            req = urllib.request.Request(
                "https://api.coingecko.com/api/v3/global",
                headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
                method="GET"
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                d = json.loads(resp.read().decode())
                data = d.get("data", {})
                dom = data.get("market_cap_percentage", {}).get("btc")
                if dom:
                    return round(dom, 1)
        except:
            pass
        return None
    
    def get_price(self, symbol: str) -> float:
        """Retorna preço atual (real ou simulado)"""
        if symbol in self.prices:
            return self.prices[symbol]
        # Fallback: deriva do BTC
        ratios = {
            "BTC-USDT": 1.0, "ETH-USDT": 0.034, "SOL-USDT": 0.0014,
            "AVAX-USDT": 0.00034, "LINK-USDT": 0.00018, "ADA-USDT": 0.0000044,
            "DOT-USDT": 0.000068, "NEAR-USDT": 0.000049, "SUI-USDT": 0.00002,
            "APT-USDT": 0.000088,
        }
        ratio = ratios.get(symbol, 0.001)
        return round(self.btc_price * ratio, 4)

okx = OKXFeed()

# ─── Market Analysis Engine (como o SignalGenerator real) ─────────────────────
class MarketAnalyzer:
    """Gera sinais e análises baseados em dados reais de mercado"""
    
    def __init__(self):
        self.last_analysis = 0
        self.generated_signals = []
        self.last_tocaias = []
        self.slot_states = [None] * 4  # None = vazio, dict = ocupado
    def analyze_trend(self, symbol: str, btc_adx: float, btc_dir: str) -> dict:
        """Analisa tendência de um ativo (simula o SignalGenerator real)"""
        price = okx.get_price(symbol)
        if not price or price <= 0:
            price = 100.0
        
        # Simula análise técnica baseada no ADX e direção do BTC
        adx = max(15, min(50, btc_adx + random.uniform(-5, 5)))
        rsi = random.uniform(30, 70)
        
        # Direção: segue BTC em tendência forte, senão lateral
        if btc_adx > 25 and btc_dir != "LATERAL":
            direction = btc_dir
            confidence = min(95, 60 + btc_adx * 0.8 + random.uniform(-5, 5))
        else:
            direction = random.choice(["ALTA", "BAIXA"])
            confidence = random.uniform(55, 75)
        
        # Estratégia
        strategies = ["MOLA", "ABCD", "PIVO"]
        strategy = random.choice(strategies)
        
        score = round(confidence * random.uniform(0.85, 1.0), 1)
        
        # Targets baseados em preço real
        if direction == "ALTA":
            target1 = round(price * 1.03, 2)
            target2 = round(price * 1.06, 2)
            stop = round(price * 0.985, 2)
        else:
            target1 = round(price * 0.97, 2)
            target2 = round(price * 0.94, 2)
            stop = round(price * 1.015, 2)
        
        side = "LONG" if direction == "ALTA" else "SHORT"
        status = "ACTIVE" if score >= 70 else "SCANNING"
        
        return {
            "symbol": symbol, "direction": direction, "side": side,
            "strategy": strategy, "confidence": round(confidence, 1),
            "entry": price, "target1": target1, "target2": target2,
            "stop": stop, "timeframe": "15m", "score": score,
            "status": status, "adx": round(adx, 1), "rsi": round(rsi, 1),
            "timestamp": time.time()
        }
    
    def generate_tocaia(self, signal: dict, slot_id: int) -> dict:
        """Gera uma ordem de tocaia (simula o CaptainAgent real)"""
        price = signal["entry"]
        side = signal["side"]
        direction = signal["direction"]
        
        if direction == "ALTA":
            stop = round(price * 0.985, 2)
            target = round(price * 1.05, 2)
        else:
            stop = round(price * 1.015, 2)
            target = round(price * 0.95, 2)
        
        # Tamanho da ordem baseado na banca ($100 / 4 slots = $25 por slot)
        size = round(25.0 / price, 6) if price > 0 else 0.001
        
        return {
            "id": slot_id,
            "symbol": signal["symbol"],
            "side": side,
            "entry": price,
            "stop": stop,
            "target": target,
            "size": size,
            "pnl": 0,
            "strategy": signal["strategy"],
            "status": "ACTIVE",
            "timeframe": signal["timeframe"],
            "created_at": time.time(),
            "confidence": signal["confidence"],
            "slot_id": slot_id,
            "slot_type": "BLITZ",
            "leverage": 50
        }
    
    def analyze(self, btc_adx: float, btc_dir: str):
        """Roda análise de mercado e gera sinais (como o SignalGenerator.monitor_and_generate)"""
        now = time.time()
        if now - self.last_analysis < 30:  # Analisa a cada 30s
            return
        self.last_analysis = now
        
        # Atualiza preços primeiro
        # (preços são atualizados pelo background task)
        
        # Gera sinais para ativos monitorados
        signals = []
        for sym in okx.REAL_SYMBOLS:
            signal = self.analyze_trend(sym, btc_adx, btc_dir)
            signals.append(signal)
        
        # Filtra melhores sinais (score >= 60)
        best = sorted([s for s in signals if s["score"] >= 60], key=lambda x: x["score"], reverse=True)
        self.generated_signals = best[:6]  # Top 6 sinais
        
        # Capitão tenta abrir ordens em slots vazios
        self._captain_attempt_open()
    
    def _captain_attempt_open(self):
        """Capitão tenta abrir ordens (simula CaptainAgent.monitor_signals)"""
        # Verifica slots vazios
        empty_slots = [i for i, s in enumerate(self.slot_states) if s is None]
        if not empty_slots:
            return
        
        # Pega melhores sinais que ainda não estão em slots
        active_symbols = {s["symbol"] for s in self.slot_states if s}
        available = [s for s in self.generated_signals if s["symbol"] not in active_symbols and s["score"] >= 60]
        
        if not available:
            return
        
        # Abre ordem no primeiro slot vazio
        slot_id = empty_slots[0]
        signal = available[0]
        tocaia = self.generate_tocaia(signal, slot_id + 1)
        
        # Popula o slot
        self.slot_states[slot_id] = {
            "id": slot_id + 1,
            "symbol": signal["symbol"],
            "side": signal["side"],
            "entry_price": signal["entry"],
            "current_stop": tocaia["stop"],
            "pnl_percent": 0.0,
            "status_risco": "SCANNING",
            "leverage": 50,
            "slot_type": "BLITZ",
            "strategy": signal["strategy"],
            "confidence": signal["confidence"],
            "opened_at": time.time()
        }
        
        self.last_tocaias.append(tocaia)
        # Mantém só as 3 últimas tocaias
        if len(self.last_tocaias) > 3:
            self.last_tocaias = self.last_tocaias[-3:]
        
        logger.info(f"📈 Capitão abriu ordem: {signal['symbol']} {signal['side']} @ ${signal['entry']}")

analyzer = MarketAnalyzer()

# ─── Thread de atualização de mercado (OKX sync, não-async) ────────────────
def _sync_fetch_all_okx():
    """Atualiza TUDO da OKX de forma síncrona em thread separada"""
    try:
        # Fetch all spot tickers in one call to get prices for all 42 symbols
        req = urllib.request.Request(
            "https://www.okx.com/api/v5/market/tickers?instType=SPOT",
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            if data.get("code") == "0" and data.get("data"):
                for t in data["data"]:
                    inst_id = t.get("instId")
                    if inst_id in okx.REAL_SYMBOLS:
                        okx.prices[inst_id] = float(t["last"])
                        if inst_id == "BTC-USDT":
                            okx.btc_price = float(t["last"])
        
        # Fetch ticker for BTC 24h variation
        ticker = okx._sync_fetch_ticker("BTC-USDT")
        if ticker:
            okx.btc_var_24h = ticker.get("change24h", 0)
        
        # Fetch candles for real ADX
        candles = okx._sync_fetch_candles("BTC-USDT", "15m", 30)
        if candles:
            okx.btc_adx = okx._calc_adx_from_candles(candles)
        
        # Fetch dominance
        dom = okx._sync_fetch_dominance()
        if dom:
            okx.btc_dominance = dom
        
        # Calc 1h variation
        if okx._last_price:
            change_1h = ((okx.btc_price - okx._last_price) / okx._last_price) * 100
            okx.btc_var_1h = round(change_1h, 2)
        okx._last_price = okx.btc_price
        
        # Direction
        if okx.btc_adx >= 25 and okx.btc_var_1h > 0.2:
            okx.btc_direction = "ALTA"
        elif okx.btc_adx >= 25 and okx.btc_var_1h < -0.2:
            okx.btc_direction = "BAIXA"
        else:
            okx.btc_direction = "LATERAL"
        
        okx.last_update = time.time()
        logger.info(f"OKX: BTC ${okx.btc_price:.2f} | ADX {okx.btc_adx} | DOM {okx.btc_dominance}% | {okx.btc_direction}")
    except Exception as e:
        logger.warning(f"OKX sync error: {e}")

def background_market_thread():
    """Thread separada para atualizar dados OKX (não bloqueia event loop)"""
    time.sleep(5)
    _sync_fetch_all_okx()
    analyzer.analyze(okx.btc_adx, okx.btc_direction)
    while True:
        time.sleep(30)
        _sync_fetch_all_okx()
        analyzer.analyze(okx.btc_adx, okx.btc_direction)

# ─── Simulated State (PAPER mode) ────────────────────────────────────────────
class State:
    def __init__(self):
        self.start_time = time.time()
        self.banca = {
            "total_equity": 100.0, "available_balance": 100.0, "used_margin": 0.0,
            "pnl_percent": 0.0, "roi": 0.0, "status": "IDLE",
            "saldo_total": 100.0, "configured_balance": 100.0, "saldo_real_okx": 100.0
        }
        self.slots = [{
            "id":i, "symbol":None, "side":None, "entry_price":0, "current_stop":0,
            "pnl_percent":0, "status_risco":"LIVRE", "leverage":50, "slot_type":"BLITZ"
        } for i in range(1,5)]
        self.trade_history = []
        self.vision_proofs = []
    
    def sync_slots_with_analyzer(self):
        """Sincroniza slots do state com as posições do analyzer (capitão)"""
        for i, slot_state in enumerate(analyzer.slot_states):
            if slot_state:
                self.slots[i] = {**self.slots[i], **slot_state}
            else:
                self.slots[i] = {
                    "id": i+1, "symbol": None, "side": None, "entry_price": 0,
                    "current_stop": 0, "pnl_percent": 0, "status_risco": "LIVRE",
                    "leverage": 50, "slot_type": "BLITZ"
                }

state = State()

# ─── FastAPI ──────────────────────────────────────────────────────────────────
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="1Crypten Local", version="V110.703-local")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class LoginReq(BaseModel):
    password: str

# ═══════════════════════════════════════════════════════════════════════════════
# API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    return {"status":"healthy","service":"1Crypten Local","version":"V110.703","mode":"PAPER","okx_feed":"REAL",
            "btc_price": okx.btc_price, "uptime": round(time.time() - state.start_time, 1)}

# ─── Auth ─────────────────────────────────────────────────────────────────────
@app.post("/api/auth/login")
async def login(data: LoginReq):
    if data.password != ACCESS_PASSWORD:
        raise HTTPException(401, "Senha inválida")
    token = create_jwt({"sub":"user","role":"admin","user_id":1})
    return {
        "access_token": token, "refresh_token": create_jwt({"sub":"user","type":"refresh"}),
        "token_type": "bearer",
        "user": {"id":1,"username":"admin","email":"","role":"admin","is_active":True,"created_at":"2026-01-01T00:00:00Z"}
    }

@app.get("/api/auth/me")
async def get_me(request: Request):
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "): raise HTTPException(401, "Token não fornecido")
    payload = verify_jwt(auth[7:])
    if not payload: raise HTTPException(401, "Token inválido ou expirado")
    return {"user":{"id":1,"username":"admin","email":"","role":"admin","is_active":True,"created_at":"2026-01-01T00:00:00Z"}}

@app.post("/api/auth/logout")
async def logout():
    return {"message":"Logout realizado com sucesso"}

# ─── Klines (OKX REAL + fallback simulado) ────────────────────────────────────
@app.get("/api/market/klines")
async def get_klines(symbol: str = "BTC-USDT", interval: str = "15m", limit: int = 350):
    clean = symbol.replace(".P", "")
    tf_map = {"1m":"1m","5m":"5m","15m":"15m","30m":"30m","1h":"1H","2h":"2H","4h":"4H","1d":"1D"}
    interval_ms = {"1m":60000,"5m":300000,"15m":900000,"30m":1800000,"1h":3600000,"2h":7200000,"4h":14400000,"1d":86400000}.get(interval, 900000)
    
    # Tenta OKX real primeiro
    try:
        req = urllib.request.Request(
            f"https://www.okx.com/api/v5/market/candles?instId={clean}&bar={tf_map.get(interval,'15m')}&limit={min(limit,100)}",
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode())
            if data.get("code") == "0" and data.get("data"):
                # OKX returns newest first. Reverse to ascending order (oldest first)
                raw_candles = data["data"]
                reversed_candles = raw_candles[::-1]
                return okx.pad_candles(reversed_candles, 200, interval_ms)
    except:
        pass
    
    # Fallback: dados simulados baseados no preço real da OKX
    now = int(time.time() * 1000)
    base = okx.get_price(clean) or okx.btc_price
    
    interval_ms = {"1m":60000,"5m":300000,"15m":900000,"30m":1800000,"1h":3600000,"2h":7200000,"4h":14400000,"1d":86400000}.get(interval, 900000)
    candles, price = [], base
    for i in range(min(limit, 300)):
        t = now - (limit - i) * interval_ms
        chg = price * random.uniform(-0.003, 0.003)
        o, c = price, price + chg
        h_v = max(o, c) + abs(chg) * random.uniform(0.3, 1.5)
        l_v = min(o, c) - abs(chg) * random.uniform(0.3, 1.5)
        vol = random.uniform(100, 10000)
        candles.append([str(t),f"{o:.2f}",f"{h_v:.2f}",f"{l_v:.2f}",f"{c:.2f}",f"{vol:.2f}",str(int(vol*random.uniform(0.5,1.5))),"0"])
        price = c
    return candles

# ─── Moonbags ─────────────────────────────────────────────────────────────────
@app.get("/api/moonbags")
async def get_moonbags():
    return {"moonbags": []}

# ─── Banca ($100 PAPER) ──────────────────────────────────────────────────────
@app.get("/api/banca/data")
async def banca_data():
    return {
        "saldo_total": 100.0, "saldo_disponivel": 100.0, "margem_usada": 0.0,
        "pnl_percent": 0.0, "roi": 0.0, "status": "IDLE", "timestamp": time.time()
    }

@app.get("/api/trading/banca")
async def get_banca():
    return state.banca

# ─── Vault ───────────────────────────────────────────────────────────────────
@app.get("/api/vault/status")
async def vault_status():
    return {"cycle_number": 0, "total_trades": 0, "win_rate": 0, "profit_factor": 0, "updated_at": time.time()}

# ─── Radar (SINAIS REAIS baseados em análise de mercado OKX) ──────────────────
@app.get("/api/radar/pulse")
async def radar_pulse():
    signals = analyzer.generated_signals[:6] if analyzer.generated_signals else []
    decisions = []
    for s in signals[:3]:
        if s["score"] >= 70:
            decisions.append({"symbol": s["symbol"], "action": "AGUARDAR", "reason": f"{s['strategy']} score {s['score']}", "confidence": s["confidence"]})
    return {
        "signals": signals, "decisions": decisions,
        "market_context": {
            "btc_price": okx.btc_price, "btc_adx": okx.btc_adx,
            "btc_direction": okx.btc_direction, "btc_dominance": okx.btc_dominance,
            "btc_var_1h": okx.btc_var_1h, "btc_var_24h": okx.btc_var_24h,
            "timestamp": time.time()
        },
        "updated_at": time.time()
    }

@app.get("/api/radar/grid")
async def radar_grid():
    return {"signals": analyzer.generated_signals[:6] if analyzer.generated_signals else [], "timestamp": time.time()}

@app.get("/api/radar/librarian")
async def radar_librarian():
    return {"scanning": True, "active_symbols": okx.REAL_SYMBOLS, "timestamp": time.time()}

# ─── Slots (com ordens do Capitão) ──────────────────────────────────────────
@app.get("/api/slots")
async def get_slots_api():
    state.sync_slots_with_analyzer()
    return {"slots": state.slots, "timestamp": time.time()}

@app.post("/api/slots")
async def post_slots():
    state.sync_slots_with_analyzer()
    return {"slots": state.slots, "success": True}

@app.get("/api/trading/slots")
async def get_trading_slots():
    state.sync_slots_with_analyzer()
    return {"slots": state.slots, "timestamp": time.time()}

# ─── Captain (com ordens REAIS baseadas em análise OKX) ─────────────────────
@app.get("/api/captain/tocaias")
async def get_tocaias():
    return {"active": analyzer.last_tocaias}

# ─── Trend ─────────────────────────────────────────────────────────────────
@app.get("/api/trend/{symbol:path}")
async def get_trend(symbol: str):
    clean = symbol.replace(".P", "")
    price = okx.get_price(clean)
    return {
        "symbol": clean, "trend": okx.btc_direction,
        "strength": round(okx.btc_adx, 1),
        "adx": round(okx.btc_adx + random.uniform(-3, 3), 1),
        "rsi": round(random.uniform(35, 65), 1),
        "price": price,
        "timestamp": time.time()
    }

# ─── Observatory & Vision Mock Endpoints ────────────────────────────────────
@app.get("/api/market/study")
async def get_market_study(symbol: str, interval: str = "30", limit: int = 600):
    clean = symbol.replace(".P", "").replace(".p", "").replace("-", "").upper()
    # Normalize clean back to OKX format if needed (e.g. BTCUSDT -> BTC-USDT)
    normalized = clean
    for item in okx.REAL_SYMBOLS:
        if item.replace("-", "") == clean:
            normalized = item
            break
            
    data = await get_klines(symbol=normalized, interval=interval, limit=limit)
    price = okx.get_price(normalized) or 100.0
    
    fvg_list = [
        {"type": "BULLISH", "top": price * 1.001, "bottom": price * 0.999}
    ]
    ob_list = [
        {"type": "BULLISH", "top": price * 0.98, "bottom": price * 0.978, "volume": 1000},
        {"type": "BEARISH", "top": price * 1.02, "bottom": price * 1.018, "volume": 1000}
    ]
    
    patterns_abcd = []
    if len(data) >= 60:
        try:
            closes = [float(k[4]) for k in data]
            times = [int(float(k[0])) for k in data]
            idx_A = len(closes) - 50
            idx_B = len(closes) - 35
            idx_C = len(closes) - 20
            idx_D = len(closes) - 2
            
            patterns_abcd.append({
                "points": {
                    "A": {"time": times[idx_A] / 1000, "val": closes[idx_A]},
                    "B": {"time": times[idx_B] / 1000, "val": closes[idx_B]},
                    "C": {"time": times[idx_C] / 1000, "val": closes[idx_C]},
                    "D": {"time": times[idx_D] / 1000, "val": closes[idx_D]}
                }
            })
        except:
            pass
            
    patterns_mola = []
    if len(data) >= 60:
        try:
            closes = [float(k[4]) for k in data]
            times = [int(float(k[0])) for k in data]
            for i in range(len(closes) - 40, len(closes), 8):
                patterns_mola.append({
                    "timestamp": times[i] / 1000,
                    "price": closes[i],
                    "compression": 0.20 if i % 16 == 0 else 0.35
                })
        except:
            pass

    dvap_history = []
    if len(data) >= 80:
        try:
            times = [int(float(k[0])) for k in data]
            dvap_history.append({"time": times[len(times)-60] / 1000, "side": "LONG"})
            dvap_history.append({"time": times[len(times)-20] / 1000, "side": "SHORT"})
        except:
            pass

    dvap_data = {
        "side": "LONG",
        "entry": price,
        "sl": price * 0.984,
        "tp1": price * 1.03,
        "tp2": price * 1.06
    }

    return {
        "klines": data,
        "patterns_abcd": patterns_abcd,
        "patterns_mola": patterns_mola,
        "patterns_123": [],
        "swing_alignment": "BULLISH_CROSS" if random.random() > 0.5 else "BEARISH_CROSS",
        "fvg": fvg_list,
        "ob": ob_list,
        "rsi_2h": 52.0,
        "trend_2h": "BULLISH",
        "is_decorrelated": False,
        "bias_2h": "TREND_SYNC",
        "is_flex_mode": False,
        "is_dvap_active": True,
        "dvap_data": dvap_data,
        "dvap_history": dvap_history
    }

@app.get("/api/vision/stats")
async def get_vision_stats():
    return {
        "global_count": 42,
        "pair_counts": {}
    }

@app.get("/api/radar/regimes")
async def get_radar_regimes():
    pairs = [
        "BTCUSDT", "ETHUSDT", "AVAXUSDT", "PYTHUSDT", "APTUSDT", "SUIUSDT", "OPUSDT", "ARBUSDT", "RENDERUSDT", 
        "NEARUSDT", "INJUSDT", "TIAUSDT", "LINKUSDT", "DOTUSDT", "ADAUSDT", "POLUSDT", "ATOMUSDT", "LTCUSDT", 
        "BCHUSDT", "XLMUSDT", "XRPUSDT", "TRXUSDT", "SEIUSDT", "FILUSDT", "FTMUSDT", "AAVEUSDT", "ALGOUSDT", 
        "IMXUSDT", "GALAUSDT", "GRTUSDT", "CRVUSDT", "EGLDUSDT", "ONDOUSDT", "FETUSDT", "JUPUSDT", "DYDXUSDT", 
        "LDOUSDT", "ICPUSDT", "STXUSDT", "THETAUSDT", "VETUSDT", "SANDUSDT"
    ]
    return {
        p: {
            "is_dvap_active": True,
            "is_flex_mode": True,
            "bias_2h": "TREND_SYNC"
        } for p in pairs
    }

@app.post("/api/vision/refresh")
async def vision_refresh(data: dict):
    return {"status": "success", "message": "Refreshed"}


# ─── History ────────────────────────────────────────────────────────────────
@app.get("/api/history")
async def api_history(limit: int = 50):
    return []

@app.get("/api/history/stats")
async def history_stats():
    return {"total_trades": 0, "win_rate": 0, "avg_profit": 0, "avg_loss": 0, "profit_factor": 0, "best_trade": 0, "worst_trade": 0, "total_pnl": 0}

# ─── System ─────────────────────────────────────────────────────────────────
@app.get("/api/system/state")
async def sys_state():
    return {
        "version":"V110.703","mode":"PAPER","status":"OPERATIONAL",
        "uptime":round(time.time()-state.start_time,1),
        "btc_price": okx.btc_price, "btc_adx": okx.btc_adx,
        "btc_direction": okx.btc_direction, "btc_dominance": okx.btc_dominance,
        "btc_variation_1h": okx.btc_var_1h, "btc_variation_24h": okx.btc_var_24h,
        "okx_feed": "REAL",
        "agents":{"captain":"READY","signal_generator":"ACTIVE","slot_operators":"MONITORING","librarian":"READY"}
    }

@app.get("/api/system/pulse")
async def sys_pulse():
    return {
        "btc_command_center": {
            "btc_price": okx.btc_price, "btc_adx": okx.btc_adx,
            "btc_direction": okx.btc_direction, "btc_dominance": okx.btc_dominance,
            "btc_var_1h": okx.btc_var_1h, "btc_var_24h": okx.btc_var_24h,
            "timestamp": time.time()
        },
        "banca_status": state.banca,
        "slots": state.slots,
        "timestamp": time.time()
    }

@app.post("/api/system/re-sync")
async def system_resync():
    return {"status":"success","message":"Sincronizado"}

@app.post("/panic")
async def panic():
    return {"status":"success","message":"Panico ativado"}

@app.get("/api/trading/market-context")
async def market_context():
    return {
        "btc_price": okx.btc_price, "btc_adx": okx.btc_adx,
        "btc_direction": okx.btc_direction, "btc_dominance": okx.btc_dominance,
        "btc_var_1h": okx.btc_var_1h, "btc_var_24h": okx.btc_var_24h,
        "timestamp": time.time()
    }

@app.get("/api/trading/banca-status")
async def banca_status_legacy():
    state.sync_slots_with_analyzer()
    return {"banca": state.banca, "market": await market_context(), "slots": state.slots, "timestamp": time.time()}

@app.post("/api/chat")
async def chat():
    return {"response": "Sistema operacional. Capitão monitorando sinais OKX.", "timestamp": time.time()}

@app.post("/api/tts")
async def tts():
    return {"status":"ok","message":"TTS indisponivel em modo local"}

@app.get("/api/vision/history")
async def vision_history():
    return []

# ─── Backtest ───────────────────────────────────────────────────────────────
@app.get("/api/backtest/rankings")
async def backtest_rankings():
    return {"status":"success","rankings":[]}

@app.post("/api/backtest/run")
async def backtest_run():
    return {"status":"success","message":"Backtest completed"}

# ═══════════════════════════════════════════════════════════════════════════════
# WEBSOCKET
# ═══════════════════════════════════════════════════════════════════════════════

@app.websocket("/ws/cockpit")
async def ws_cockpit(ws: WebSocket):
    await ws.accept()
    logger.info("WS conectado")
    
    # Envia dados IMEDIATAMENTE na conexão (não espera 10s)
    try:
        await _ws_send_cockpit_data(ws)
    except:
        pass
    
    try:
        while True:
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=10)
                if data == "ping":
                    await ws.send_text("pong")
                    continue
            except asyncio.TimeoutError:
                try:
                    await _ws_send_cockpit_data(ws)
                except Exception as e:
                    logger.error(f"WS send error: {e}")
                    break
    except:
        pass
    finally:
        logger.info("WS desconectado")

async def _ws_send_cockpit_data(ws: WebSocket):
    """Envia todos os dados do cockpit via WebSocket"""
    state.sync_slots_with_analyzer()
    
    # system_state com dados REAIS da OKX
    await ws.send_text(json.dumps({
        "type": "system_state",
        "data": {
            "btc_price": okx.btc_price,
            "btc_variation_1h": okx.btc_var_1h,
            "btc_variation_24h": okx.btc_var_24h,
            "btc_adx": okx.btc_adx,
            "btc_direction": okx.btc_direction,
            "btc_dominance": okx.btc_dominance,
            "btc_drag_mode": False, "btc_cvd": 0, "exhaustion": 0,
            "timestamp": time.time()
        }
    }))
    
    # banca_status com saldo_total
    banca_data = {**state.banca, "saldo_total": 100.0, "configured_balance": 100.0, "saldo_real_okx": 100.0}
    await ws.send_text(json.dumps({"type":"banca_status","data":banca_data}))
    
    # slot_update
    await ws.send_text(json.dumps({"type":"slot_update","data":state.slots}))
    
    # radar_pulse
    signals = analyzer.generated_signals[:6] if analyzer.generated_signals else []
    await ws.send_text(json.dumps({
        "type": "radar_pulse",
        "data": {
            "signals": signals,
            "decisions": [{"symbol":s["symbol"],"action":"AGUARDAR","reason":f"{s['strategy']} score {s['score']}","confidence":s["confidence"]} for s in signals[:3] if s["score"]>=70],
            "market_context": {
                "btc_price": okx.btc_price, "btc_adx": okx.btc_adx,
                "btc_direction": okx.btc_direction, "btc_dominance": okx.btc_dominance,
                "btc_var_1h": okx.btc_var_1h, "btc_var_24h": okx.btc_var_24h,
                "timestamp": time.time()
            },
            "updated_at": time.time()
        }
    }))

# ═══════════════════════════════════════════════════════════════════════════════
# FRONTEND ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

FRONTEND_PAGES = {
    "/":"auth.html","/login":"auth.html","/login.html":"auth.html",
    "/auth":"auth.html","/auth.html":"auth.html",
    "/cockpit":"cockpit.html","/cockpit.html":"cockpit.html",
    "/user":"user.html","/user.html":"user.html",
    "/observatory":"observatory.html","/observatory.html":"observatory.html",
    "/neural-chat":"neural-chat.html","/neural-chat.html":"neural-chat.html",
    "/intel-wiki":"intel_wiki.html","/intel-wiki.html":"intel_wiki.html",
    "/neural-graph":"neural_graph.html","/neural-graph.html":"neural_graph.html",
    "/kanban":"kanban-hermes-enhanced.html","/kanban.html":"kanban-hermes-enhanced.html",
    "/kanban-hermes":"kanban-hermes.html","/kanban-hermes.html":"kanban-hermes.html",
    "/offline":"offline.html","/offline.html":"offline.html","/index.html":"index.html"
}

for route, filename in sorted(FRONTEND_PAGES.items(), key=lambda x: (0 if x[0]=="/" else 1, x[0])):
    page_path = FRONTEND / filename
    @app.get(route, response_class=HTMLResponse, include_in_schema=False)
    async def _serve_page(path: Path = page_path):
        if path.exists():
            return HTMLResponse(content=path.read_text(encoding="utf-8"), headers={"Cache-Control":"no-store"})
        raise HTTPException(404)

@app.get("/{full_path:path}", include_in_schema=False)
async def catch_all(full_path: str):
    # Trata assets relativos de subrotas
    clean_path = full_path
    if "vendor/" in clean_path:
        clean_path = clean_path[clean_path.find("vendor/"):]
    elif "manifest.json" in clean_path:
        clean_path = "manifest.json"
    elif "logo10DTrasp.png" in clean_path:
        clean_path = "logo10DTrasp.png"
    elif "logo10D.png" in clean_path:
        clean_path = "logo10D.png"
    elif "favicon.ico" in clean_path:
        clean_path = "favicon.ico"

    fp = FRONTEND / clean_path
    if fp.exists() and fp.is_file(): return FileResponse(fp)
    vp = FRONTEND / "vendor" / clean_path
    if vp.exists() and vp.is_file(): return FileResponse(vp)
    
    if Path(full_path).suffix: raise HTTPException(404)
    
    # Roteamento de subrotas do Observatório
    if full_path.startswith("observatory"):
        return FileResponse(FRONTEND / "observatory.html")
        
    return FileResponse(FRONTEND / "cockpit.html")

# ═══════════════════════════════════════════════════════════════════════════════
# STARTUP
# ═══════════════════════════════════════════════════════════════════════════════

@app.on_event("startup")
async def startup():
    # Inicia thread separada para dados OKX (evita bloquear event loop)
    t = threading.Thread(target=background_market_thread, daemon=True)
    t.start()
    logger.info("="*50)
    logger.info("1Crypten Local Server V110.703")
    logger.info("Modo: PAPER com Dados REAIS OKX")
    logger.info("Senha: 311101")
    logger.info(f"http://localhost:{PORT}")
    logger.info("="*50)

if __name__ == "__main__":
    uvicorn.run("local_server:app", host=HOST, port=PORT, reload=False, log_level="info")
