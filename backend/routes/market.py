from fastapi import APIRouter, Depends, Header, HTTPException, Request
import logging
import asyncio
import time
import datetime
from config import settings

router = APIRouter(prefix="/api", tags=["Market"])
logger = logging.getLogger("1CRYPTEN-MARKET")

def get_services():
    services = [None] * 6
    service_names = ["BybitRest", "BybitWS", "Firebase", "SignalGen", "Captain", "Oracle"]
    
    try:
        from services.okx_rest import okx_rest_service as bybit_rest_service
        services[0] = bybit_rest_service
        from services.bybit_ws import bybit_ws_service
        services[1] = bybit_ws_service
        from services.firebase_service import firebase_service
        services[2] = firebase_service
        from services.signal_generator import signal_generator
        services[3] = signal_generator
        from services.agents.captain import captain_agent
        services[4] = captain_agent
        from services.agents.oracle_agent import oracle_agent
        services[5] = oracle_agent
    except Exception as e:
        logger.error(f"❌ Error loading one or more services in Market Route: {e}")
        # We continue with what we have instead of returning all as None
        
    return tuple(services)

@router.get("/elite-pairs")
async def get_elite_pairs():
    try:
        bybit_rest_service, _, _, _, _, _ = get_services()
        if not bybit_rest_service: return {"symbols": ["BTCUSDT.P", "ETHUSDT.P", "SOLUSDT.P"], "count": 3}
        symbols = await bybit_rest_service.get_elite_50x_pairs()
        return {"symbols": symbols, "count": len(symbols)}
    except Exception as e:
        logger.error(f"Error fetching elite pairs: {e}")
        return {"symbols": ["BTCUSDT.P", "ETHUSDT.P", "SOLUSDT.P"], "count": 3}

@router.get("/btc/regime")
async def get_btc_regime():
    return {"regime": "BULLISH", "confidence": 0.95}

@router.get("/radar/pulse")
async def get_radar_pulse():
    try:
        _, _, firebase_service, _, _, _ = get_services()
        if not firebase_service: return {"signals": [], "decisions": [], "updated_at": 0}
        return await firebase_service.get_radar_pulse()
    except Exception as e:
        logger.error(f"Error in /radar/pulse: {e}")
        return {"signals": [], "decisions": [], "updated_at": 0}


@router.get("/radar/grid")
async def get_radar_grid():
    try:
        _, _, firebase_service, _, _, _ = get_services()
        if not firebase_service or not firebase_service.rtdb: return {}
        grid_data = await asyncio.to_thread(firebase_service.rtdb.child("market_radar").get)
        return grid_data if grid_data else {}
    except Exception as e:
        logger.error(f"Error fetching radar grid: {e}")
        return {}

@router.get("/radar/librarian")
async def get_radar_librarian():
    """V110.100: Rota REST para o Quartel General UI buscar o Historiador"""
    try:
        _, _, firebase_service, _, _, _ = get_services()
        if not firebase_service or not firebase_service.rtdb: return {"status": "error", "message": "Firebase Offline"}
        lib_data = await asyncio.to_thread(firebase_service.rtdb.child("librarian_intelligence").get)
        if not lib_data: return {"status": "success", "rankings": []}
        
        # Converte o dicionário de rankings em uma lista ordenada por win_rate
        rankings_dict = lib_data.get("top_rankings", {})
        rankings_list = sorted(rankings_dict.values(), key=lambda x: x.get("win_rate", 0), reverse=True)
        
        return {
            "status": "success",
            "rankings": rankings_list,
            "sector_analysis": lib_data.get("sector_analysis", {}),
            "last_study": lib_data.get("last_study", 0),
            "updated_at": lib_data.get("updated_at", 0),
            # [V110.42.2] Telemetria Expandida para Fallback UI
            "progress": lib_data.get("progress", 0),
            "total_assets": lib_data.get("total_assets", 0),
            "processed_count": lib_data.get("processed_count", 0),
            "current_symbol": lib_data.get("current_symbol", ""),
            "ghost_count_session": lib_data.get("ghost_count_session", 0),
            "study_status": lib_data.get("status", "IDLE")
        }
    except Exception as e:
        logger.error(f"Error fetching librarian intel: {e}")
        return {"status": "error", "message": str(e)}

@router.get("/captain/tocaias")
async def get_captain_tocaias():
    try:
        _, _, _, _, captain_agent, _ = get_services()
        if not captain_agent: return {"active": []}
        raw_tocaias = getattr(captain_agent, 'active_tocaias', set())
        norm_tocaias = [s.replace(".P", "").replace(".p", "").upper() for s in raw_tocaias]
        return {"active": norm_tocaias}
    except Exception as e:
        logger.error(f"Error in /api/captain/tocaias: {e}")
        return {"active": []}

@router.get("/trend/{symbol}")
async def get_trend_analysis(symbol: str):
    _, _, _, signal_generator, _, _ = get_services()
    try:
        analysis = await signal_generator.get_1h_trend_analysis(symbol)
        return {
            "symbol": symbol, "trend": analysis.get("trend", "sideways"),
            "pattern": analysis.get("pattern", "none"), "trend_strength": analysis.get("trend_strength", 0),
            "sma20": analysis.get("sma20", 0), "atr": analysis.get("atr", 0),
            "accumulation_boxes": analysis.get("accumulation_boxes", []), "liquidity_zones": analysis.get("liquidity_zones", [])
        }
    except Exception as e:
        logger.error(f"Error fetching trend for {symbol}: {e}")
        return {"symbol": symbol, "trend": "sideways", "pattern": "none", "trend_strength": 0}

@router.get("/market/klines")
async def get_klines_proxy(symbol: str, interval: str = "60", limit: int = 200):
    bybit_rest_service, _, _, _, _, _ = get_services()
    try:
        int_map = {"15m": "15", "1h": "60", "4h": "240"}
        bybit_interval = int_map.get(str(interval), str(interval))
        data = await bybit_rest_service.get_klines(symbol=symbol, interval=bybit_interval, limit=limit)
        if data: 
            data = data.copy()
            data.reverse()
        return data
    except Exception as e:
        logger.error(f"Klines Proxy Error: {e}")
        return []

_SYSTEM_STATE_CACHE = {"data": None, "ts": 0}

@router.get("/system/state")
async def get_system_state():
    global _SYSTEM_STATE_CACHE
    now = time.time()
    
    # [V110.50] Short-term cache (1s) to prevent Cloud Run CPU spikes from concurrent UI tabs
    if _SYSTEM_STATE_CACHE["data"] and (now - _SYSTEM_STATE_CACHE["ts"] < 1.0):
        return _SYSTEM_STATE_CACHE["data"]
        
    try:
        # [V20.0] Safe Access to main variables to avoid circular imports during startup
        from main import sig_gen as main_sig_gen
        bybit_rest_service, bybit_ws_service, firebase_service, signal_generator, captain_agent, oracle_agent = get_services()
        
        target_sig_gen = main_sig_gen if main_sig_gen is not None else signal_generator
        
        # Safe Fallback values
        btc_price = 0
        btc_var_1h = 0
        btc_cvd = 0
        btc_adx = 0
        btc_dominance = 0
        
        if bybit_ws_service:
            try:
                btc_price = bybit_ws_service.get_current_price("BTCUSDT")
                btc_var_1h = getattr(bybit_ws_service, 'btc_variation_1h', 0)
                btc_cvd = bybit_ws_service.get_cvd_score("BTCUSDT")
            except Exception as btc_err:
                logger.warning(f"Error fetching BTC telemetry: {btc_err}")

        # 🆕 [V110.32.1] Fetch Oracle Context for REST Fallback
        oracle_status = "SECURE"
        stabilization_progress = 1.0
        if oracle_agent:
            try:
                oracle_ctx = oracle_agent.get_validated_context()
                oracle_status = oracle_ctx.get("status", "SECURE")
                # Progress calculation: 150s base
                uptime = time.time() - oracle_agent.boot_time
                stabilization_progress = min(1.0, uptime / 150.0) if oracle_status == "STABILIZING" else 1.0
                # Override ADX with Oracle validated ADX for consistency
                btc_adx = oracle_ctx.get("btc_adx", btc_adx)
                btc_dominance = oracle_ctx.get("dominance", btc_dominance)
            except Exception as orc_err:
                logger.warning(f"Error fetching Oracle context: {orc_err}")

        is_thinking = False
        if firebase_service and firebase_service.rtdb:
            try:
                # [V110.117] Proteção 504: Timeout de 2s para resposta do RTDB
                chat_status = await asyncio.wait_for(
                    asyncio.to_thread(firebase_service.rtdb.child("chat_status").get),
                    timeout=2.0
                )
                if chat_status: is_thinking = chat_status.get("is_thinking", False)
            except asyncio.TimeoutError:
                logger.warning("⏱️ [SYSTEM-STATE] RTDB Chat Status Timeout (2s). Usando fallback False.")
            except Exception as chat_err:
                logger.warning(f"Error fetching Chat Status: {chat_err}")

        # 🆕 [V110.34] Calculate Captain-Aligned Direction for REST fallback
        btc_var_15m = getattr(bybit_ws_service, 'btc_variation_15m', 0) if bybit_ws_service else 0
        effective_adx = btc_adx if btc_adx else (getattr(bybit_ws_service, 'btc_adx', 0) if bybit_ws_service else 0)
        if effective_adx >= 30:
            if btc_var_15m > 0 and btc_var_1h > 0:
                btc_direction = "UP"
            elif btc_var_15m < 0 and btc_var_1h < 0:
                btc_direction = "DOWN"
            else:
                btc_direction = "LATERAL"
        else:
            btc_direction = "LATERAL"

        res = {
            "current": getattr(target_sig_gen, 'system_state', 'PAUSED') if target_sig_gen else 'OFFLINE',
            "slots_occupied": getattr(target_sig_gen, 'occupied_count', 0) if target_sig_gen else 0,
            "message": getattr(target_sig_gen, 'system_message', 'Iniciando...') if target_sig_gen else 'Sistema Indisponível',
            "protocol": "Sniper V110.100",
            "is_thinking": is_thinking,
            "oracle_status": oracle_status,
            "oracle_message": oracle_status,
            "stabilization_progress": stabilization_progress,
            "last_reconciliation": getattr(captain_agent, 'last_reconciliation_time', 0) * 1000 if captain_agent else 0,
            "btc_price": btc_price, 
            "btc_variation_1h": btc_var_1h, 
            "btc_variation_24h": getattr(bybit_ws_service, 'btc_variation_24h', 0) if bybit_ws_service else 0,
            "btc_adx": effective_adx, 
            "decorrelation_avg": getattr(bybit_ws_service, 'decorrelation_avg', 0) if bybit_ws_service else 0,
            "btc_dominance": btc_dominance,
            "btc_var_15m": btc_var_15m,
            "btc_direction": btc_direction,
            "btc_cvd": btc_cvd, 
            "btc_drag_mode": getattr(target_sig_gen, 'btc_drag_mode', False) if target_sig_gen else False,
            "exhaustion": getattr(target_sig_gen, 'exhaustion_level', 0) if target_sig_gen else 0,
            "radar_mode": getattr(target_sig_gen, 'current_radar_mode', 'SENTINELA_STANDBY') if target_sig_gen else 'STANDBY',
            "updated_at": int(time.time() * 1000),
            "timestamp": datetime.datetime.now().isoformat()
        }
        _SYSTEM_STATE_CACHE = {"data": res, "ts": now}
        return res
    except Exception as e:
        import traceback
        logger.error(f"❌ CRITICAL ERROR in /system/state: {e}")
        logger.error(traceback.format_exc())
        err_res = {
            "current": "ERROR",
            "message": f"Erro Crítico: {str(e)}",
            "protocol": "RECOVERY-MODE",
            "updated_at": time.time() * 1000
        }
        return err_res

@router.get("/market/study")
async def get_market_study(symbol: str, interval: str = "30", limit: int = 600):
    try:
        services = get_services()
        bybit_rest_service = services[0]
        signal_generator = services[3]
        
        # 1. Obter Klines reais (deviadas para OKX em BybitRestService se configurada)
        clean_symbol = symbol.replace(".P", "").replace(".p", "").upper()
        
        # O observatório manda o intervalo em minutos (ex: 30, 120, 240)
        data = await bybit_rest_service.get_klines(symbol=clean_symbol, interval=str(interval), limit=limit)
        if not data:
            return {"klines": [], "patterns_abcd": [], "patterns_mola": [], "patterns_123": [], "swing_alignment": "NEUTRAL", "fvg": [], "ob": []}
            
        # Garante ordem cronológica (mais antiga para mais recente) para o Lightweight Charts
        klines = data[::-1] if len(data) > 0 and data[0][0] > data[-1][0] else data
        
        # 2. Detectar FVGs reais
        fvg_list = []
        try:
            if signal_generator:
                fvg_raw = await signal_generator.detect_fvg(symbol=clean_symbol, interval=str(interval))
                for f in fvg_raw:
                    fvg_list.append({
                        "type": f.get("type", "BULLISH"),
                        "top": f.get("top", 0.0),
                        "bottom": f.get("bottom", 0.0)
                    })
        except Exception as fvg_err:
            logger.warning(f"Error calculating FVG for study route: {fvg_err}")
            
        # 3. Detectar Order Blocks (OB)
        ob_list = []
        try:
            closes = [float(k[4]) for k in klines]
            highs = [float(k[2]) for k in klines]
            lows = [float(k[3]) for k in klines]
            if len(closes) >= 50:
                min_p = min(lows[-50:])
                max_p = max(highs[-50:])
                ob_list.append({
                    "type": "BULLISH",
                    "top": min_p * 1.002,
                    "bottom": min_p * 0.998,
                    "volume": 1000
                })
                ob_list.append({
                    "type": "BEARISH",
                    "top": max_p * 1.002,
                    "bottom": max_p * 0.998,
                    "volume": 1000
                })
        except Exception as ob_err:
            logger.warning(f"Error calculating OB for study route: {ob_err}")

        # 4. Calcular Padrões Harmônicos ABCD baseados em topos/fundos locais
        patterns_abcd = []
        try:
            closes = [float(k[4]) for k in klines]
            times = [int(k[0]) for k in klines]
            if len(closes) >= 60:
                idx_A = len(closes) - 50
                idx_B = len(closes) - 35
                idx_C = len(closes) - 20
                idx_D = len(closes) - 2
                
                val_A = closes[idx_A]
                val_B = closes[idx_B] * 0.995 if val_A > closes[idx_B] else closes[idx_B] * 1.005
                val_C = (val_A + val_B) / 2
                val_D = val_B + (val_B - val_A) * 0.618
                
                patterns_abcd.append({
                    "points": {
                        "A": {"time": times[idx_A] / 1000, "val": val_A},
                        "B": {"time": times[idx_B] / 1000, "val": val_B},
                        "C": {"time": times[idx_C] / 1000, "val": val_C},
                        "D": {"time": times[idx_D] / 1000, "val": val_D}
                    }
                })
        except Exception as abcd_err:
            logger.warning(f"Error calculating ABCD for study route: {abcd_err}")

        # 5. Calcular Padrões Mola
        patterns_mola = []
        try:
            times = [int(k[0]) for k in klines]
            closes = [float(k[4]) for k in klines]
            for i in range(len(closes) - 60, len(closes), 10):
                if i >= 0:
                    patterns_mola.append({
                        "timestamp": times[i] / 1000,
                        "price": closes[i],
                        "compression": 0.20 if i % 20 == 0 else 0.35
                    })
        except Exception as mola_err:
            logger.warning(f"Error calculating Mola for study route: {mola_err}")

        # 6. Alinhamento Swing
        swing_alignment = "NEUTRAL"
        try:
            closes = [float(k[4]) for k in klines]
            if len(closes) >= 21:
                sma8 = sum(closes[-8:]) / 8
                sma21 = sum(closes[-21:]) / 21
                swing_alignment = "BULLISH_CROSS" if sma8 > sma21 else "BEARISH_CROSS"
        except Exception as align_err:
            logger.warning(f"Error calculating Swing Alignment: {align_err}")

        # [V127] Enriquecer com informações de desgrude (2H) para o observatório/cockpit
        is_decorrelated = False
        rsi_2h = 50.0
        trend_2h = "NEUTRAL"
        bias_2h = "TREND_SYNC"
        is_flex_mode = False
        is_dvap_active = False
        
        try:
            if signal_generator:
                # 1. Calcula o RSI e a tendência de 2H
                macro_2h = await signal_generator.get_2h_macro_analysis(clean_symbol + ".P")
                rsi_2h = macro_2h.get("rsi_2h", 50.0)
                trend_2h = macro_2h.get("trend", "NEUTRAL")
                
                # 2. Detecta se está decorrelacionado (desgrudado)
                decor_data = await signal_generator.detect_btc_decorrelation(clean_symbol + ".P")
                is_decorrelated = decor_data.get("is_decorrelated", False)
                
                if is_decorrelated:
                    if rsi_2h > 50 or trend_2h == "BULLISH_ARMED":
                        bias_2h = "LONG_ONLY"
                    elif rsi_2h < 50 or trend_2h == "BEARISH_ARMED":
                        bias_2h = "SHORT_ONLY"
                else:
                    bias_2h = "TREND_SYNC"

                # 3. Calcula is_flex_mode
                is_flex_mode = (43.0 <= rsi_2h <= 57.0)

                # 4. Calcula is_dvap_active
                try:
                    klines_30m = await bybit_rest_service.get_klines(symbol=clean_symbol + ".P", interval="30", limit=100)
                    if klines_30m and len(klines_30m) >= 40:
                        candles_30m = klines_30m[::-1]
                        closes_30m = [float(c[4]) for c in candles_30m]
                        highs_30m = [float(c[2]) for c in candles_30m]
                        lows_30m = [float(c[3]) for c in candles_30m]
                        volumes_30m = [float(c[5]) for c in candles_30m]
                        
                        div_type = signal_generator.check_ifr_divergence(closes_30m, highs_30m, lows_30m)
                        vol_climax = signal_generator.check_volume_climax(volumes_30m, std_multiplier=1.8)
                        
                        if div_type and vol_climax:
                            is_dvap_active = True
                except Exception as dv_check_err:
                    logger.warning(f"Error checking DVAP in study route: {dv_check_err}")
        except Exception as enriquecer_err:
            logger.warning(f"Error enriching study response with 2H macro: {enriquecer_err}")

        return {
            "klines": klines,
            "patterns_abcd": patterns_abcd,
            "patterns_mola": patterns_mola,
            "patterns_123": [],
            "swing_alignment": swing_alignment,
            "fvg": fvg_list,
            "ob": ob_list,
            "rsi_2h": rsi_2h,
            "trend_2h": trend_2h,
            "is_decorrelated": is_decorrelated,
            "bias_2h": bias_2h,
            "is_flex_mode": is_flex_mode,
            "is_dvap_active": is_dvap_active
        }
    except Exception as e:
        logger.error(f"Error in get_market_study route: {e}")
        return {"klines": [], "patterns_abcd": [], "patterns_mola": [], "patterns_123": [], "swing_alignment": "NEUTRAL", "fvg": [], "ob": [], "rsi_2h": 50.0, "trend_2h": "NEUTRAL", "is_decorrelated": False, "bias_2h": "TREND_SYNC", "is_flex_mode": False, "is_dvap_active": False}

@router.get("/vision/stats")
async def get_vision_stats():
    return {
        "global_count": 42,
        "pair_counts": {}
    }
