import os
import logging
import asyncio
import time
import datetime
import math
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone, timedelta
from services.firebase_service import firebase_service
from services.okx_rest import okx_rest_service
from services.okx_ws_public import okx_ws_public_service
from services.vault_service import vault_service
from services.execution_protocol import execution_protocol
from services.agents.oracle_agent import oracle_agent
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SignalGenerator")

def normalize_symbol(symbol: str) -> str:
    """Normaliza símbolos removendo .P para comparação consistente."""
    if not symbol:
        return symbol
    norm = symbol.replace(".P", "").upper()
    # V6.0: Robust Mapping - Ensure it ends with USDT to match OKXRest
    if not (norm.endswith("USDT") or norm.endswith("USDC")):
        norm = f"{norm}USDT"
    return norm

class SignalGenerator:
    def __init__(self):
        self.is_running = False
        self.last_standby_log = 0
        self.radar_interval = 5.0 # V12.1: Optimized for responsiveness (from 10s)
        self.scan_interval = 5.0 # Reduced from 15s to 5s for V7.0 High-Precision Reactivity
        self.signal_queue = asyncio.PriorityQueue() # ⚡ V110.116: PriorityQueue for Elite Signals
        self._signal_counter = 0  # [V110.118] Tie-breaker para evitar TypeError ao comparar dicionários com mesmo score
        self._api_semaphore = asyncio.Semaphore(5) # V15.1.3: Limit concurrent Bybit REST calls
        self.exhaustion_level = 0.0
        self.last_context_update = 0  # V5.1.0: Context Sync
        self.last_radar_sync = 0      # V32.0: Periodic Dashboard Sync
        self._is_syncing_radar = False
        # V9.0 Multi-Timeframe Trend Cache
        self.trend_cache = {}  # {symbol: {'trend': 'bullish'|'bearish'|'sideways', 'updated_at': timestamp, 'pattern': str}}
        self.trend_cache_ttl = 120  # [V20.4] 2 minutes cache (was 5min) for faster reversal detection
        self.last_sent_signals = {} # {symbol: {'score': int, 'timestamp': float}}
        self.btc_drag_mode = False # V10.2: Initial State
        self.current_radar_mode = "SCAVENGER_RANGE"  # [V71.0] Dynamic Radar: ELITE_30_TREND | SCAVENGER_RANGE
        self._radar_ranging_streak = 0  # [V71.1] Hysteresis counter: consecutive RANGING readings
        self._radar_trending_streak = 0  # [V71.1] Hysteresis counter: consecutive TRENDING readings
        self._RADAR_HYSTERESIS_THRESHOLD = 3  # [V71.1] Need 3 consecutive readings to switch mode
        # V10.6 System Harmony: State Machine
        self.system_state = "PAUSED"  # SCANNING | MONITORING | PAUSED
        self.occupied_count = 0 
        self.system_message = "Iniciando..."
        self.last_state_update = 0
        # V12.0 Multi-Timeframe Caches
        self.trend_cache_4h = {}  # {symbol: {'trend': str, 'ema20': float, 'updated_at': timestamp}}
        self.trend_cache_4h_ttl = 600  # 10 minutes cache for 4H
        self.zones_cache_15m = {}  # {symbol: {'support': float, 'resistance': float, 'updated_at': timestamp}}
        self.zones_cache_15m_ttl = 180  # 3 minutes cache for 15m
        self.trend_cache_2h = {}  # V15.1: Shadow Sentinel 2H Cache
        self.trend_cache_2h_ttl = 600  # 10 minutes cache for 2H
        self.trend_cache_30m = {}  # [V40.2] Hybrid Tactical 30m Cache
        self.trend_cache_30m_ttl = 180  # 3 minutes cache for 30m (more responsive)
        # V42.9: Market Regime Cache for ADX visibility
        self.market_regime_cache = {}
        self.market_regime_cache_ttl = 120 # 2 minutes
        # V12.3 Valid entry patterns (bonus, not mandatory)
        self.valid_entry_patterns = [
            'pullback_bounce', 'pullback_rejection',
            'liquidity_sweep_long', 'liquidity_sweep_short',
            'bear_trap', 'bull_trap',
            'accumulation_box_exit_up', 'accumulation_box_exit_down'
        ]
        # V12.3 Diagnostic Counters (logged every 60s)
        self._diag_counters = {
            'scanned': 0, 'cvd_pass': 0, 'rsi_pass': 0, 'trend1h_pass': 0,
            'ema4h_pass': 0, 'zone_pass': 0, 'pattern_pass': 0, 'score_pass': 0, 'queued': 0
        }
        self._last_diag_log = 0
        self.recent_rejections = [] # V15.7.7: Keep track of recently rejected candidates for transparency
        
        self._last_diag_log = 0
        # V27.0 Phase 3: Multi-Timeframe Intelligence V2
        self.trend_cache_daily = {}  # {symbol: {'trend': str, 'ema50': float, 'sma200': float, 'updated_at': ts}}
        self.trend_cache_daily_ttl = 14400  # 4 hours cache for Daily
        self.market_regime_cache = {}  # {symbol: {'regime': str, 'adx': float, 'bb_width': float, 'updated_at': ts}}
        self.market_regime_cache_ttl = 1800  # 30 minutes cache
        self.btc_direction_cache = {'direction': 'NEUTRAL', 'strength': 0, 'aligned_with': 'Both', 'updated_at': 0}
        self.btc_direction_cache_ttl = 300  # 5 minutes cache
        self.asset_blocklist_permanent = settings.ASSET_BLOCKLIST
        # [V100.1] Persistent Blocklist
        base_dir = os.path.dirname(os.path.abspath(__file__))
        backend_dir = os.path.dirname(base_dir)
        self.BLOCKLIST_STORAGE_FILE = os.path.join(backend_dir, "auto_blocks.json")
        self.auto_blocked_assets = {} # Inicializa antes do load
        self._load_auto_blocks()
        # [V33.0] HOT ASSET DETECTOR — Ativos com wins consecutivos ganham bônus
        self.hot_assets = {}  # {symbol: {'wins': int, 'last_win_at': timestamp, 'bonus': 15}}
        self.hot_asset_ttl = 21600  # 6 hours
        self.radar_consensus_cache = {} # [V56.0] {symbol: {'data': dict, 'updated_at': float}}
        self.decorrelation_cache = {}   # [V57.0] {symbol: {'data': dict, 'updated_at': float}}
        # [V110.7] Anticipation Radar (Shadow Mode)
        self.anticipation_signals = []  # List of dicts: {'symbol', 'side', 'score', 'reason', 'timestamp'}
        self.last_anticipation_sync = 0
    
    def _classify_strategy(self, move_room_pct, pattern, trend_1h, trend_2h, abs_cvd, market_regime='TRANSITION'):
        """
        V21.0: Classificação inteligente de estratégia baseada em múltiplos fatores.
        [V28.0] Regime-Aware: Impede SWING se o regime for RANGING.
        SWING = tendência clara + padrão forte + volume alto
        SCALP = range-bound + padrão fraco + volume moderado
        """
        swing_score = 0
        
        # 1. Espaço de movimento (peso principal)
        if move_room_pct >= 3.0:
            swing_score += 3  # Muito espaço = definitivamente SWING
        elif move_room_pct >= 2.0:
            swing_score += 2
        elif move_room_pct >= 1.5:
            swing_score += 1  # Espaço moderado, depende de outros fatores
        
        # 2. Padrão de entrada (sweep_and_reclaim = swing, box_exit = swing)
        swing_patterns = ['sweep_and_reclaim_long', 'sweep_and_reclaim_short', 
                          'accumulation_box_exit_up', 'accumulation_box_exit_down',
                          'trend_continuation', 'momentum_breakout']
        if pattern in swing_patterns:
            swing_score += 2
        
        # 3. Alinhamento de tendência multi-timeframe
        if trend_1h == trend_2h and trend_1h != 'sideways':
            swing_score += 2  # Tendência alinhada em 1H e 2H = forte
        elif trend_2h != 'sideways':
            swing_score += 1
        
        # 4. Volume institucional (CVD alto = movimento forte)
        if abs_cvd > 100000:
            swing_score += 1
            
        # [V34.0] All-SWING Transition: Removed RANGING penalty to allow Pullback Hunter to decide.
        # Todos os sinais agora são filtrados e empurrados como SWING pelo radar.
        
        strategy = "SWING"
        logger.debug(f"🏷️ [V34.0] Strategy: {strategy} (score={swing_score}, room={move_room_pct:.1f}%, regime={market_regime})")
        return strategy

    # ═══════════════════════════════════════════════════════════════
    # ████ [V25.1] ENTRY CONFIRMATION PROTOCOL — 5m Triggers ████
    # ═══════════════════════════════════════════════════════════════
    
    async def get_5m_entry_triggers(self, symbol: str, side: str, zones_15m: dict) -> dict:
        """
        [V25.1] Analyzes 5m candles for precise entry triggers.
        Returns: {
            'has_trigger': bool,
            'trigger_type': str (ZONE_REACTION | BREAKOUT | FUNDING_SQUEEZE | None),
            'confidence': float (0-100),
            'funding_rate': float,
            'volume_confirmed': bool
        }
        """
        try:
            # Fetch 5m candles (last 20 = 100 minutes)
            klines = await okx_rest_service.get_klines(symbol=symbol, interval="5", limit=20)
            if not klines or len(klines) < 10:
                return {'has_trigger': False, 'trigger_type': None, 'confidence': 0, 'funding_rate': 0, 'volume_confirmed': False}
            
            # Bybit returns newest first — reverse for chronological order
            candles = klines[::-1]
            closes = [float(c[4]) for c in candles]
            highs = [float(c[2]) for c in candles]
            lows = [float(c[3]) for c in candles]
            # Mark price klines may not have volume (index 5), handle gracefully
            volumes = []
            for c in candles:
                try:
                    volumes.append(float(c[5]))
                except (IndexError, ValueError):
                    volumes.append(0)
            
            current_close = closes[-1]
            current_high = highs[-1]
            current_low = lows[-1]
            
            # Volume confirmation: [V27.6] The trigger candle must have 1.5x the average volume of the previous 10 candles
            avg_vol_10 = sum(volumes[-11:-1]) / 10 if len(volumes) >= 11 else 1
            trigger_vol = volumes[-1] if volumes else 0
            volume_confirmed = trigger_vol >= (avg_vol_10 * 1.5)
            
            # Funding rate
            funding_rate = await okx_rest_service.get_funding_rate(symbol)
            
            # [V46.0] Premium Liquidity & Sentiment Injection
            ls_ratio = await okx_rest_service.get_account_ratio(symbol)
            oi_history = await okx_rest_service.get_open_interest_history(symbol, interval="5min", limit=3)
            
            oi_rising = False
            if len(oi_history) >= 2:
                curr_oi = float(oi_history[0].get("openInterest", 0))
                prev_oi = float(oi_history[1].get("openInterest", 0))
                if prev_oi > 0:
                    oi_change = (curr_oi - prev_oi) / prev_oi
                    oi_rising = oi_change > 0.001 # At least 0.1% increase in capital
            
            side_norm = side.lower()
            trigger_type = None
            confidence = 0
            
            # === TRIGGER A: Zone Reaction (SNIPER) ===
            zone_result = self._detect_zone_reaction(
                candles, side_norm, zones_15m, closes, highs, lows
            )
            if zone_result['detected']:
                # [V27.6] CVD Needle Flip Confirmation
                cvd = okx_ws_public_service.get_cvd_score(symbol)
                # For Longs (support rejection), we want CVD to be recovering (not deeply negative anymore)
                cvd_flip_confirmed = (side_norm == "buy" and cvd > -10000) or (side_norm == "sell" and cvd < 10000)
                
                # [V46.0] LS/OI Confirmation (The Tocaia Bridge)
                # Sinais com liquidez (OI subindo) ganham bônus de confiança
                liquidity_mult = 1.1 if oi_rising else 0.95
                
                if cvd_flip_confirmed and volume_confirmed:
                    trigger_type = "ZONE_REACTION"
                    confidence = zone_result['confidence'] * liquidity_mult
                    logger.info(f"✅ [V46.0] Calibrated Sniper: {symbol} | LS={ls_ratio:.2f} | OI Rising={oi_rising} | Conf={confidence:.1f}")
                else:
                    logger.debug(f"🚧 [V27.6] Zone Reaction ignored for {symbol}: CVD Flip={cvd_flip_confirmed}, Vol={volume_confirmed}")
            
            # === TRIGGER B: Breakout Confirmation ===
            if not trigger_type:
                breakout_result = self._detect_breakout_confirmation(
                    candles, side_norm, closes, highs, lows
                )
                if breakout_result['detected']:
                    # [V46.0] Breakout must have OI confirmation to be valid (Smart Money Entry)
                    if oi_rising or volume_confirmed:
                        trigger_type = "BREAKOUT"
                        confidence = breakout_result['confidence']
                    else:
                        logger.info(f"🚧 [V46.0] Breakout REJECTED (No Liquidity): {symbol} | OI Rising={oi_rising} | Vol={volume_confirmed}")
            
            # === TRIGGER C: Funding Squeeze ===
            if not trigger_type:
                # Long squeeze: funding very negative + CVD turning heavily positive + volume
                # Short squeeze: funding very positive + CVD turning heavily negative + volume
                cvd = okx_ws_public_service.get_cvd_score(symbol)
                # [V28.2] Strict Funding Squeeze: Raised from 5k to 80k CVD and requires volume bump
                if side_norm == "buy" and funding_rate < -0.0003 and cvd > 80000 and volume_confirmed:
                    trigger_type = "FUNDING_SQUEEZE"
                    confidence = min(90, 60 + abs(funding_rate) * 100000)
                elif side_norm == "sell" and funding_rate > 0.0005 and cvd < -80000 and volume_confirmed:
                    trigger_type = "FUNDING_SQUEEZE"
                    confidence = min(90, 60 + abs(funding_rate) * 100000)
                    
            # === TRIGGER D: MOMENTUM SURFE (TREND FOLLOWING) ===
            if not trigger_type:
                cvd = okx_ws_public_service.get_cvd_score(symbol)
                try:
                    regime_data = await self.detect_market_regime(symbol)
                    is_trending = regime_data.get('regime') == 'TRENDING'
                except:
                    is_trending = False
                
                if is_trending:
                    if side_norm == "buy" and cvd > 80000 and volume_confirmed:
                        trigger_type = "TREND_SURF"
                        confidence = 90
                        logger.info(f"🌊 [TREND SURF] {symbol} Bullish Breakout/Momentum detected (CVD={cvd})")
                    elif side_norm == "sell" and cvd < -80000 and volume_confirmed:
                        trigger_type = "TREND_SURF"
                        confidence = 90
                        logger.info(f"🌊 [TREND SURF] {symbol} Bearish Breakdown/Momentum detected (CVD={cvd})")
            
            # Funding contradiction penalty
            funding_contradiction = False
            if side_norm == "buy" and funding_rate > 0.0005:
                funding_contradiction = True  # Market euphoric — risky for longs
                confidence = max(0, confidence - 15)
            elif side_norm == "sell" and funding_rate < -0.0005:
                funding_contradiction = True  # Market fearful — risky for shorts
                confidence = max(0, confidence - 15)
            
            # [V46.0] Retail Trap Filter
            # Se LS Ratio está muito alto (> 1.8), varejo está muito LONG -> Risco de Trap para Longs
            if side_norm == "buy" and ls_ratio > 1.8:
                confidence = max(0, confidence - 20)
                logger.info(f"⚠️ [V46.0] Retail Trap Warning (LS High): {symbol} | LS={ls_ratio}")
            elif side_norm == "sell" and ls_ratio < 0.6:
                confidence = max(0, confidence - 20)
                logger.info(f"⚠️ [V46.0] Retail Trap Warning (LS Low): {symbol} | LS={ls_ratio}")

            # === [V7.0] THE PERFECT ENTRY: Fibonacci & Orderflow Confluence ===
            fib = await self.get_fibonacci_levels(symbol, interval="15", limit=40)
            walls = await self.get_orderbook_walls(symbol)
            
            fib_confluence = 0
            if fib and 'golden_zone' in fib:
                z_low, z_high = fib['golden_zone']
                # Check if price is within the golden zone (with a small buffer)
                zone_range = abs(z_high - z_low)
                z_min, z_max = (min(z_low, z_high), max(z_low, z_high))
                if (z_min - zone_range*0.1) <= current_close <= (z_max + zone_range*0.1):
                    fib_confluence = 25 # Major bonus for Golden Zone
                    logger.info(f"🏆 [V7.0] GOLDEN ZONE CONFLUENCE: {symbol} at {current_close} (Zone: {z_min:.6f}-{z_max:.6f})")
                else:
                    # Check for 0.382 or 0.786
                    for lvl_name in ['0.382', '0.786']:
                        lvl_price = fib['levels'].get(lvl_name, 0)
                        if abs(current_close - lvl_price) / current_close < 0.002:
                            fib_confluence = 15
                            break
            
            wall_confluence = 0
            if side_norm == "buy" and walls.get('buy_walls'):
                # Are there walls below us supporting the move?
                nearest_wall = max(walls['buy_walls'])
                if current_close > nearest_wall and (current_close - nearest_wall)/current_close < 0.005:
                    wall_confluence = 15
            elif side_norm == "sell" and walls.get('sell_walls'):
                # Are there walls above us resisting the move?
                nearest_wall = min(walls['sell_walls'])
                if current_close < nearest_wall and (nearest_wall - current_close)/current_close < 0.005:
                    wall_confluence = 15
            
            confidence += (fib_confluence + wall_confluence)

            # === [V55.0] SMC & MICROSTRUCTURE CONFIRMATION ===
            
            # 1. Fair Value Gap (FVG) - Are we entering into an imbalance?
            fvgs = await self.detect_fvg(symbol, interval="5")
            has_fvg_confluence = False
            for fvg in fvgs:
                # If Long, we want a Bullish FVG below us (support) or entering a Bearish FVG to fill it
                if side_norm == "buy" and fvg["type"] == "BULLISH_FVG" and current_close > fvg["mid"]:
                    has_fvg_confluence = True
                    confidence += 10
                elif side_norm == "sell" and fvg["type"] == "BEARISH_FVG" and current_close < fvg["mid"]:
                    has_fvg_confluence = True
                    confidence += 10
            
            # 2. Market Structure (CHoCH/BoS)
            structure = await self.detect_choch_and_bos(symbol)
            if (side_norm == "buy" and "BULLISH" in structure["status"]) or \
               (side_norm == "sell" and "BEARISH" in structure["status"]):
                confidence += 15
                logger.info(f"📊 [V55.0] Structure Aligned: {symbol} | {structure['status']}")
            
            # 3. Spring/Upthrust (Liquidity Sweep)
            spring = await self.detect_spring(symbol)
            if spring["detected"]:
                if (side_norm == "buy" and spring["type"] == "SPRING") or \
                   (side_norm == "sell" and spring["type"] == "UPTHRUST"):
                    confidence += 20
                    logger.info(f"🦇 [V55.0] LIQUIDITY SWEEP DETECTED! {symbol} | {spring['type']}")

            # 4. Microstructure (VAMP & OBI)
            vamp = okx_ws_public_service.vamp_cache.get(symbol, 0)
            obi = okx_ws_public_service.obi_cache.get(symbol, 0)
            
            if vamp > 0:
                # If Long, price below VAMP = "Cheap/Attractive"
                if side_norm == "buy" and current_close < vamp:
                    confidence += 12
                # If Short, price above VAMP = "Expensive/Rejection"
                elif side_norm == "sell" and current_close > vamp:
                    confidence += 12
            
            if (side_norm == "buy" and obi > 0.4) or (side_norm == "sell" and obi < -0.4):
                confidence += 15
                logger.info(f"🔥 [V55.0] OBI PRESSURE CONFIRMED: {symbol} | OBI={obi}")

            # [V43.2] Aumentando rigor: Confiança mínima sobe de 65 para 75 para recuperação de banca
            # [V62.0 MAESTRIA] Rigor cirúrgico para Mercado Lateral (RANGING)
            try:
                regime_data = await self.detect_market_regime(symbol)
                is_market_ranging = regime_data.get('regime', 'TRANSITION') == 'RANGING'
            except Exception as e:
                logger.warning(f"Failed to detect regime for {symbol} in 5m trigger: {e}")
                is_market_ranging = False
                
            # [V71.5] RELAXED CONFIDENCE: Lowered from 85/75 to 70/65 for better reactivity
            min_confidence = 70 if is_market_ranging else 65
            
            # [V62.0] Filtro de Baixa Volatilidade (Mar Morto)
            atr = okx_ws_public_service.atr_cache.get(symbol, 0)
            asset_volatility = (atr / current_close) if (atr and current_close > 0) else 0
            is_dead_market = asset_volatility < 0.002 # Menos de 0.2% de volatilidade ATR
            
            cvd = okx_ws_public_service.get_cvd_score(symbol)
            is_exhausted = False
            is_heavy_momentum = False
            
            if trigger_type != "TREND_SURF":
                # [V110.116] ADAPTIVE CVD EXHAUSTION: High momentum (ROARING) allows more institutional flow
                is_roaring = regime_data.get('regime') == 'ROARING'
                exhaustion_limit = 300000 if is_roaring else 150000
                momentum_limit = 150000 if is_roaring else 80000

                is_exhausted = (side_norm == "buy" and cvd > exhaustion_limit) or (side_norm == "sell" and cvd < -exhaustion_limit)
                
                # [V27.5] Momentum Block: Filtro Anti-Rolo Compressor
                is_heavy_momentum = (side_norm == "sell" and cvd > momentum_limit) or (side_norm == "buy" and cvd < -momentum_limit)
                
                if is_exhausted:
                    logger.info(f"🚫 [CVD-EXHAUSTION] {symbol} | limit={exhaustion_limit} | CVD={cvd}")
                if is_heavy_momentum and not is_exhausted:
                    logger.info(f"🚫 [V27.5] BLOCK: Heavy Momentum on {symbol} | side={side_norm} | CVD={cvd} | limit={momentum_limit}")
            
            has_trigger = trigger_type is not None and confidence >= min_confidence and not is_exhausted and not is_heavy_momentum and not is_dead_market
            
            if not has_trigger and trigger_type:
               reason = "LOW_CONFIDENCE" if confidence < min_confidence else ("DEAD_MARKET" if is_dead_market else "SENTI_BLOCK")
               logger.info(f"🚧 [5m-TRIGGER REJECT] {symbol} {side_norm}: Type={trigger_type}, Conf={confidence:.1f} (min={min_confidence}), Reason={reason}")
            elif not trigger_type:
               logger.debug(f"🔍 [5m-TRIGGER NONE] {symbol} {side_norm}: Sem gatilho de zona/breakout/squeeze neste candle.")
            
            return {
                'has_trigger': has_trigger,
                'trigger_type': trigger_type,
                'confidence': round(confidence, 1),
                'funding_rate': funding_rate,
                'funding_contradiction': funding_contradiction,
                'volume_confirmed': volume_confirmed,
                'ls_ratio': ls_ratio,
                'oi_rising': oi_rising,
                'is_trend_surf': trigger_type == "TREND_SURF"
            }
        except Exception as e:
            logger.warning(f"[V25.1] 5m trigger analysis error for {symbol}: {e}")
            return {'has_trigger': False, 'trigger_type': None, 'confidence': 0, 'funding_rate': 0, 'volume_confirmed': False}
    
    def _detect_zone_reaction(self, candles, side_norm, zones_15m, closes, highs, lows) -> dict:
        """
        [V25.1] Detects price rejection at a support/resistance zone.
        A valid zone reaction requires:
        1. Price touched a zone (within 0.3%)
        2. Last candle has a rejection wick >= 50% of total range
        """
        support = zones_15m.get('support', 0)
        resistance = zones_15m.get('resistance', 0)
        
        if not support and not resistance:
            return {'detected': False, 'confidence': 0}
        
        last_close = closes[-1]
        last_high = highs[-1]
        last_low = lows[-1]
        last_range = last_high - last_low
        
        if last_range <= 0:
            return {'detected': False, 'confidence': 0}
        
        body_top = max(last_close, float(candles[-1][1]))  # open
        body_bottom = min(last_close, float(candles[-1][1]))
        body_ratio = abs(body_top - body_bottom) / last_range
        
        if side_norm == "buy" and support > 0:
            # Check if price touched support zone (within 0.3%)
            distance_to_support = abs(last_low - support) / support * 100
            if distance_to_support < 0.3:
                # Check for bullish rejection: lower wick >= 50% of range
                lower_wick = body_bottom - last_low
                wick_ratio = lower_wick / last_range
                
                # [V27.5] Strict Zone Reaction: Corpo pequeno (<= 35%) OU Fechamento a favor (Verde)
                is_strict_reaction = body_ratio <= 0.35 or last_close > float(candles[-1][1])
                
                if wick_ratio >= 0.5 and last_close > body_bottom and is_strict_reaction:
                    confidence = min(90, 60 + wick_ratio * 30)
                    logger.info(f"🎯 [V27.5] STRICT ZONE REACTION (buy): {candles[-1]} near support {support:.6f}, wick_ratio={wick_ratio:.2f}, body_ratio={body_ratio:.2f}")
                    return {'detected': True, 'confidence': confidence}
        
        elif side_norm == "sell" and resistance > 0:
            distance_to_resistance = abs(last_high - resistance) / resistance * 100
            if distance_to_resistance < 0.3:
                # Check for bearish rejection: upper wick >= 50% of range
                upper_wick = last_high - body_top
                wick_ratio = upper_wick / last_range
                
                # [V27.5] Strict Zone Reaction: Corpo pequeno (<= 35%) OU Fechamento a favor (Vermelho)
                is_strict_reaction = body_ratio <= 0.35 or last_close < float(candles[-1][1])
                
                if wick_ratio >= 0.5 and last_close < body_top and is_strict_reaction:
                    confidence = min(90, 60 + wick_ratio * 30)
                    logger.info(f"🎯 [V27.5] STRICT ZONE REACTION (sell): near resistance {resistance:.6f}, wick_ratio={wick_ratio:.2f}, body_ratio={body_ratio:.2f}")
                    return {'detected': True, 'confidence': confidence}
        
        return {'detected': False, 'confidence': 0}
    
    def _detect_breakout_confirmation(self, candles, side_norm, closes, highs, lows) -> dict:
        """
        [V25.1] Detects breakout confirmation: price CLOSES above/below recent resistance/support.
        Requires the last 5m candle to CLOSE beyond the level (not just wick).
        """
        if len(closes) < 15:
            return {'detected': False, 'confidence': 0}
        
        # Find recent resistance (highest close of candles 5-15) and support (lowest close)
        lookback_highs = highs[5:15]
        lookback_lows = lows[5:15]
        recent_resistance = max(lookback_highs) if lookback_highs else 0
        recent_support = min(lookback_lows) if lookback_lows else 0
        
        last_close = closes[-1]
        prev_close = closes[-2]
        
        if side_norm == "buy" and recent_resistance > 0:
            # Breakout: current candle CLOSES above recent resistance AND previous didn't
            if last_close > recent_resistance and prev_close <= recent_resistance:
                breakout_strength = (last_close - recent_resistance) / recent_resistance * 100
                confidence = min(85, 55 + breakout_strength * 50)
                logger.info(f"🚀 [V25.1] BREAKOUT CONFIRMED (buy): Close {last_close:.6f} > Resistance {recent_resistance:.6f}")
                return {'detected': True, 'confidence': confidence}
        
        elif side_norm == "sell" and recent_support > 0:
            if last_close < recent_support and prev_close >= recent_support:
                breakout_strength = (recent_support - last_close) / recent_support * 100
                confidence = min(85, 55 + breakout_strength * 50)
                logger.info(f"🚀 [V25.1] BREAKOUT CONFIRMED (sell): Close {last_close:.6f} < Support {recent_support:.6f}")
                return {'detected': True, 'confidence': confidence}
        
        return {'detected': False, 'confidence': 0}

    async def _sync_radar_rtdb(self):
        """[V15.7.5] Synchronizes latest signals and decisions to RTDB for the frontend Radar."""
        if getattr(self, "_is_syncing_radar", False):
            logger.debug("📡 [RADAR-PULSE] Sincronização anterior ainda ativa. Pulando ciclo para evitar afunilamento.")
            return
        self._is_syncing_radar = True
        try:
            from services.okx_ws_public import okx_ws_public_service
            # V15.7.5: Added logging to verify sync is happening
            logger.info("📡 [RADAR-PULSE] Syncing signals and decisions to RTDB...")
            signals = await firebase_service.get_recent_signals(limit=25)
            decisions = []
            
            for sig in signals[:15]: # Top 15 decisions
                symbol = sig.get("symbol", "")
                if not symbol: continue
                
                # [V46.0] Real-time Pressure Injection for Radar
                # We fetch live metrics from BybitWS to override staleFirestore data
                cvd_5m = okx_ws_public_service.get_cvd_score_time(symbol, 300)
                cvd_total = okx_ws_public_service.get_cvd_score(symbol)
                
                if "indicators" not in sig:
                    sig["indicators"] = {}
                
                sig["indicators"]["cvd_5m"] = round(cvd_5m, 2)
                sig["indicators"]["cvd"] = round(cvd_total, 2) # Total for the visual meter

                # [V110.805] Radar Contract Intelligence: the signal report must carry
                # the same OKX instrument metadata used later by Captain/Flash.
                if not sig.get("contract_info"):
                    try:
                        from services.okx_rest import okx_rest_service
                        contract_info = await asyncio.wait_for(
                            okx_rest_service.get_detailed_contract_info(symbol),
                            timeout=2.5
                        )
                        details = contract_info.get("contract_details", {})
                        risk = contract_info.get("risk_analysis", {})
                        sig["contract_info"] = {
                            "ctVal": details.get("ctVal", 1.0),
                            "lotSize": details.get("lotSize", details.get("qtyStep", 1.0)),
                            "minQty": details.get("minQty", 1.0),
                            "tickSize": details.get("tickSize", 0.01),
                            "maxLeverage": details.get("maxLeverage", sig.get("leverage", 50)),
                            "notionalUsd": details.get("notionalUsd", 0),
                            "riskImpactPerContract": risk.get("price_impact_per_contract", 0),
                            "minMarginRequired": risk.get("min_margin_required", 0),
                            "symbol": contract_info.get("symbol", symbol),
                            "currentPrice": contract_info.get("current_price", 0),
                        }
                        sig["leverage"] = sig.get("leverage") or sig["contract_info"].get("maxLeverage", 50)
                    except Exception as contract_err:
                        logger.warning(f"Radar contract enrichment fail for {symbol}: {contract_err}")
                
                # [V42.9] Enhanced Context Injection
                trend_data = self.trend_cache.get(symbol, {})
                trend_1h = trend_data.get("trend", "sideways")
                
                # [V56.0] Unified Intelligence Enrichment (Top 15 for better coverage)
                if signals.index(sig) < 15:
                    try:
                        cache = self.radar_consensus_cache.get(symbol)
                        if cache and (time.time() - cache["updated_at"]) < 300:
                            consensus = cache["data"]
                        else:
                            from services.agents.captain import captain_agent
                            # [V125 Failsafe Timeout] Evita congelamento se os agentes do kernel demorarem a responder
                            try:
                                consensus = await asyncio.wait_for(
                                    captain_agent._get_fleet_consensus({
                                        "symbol": symbol,
                                        "side": sig.get("side", "Buy"),
                                        "score": sig.get("score", 70)
                                    }),
                                    timeout=3.0
                                )
                            except asyncio.TimeoutError:
                                logger.warning(f"⏱️ [FLEET-TIMEOUT] Timeout de 3s na consulta do consenso para {symbol}. Usando fallback neutro.")
                                consensus = {
                                    "unified_confidence": 50,
                                    "intel": {"macro": 50, "micro": 50, "smc": 50, "onchain": 50}
                                }
                            self.radar_consensus_cache[symbol] = {"data": consensus, "updated_at": time.time()}
                        
                        sig["unified_confidence"] = consensus.get("unified_confidence", 50)
                        sig["fleet_intel"] = consensus.get("intel", {})
                    except Exception as e:
                        logger.warning(f"Radar consensus fail for {symbol}: {e}")

                # [V57.0] Decorrelation Intelligence Injection
                try:
                    d_cache = self.decorrelation_cache.get(symbol)
                    if d_cache and (time.time() - d_cache["updated_at"]) < 30: # 30s TTL
                        decorrelation = d_cache["data"]
                    else:
                        # [V57.0] Decorrelation Hunter Enrichment
                        d_res = await self.detect_btc_decorrelation(symbol)
                        is_decorrelated = d_res.get('is_decorrelated', False)
                        d_confidence = d_res.get('confidence', 0)
                        d_direction = d_res.get('direction', 'Neutral')
                        d_signals = d_res.get('signals', [])
                        correlation = d_res.get('correlation', 1.0)
                        
                        decorrelation = {
                            "score": round(d_confidence, 1),
                            "is_active": is_decorrelated,
                            "direction": d_direction,
                            "correlation": round(correlation, 3),
                            "signals": d_signals,
                            "updated_at": time.time()
                        }
                        self.decorrelation_cache[symbol] = {"data": decorrelation, "updated_at": time.time()}
                    
                    sig["decorrelation"] = decorrelation
                except Exception as e:
                    logger.warning(f"Decorrelation enrichment fail for {symbol}: {e}")
                
                # Fetch ADX and Regime (uses cache inside detect_market_regime)
                # We do it sequentially here because it's a small loop and mostly cached
                try:
                    # Note: detect_market_regime is async, but we can't easily await inside here without a separate task
                    # For now, let's look at the cache directly or use a default if it's missing to avoid blocking
                    regime_data = self.market_regime_cache.get(symbol, {"regime": "TRANSITION", "adx": 20})
                    adx_val = regime_data.get("adx", 20)
                    mkt_regime = regime_data.get("regime", trend_1h.upper())
                except:
                    adx_val = 20
                    mkt_regime = "TRANSITION"

                signal_pattern = sig.get("indicators", {}).get("pattern")
                pattern = signal_pattern if signal_pattern else trend_data.get("pattern", "none")
                
                is_blocked, remaining = await firebase_service.is_symbol_blocked(symbol)
                status = "blocked" if is_blocked else "eligible"
                
                decisions.append({
                    "symbol": symbol,
                    "trend_1h": trend_1h,
                    "pattern": pattern,
                    "score": sig.get("score", 0),
                    "adx": adx_val,
                    "regime": mkt_regime,
                    "status": status,
                    "remaining_cooldown": remaining
                })

            # V15.7.7: Inject recent rejections for frontend visibility
            now = time.time()
            self.recent_rejections = [r for r in self.recent_rejections if now - r['timestamp'] < 120] # Keep for 2 mins
            for rej in self.recent_rejections[:3]: # Show top 3 rejections
                 decisions.append({
                     "symbol": rej['symbol'],
                     "trend_1h": "rejected",
                     "pattern": rej['reason'],
                     "score": 0,
                     "status": "rejected",
                     "remaining_cooldown": 0
                 })

            # V30.2: Include BTC Market Context for UI Dashboard
            btc_dir = await self.get_btc_direction_filter()
            # [V110.36.7] SSOT M-ADX para o RadarPulse (Fim da Dualidade Visual)
            # Utiliza estritamente o M-ADX master computado assincronamente pelo websocket 
            # para remover completamente resquícios do 1H-ADX antigo e cravando a consistência UI.
            m_adx_radar = getattr(okx_ws_public_service, 'btc_adx', 0)
            
            # Inferir regime puramente pelo threshold M-ADX oficial do backend
            if m_adx_radar >= 30: inferred_regime = "ROARING"
            elif m_adx_radar >= 25: inferred_regime = "TRENDING"
            else: inferred_regime = "RANGING"

            btc_regime = {"regime": inferred_regime, "adx": m_adx_radar}
            
            logger.info(f"🔍 [DEBUG-BTC] Syncing: Dir={btc_dir.get('direction')} Regime={inferred_regime} ADX={m_adx_radar:.1f}")
            # [V57.0] Calculate Global Decorrelation Temperature
            d_scores = [sig.get("decorrelation", {}).get("score", 0) for sig in signals[:10] if "decorrelation" in sig]
            d_active = [sig for sig in signals[:10] if sig.get("decorrelation", {}).get("is_active")]
            avg_d_score = sum(d_scores) / len(d_scores) if d_scores else 0
            
            # [V110.172] BTC Dominance — valor real via Oracle (era mockado com random!)
            try:
                from services.agents.oracle_agent import oracle_agent
                _oracle_ctx = await oracle_agent.get_context()
                mock_dom = _oracle_ctx.get("dominance", 0.0)
                if mock_dom <= 0:
                    from services.agents.macro_analyst import macro_analyst
                    mock_dom = getattr(macro_analyst, '_dom_cache', 58.0) or 58.0
            except Exception:
                mock_dom = 58.0
            
            # [V110.950] Calculate Global Heat Index (Average velocity of monitored symbols)
            try:
                from services.okx_ws_public import okx_ws_public_service
                velocities = list(okx_ws_public_service.velocity_cache.values())
                global_heat = sum(velocities) / len(velocities) if velocities else 0.0
            except Exception:
                global_heat = 0.0
            
            final_direction = "LATERAL" if m_adx_radar < 25 else btc_dir.get("direction", "NEUTRAL")
            if final_direction == "NEUTRAL":
                final_direction = "LATERAL"

            market_context = {
                "btc_direction": final_direction,
                "btc_strength": btc_dir.get("strength", 0),
                "btc_regime": btc_regime.get("regime", "TRANSITION"),
                "btc_adx": btc_regime.get("adx", 20),
                "btc_dominance": round(mock_dom, 1),
                "btc_price": okx_ws_public_service.btc_price,
                "btc_variation_1h": round(okx_ws_public_service.btc_variation_1h, 2),
                "btc_variation_24h": round(okx_ws_public_service.btc_variation_24h, 2),
                "btc_variation_15m": round(okx_ws_public_service.btc_variation_15m, 2),
                "decorrelation_avg": round(avg_d_score, 1),
                "decorrelation_active_count": len(d_active),
                "heat_index": round(global_heat, 2),
                "radar_mode": self.current_radar_mode
            }

            # [DECOR_HUNTER 2.0] Varredura de pares desgrudados do BTC em QUALQUER regime.
            # Diferente da V1 que só ativava em RANGING, agora o DECOR_HUNTER 2.0
            # monitora 100 pares continuamente e só aprova sinais com gás legítimo
            # (Pearson < 0.35 + CVD forte + ratio > 2.0 + confidence >= 70).
            try:
                decor_hits = await self._scan_decorrelated_hunters()
                if decor_hits:
                    signals = decor_hits + [s for s in signals if s.get("symbol") not in {d["symbol"] for d in decor_hits}]
                    market_context["radar_mode"] = "DECOR_HUNTER"
                    logger.info(f"[DECOR-HUNTER 2.0] {len(decor_hits)} pares desgrudados com gas injetados no Radar.")
            except Exception as dh_err:
                logger.warning(f"DECOR-HUNTER 2.0 injection error: {dh_err}")

            await firebase_service.update_radar_pulse(
                signals=signals, 
                decisions=decisions, 
                market_context=market_context
            )

        except Exception as e:
            logger.error(f"Error syncing radar RTDB during init: {e}")
        finally:
            self._is_syncing_radar = False

    async def _scan_decorrelated_hunters(self) -> list:
        """
        [DECOR_HUNTER 2.0] Varre a DECOR_WATCHLIST (100 pares) em busca de pares
        genuinamente desgrudados do BTC com GÁS real.
        Opera em QUALQUER regime de mercado (RANGING, TRANSITION, TRENDING).
        Critérios de aprovação (gate):
          - Pearson < 0.35 (15h) OU corr_short < 0.25 (4h)
          - confidence >= 70
          - CVD mínimo de 20k na direção do movimento
          - decorrelation_ratio > 2.0 (alt move 2x+ mais que BTC)
          - OI em alta (desejável mas não mandatório)
        """
        try:
            from config import settings
            watchlist = getattr(settings, 'DECOR_WATCHLIST', [])
            if not watchlist:
                return []

            logger.info(f"[DECOR-HUNTER 2.0] Scan de {len(watchlist)} pares em busca de desgrudados com gas...")
            decor_signals = []
            sem = asyncio.Semaphore(10)

            async def _check_pair(symbol):
                async with sem:
                    try:
                        sym_key = symbol + ".P" if not symbol.endswith(".P") else symbol
                        d_res = await self.detect_btc_decorrelation(sym_key)
                        is_decor = d_res.get('is_decorrelated', False)
                        confidence = d_res.get('confidence', 0)
                        correlation = d_res.get('correlation', 1.0)
                        direction = d_res.get('direction', 'Neutral')
                        signals = d_res.get('signals', [])

                        # GATE: confiança mínima
                        if not is_decor or confidence < 70:
                            return None

                        # GATE: CVD (gás real, não apenas ruído)
                        has_cvd = any('CVD' in s for s in signals)
                        if not has_cvd:
                            return None

                        # GATE: decorrelation_ratio - alt move pelo menos 2x mais que BTC
                        has_ratio = any('RATIO' in s for s in signals)
                        if not has_ratio:
                            return None

                        sym_price = okx_ws_public_service.get_current_price(sym_key)
                        side = "Buy" if direction in ("Bullish", "Up", "Long") else "Sell"
                        clean_sym = symbol.replace(".P", "")
                        logger.info(f"[DECOR-HUNTER 2.0] {clean_sym} GAS! Pearson={correlation:.2f} Dir={direction} Conf={confidence:.0f}%")
                        return {
                            "symbol": clean_sym,
                            "side": side,
                            "strategy": "DECOR_HUNTER",
                            "score": min(99, int(confidence)),
                            "layer": "DECOR",
                            "price": sym_price,
                            "currentPrice": sym_price,
                            "decorrelation": {
                                "is_active": True,
                                "score": round(confidence, 1),
                                "correlation": round(correlation, 3),
                                "direction": direction,
                                "signals": signals
                            },
                            "unified_confidence": int(confidence),
                            "fleet_intel": {"macro": 50, "whale": 50, "smc": int(confidence)},
                            "radar_mode": "DECOR_HUNTER",
                            "timestamp": time.time()
                        }
                    except Exception:
                        return None

            tasks = [_check_pair(sym) for sym in watchlist]
            results = await asyncio.gather(*tasks)
            decor_signals = [r for r in results if r is not None]

            logger.info(f"[DECOR-HUNTER 2.0] Scan concluido: {len(decor_signals)} pares com gas encontrados de {len(watchlist)}.")
            return sorted(decor_signals, key=lambda x: x['score'], reverse=True)

        except Exception as e:
            logger.error(f"Erro no DECOR-HUNTER 2.0 scan: {e}")
            return []

    # ===============================================================
    # [V27.0] PHASE 3: MULTI-TIMEFRAME INTELLIGENCE V2
    # ===============================================================

    async def get_daily_macro_filter(self, symbol: str) -> dict:
        """
        V27.0: Daily (1D) macro structure filter.
        Uses EMA50 and SMA200 to determine if macro trend supports the trade direction.
        Returns: {'trend': 'bullish'|'bearish'|'sideways', 'ema50': float, 'sma200': float, 
                  'above_200sma': bool, 'pct_from_ema50': float}
        """
        try:
            cached = self.trend_cache_daily.get(symbol)
            if cached and (time.time() - cached.get('updated_at', 0)) < self.trend_cache_daily_ttl:
                return cached
            
            klines = await okx_rest_service.get_klines(symbol=symbol, interval="D", limit=200)
            
            if not klines or len(klines) < 50:
                return {'trend': 'sideways', 'ema50': 0, 'sma200': 0, 'above_200sma': True, 'pct_from_ema50': 0}
            
            candles = klines[::-1]  # Chronological order
            closes = [float(c[4]) for c in candles]
            current_price = closes[-1]
            
            # Calculate EMA50
            multiplier_50 = 2 / (50 + 1)
            ema50 = sum(closes[:50]) / 50
            for price in closes[50:]:
                ema50 = (price - ema50) * multiplier_50 + ema50
            
            # Calculate SMA200 (if enough data)
            sma200 = 0
            above_200sma = True
            if len(closes) >= 200:
                sma200 = sum(closes[-200:]) / 200
                above_200sma = current_price > sma200
            
            pct_from_ema50 = ((current_price - ema50) / ema50) * 100 if ema50 > 0 else 0
            
            # Trend determination
            if pct_from_ema50 > 1.0 and above_200sma:
                trend = 'bullish'
            elif pct_from_ema50 < -1.0 and not above_200sma:
                trend = 'bearish'
            elif pct_from_ema50 > 0.3:
                trend = 'bullish'
            elif pct_from_ema50 < -0.3:
                trend = 'bearish'
            else:
                trend = 'sideways'
            
            result = {
                'trend': trend,
                'ema50': round(ema50, 8),
                'sma200': round(sma200, 8),
                'above_200sma': above_200sma,
                'pct_from_ema50': round(pct_from_ema50, 2),
                'updated_at': time.time()
            }
            
            self.trend_cache_daily[symbol] = result
            logger.info(f"📊 [V27.0] Daily Macro {symbol}: {trend} | EMA50 dist: {pct_from_ema50:.2f}% | Above SMA200: {above_200sma}")
            return result
            
        except Exception as e:
            logger.warning(f"V27.0 Daily Macro Error for {symbol}: {e}")
            return {'trend': 'sideways', 'ema50': 0, 'sma200': 0, 'above_200sma': True, 'pct_from_ema50': 0}

    async def detect_squeeze(self, symbol: str, bb_width: float) -> dict:
        """
        [V43.0] Bollinger Squeeze Detection.
        A Squeeze occurs when BB Width is at a relative low (historical context).
        High risk of falsy breakouts (Traps).
        """
        try:
            # We use the bb_width calculated in detect_market_regime
            # A squeeze is typically < 1.0% or 1.5% depending on the asset
            # But more robustly, we should compare to recent average
            
            is_squeeze = bb_width < 1.2 # Baseline for low volatility
            
            return {
                "is_squeeze": is_squeeze,
                "bb_width": bb_width,
                "risk_factor": "HIGH_TRAP_RISK" if is_squeeze else "NORMAL"
            }
        except Exception:
            return {"is_squeeze": False, "bb_width": bb_width}

    async def detect_market_regime(self, symbol: str) -> dict:
        """
        V43.0: Market Regime Detection using ADX & Squeeze logic.
        """
        try:
            # [V110.36.10] SSOT OVERRIDE: SE FOR BTC, USAR M-ADX MASTER (OKX-WS)
            # Isso elimina a esquizofrenia de regime entre execuo e visor lateral.
            if symbol == "BTCUSDT.P":
                from services.okx_ws_public import okx_ws_public_service
                m_adx = getattr(okx_ws_public_service, "btc_adx", 20.0)
                
                # Inferir regime baseado no M-ADX Master
                if m_adx >= 30: regime = "ROARING"
                elif m_adx >= 25: regime = "TRENDING"
                else: regime = "RANGING"

                res = {
                    'regime': regime, 
                    'adx': m_adx, 
                    'bb_width': 2.0, # Mocked for regime object consistency
                    'updated_at': time.time()
                }
                # logger.info(f"🔮 [REGIME-SSOT] BTC Detected: {regime} (ADX: {m_adx:.1f})")
                return res

            # Check cache for ALTS (TTL 15m)
            cached = self.market_regime_cache.get(symbol)
            if cached and (time.time() - cached.get('updated_at', 0)) < 180: # 3 min for live precision
                return cached
            
            # V110.30.2: Increased limit to 100 for stable ADX calculation (Wilder memory)
            klines = await okx_rest_service.get_klines(symbol=symbol, interval="60", limit=100)
            
            if not klines or len(klines) < 30:
                return {'regime': 'TRANSITION', 'adx': 20, 'bb_width': 0, 'updated_at': time.time()}

            
            candles = klines[::-1]  # Chronological order
            highs = [float(c[2]) for c in candles]
            lows = [float(c[3]) for c in candles]
            closes = [float(c[4]) for c in candles]
            
            # === ADX Calculation (14-period) ===
            period = 14
            tr_list, plus_dm_list, minus_dm_list = [], [], []
            for i in range(1, len(candles)):
                high_diff = highs[i] - highs[i-1]
                low_diff = lows[i-1] - lows[i]
                tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
                tr_list.append(tr)
                plus_dm = high_diff if (high_diff > low_diff and high_diff > 0) else 0
                minus_dm = low_diff if (low_diff > high_diff and low_diff > 0) else 0
                plus_dm_list.append(plus_dm)
                minus_dm_list.append(minus_dm)
            
            atr = sum(tr_list[:period]) / period
            plus_di_smooth = sum(plus_dm_list[:period]) / period
            minus_di_smooth = sum(minus_dm_list[:period]) / period
            dx_list = []
            for i in range(period, len(tr_list)):
                atr = (atr * (period - 1) + tr_list[i]) / period
                plus_di_smooth = (plus_di_smooth * (period - 1) + plus_dm_list[i]) / period
                minus_di_smooth = (minus_di_smooth * (period - 1) + minus_dm_list[i]) / period
                
                pdi = (plus_di_smooth / atr * 100) if atr > 0 else 0
                mdi = (minus_di_smooth / atr * 100) if atr > 0 else 0
                
                dx = (abs(pdi - mdi) / (pdi + mdi) * 100) if (pdi + mdi) > 0 else 0
                dx_list.append(dx)
            
            if not dx_list:
                adx = 20.0
            else:
                adx = sum(dx_list[:period]) / period
                for i in range(period, len(dx_list)):
                    adx = (adx * (period - 1) + dx_list[i]) / period
            
            # === Bollinger Band Width ===
            bb_period = 20
            bb_width = 5.0
            if len(closes) >= bb_period:
                recent_closes = closes[-bb_period:]
                sma = sum(recent_closes) / bb_period
                variance = sum((c - sma) ** 2 for c in recent_closes) / bb_period
                std_dev = variance ** 0.5
                bb_width = (4 * std_dev / sma * 100) if sma > 0 else 5.0
            
            # [V43.0] Squeeze Integration
            squeeze_data = await self.detect_squeeze(symbol, bb_width)
            is_squeeze = squeeze_data["is_squeeze"]

            # 🆕 [V110.32.1] Sync and Validate with Oracle Agent
            try:
                from services.agents.oracle_agent import oracle_agent
                oracle_payload = {"last_adx_calc_at": time.time()}
                if symbol == "BTCUSDT.P":
                    oracle_payload["btc_adx"] = adx
                
                await oracle_agent.update_market_data("signal_generator", oracle_payload)
                
                # Se for BTC, usamos o valor validado pelo Oracle (que pode ser o LKG durante o boot)
                if symbol == "BTCUSDT.P":
                    oracle_context = oracle_agent.get_validated_context()
                    # Durante o boot, o ADX calculado localmente pode ser 0 ou instável, 
                    # mas não aceitamos 0 do Oracle.
                    oracle_adx = oracle_context.get("btc_adx", 0)
                    if oracle_context.get("status") in ["SECURE", "BOOTING_RECOVERED", "STABILIZING"] and oracle_adx > 0.01:
                        adx = oracle_adx
            except Exception as oracle_err:
                logger.error(f"Error syncing with Oracle from SigGen: {oracle_err}")

            # Regime Classification
            # [V110.35.0] RELAXED TREND: ADX > 25 as requested by Admiral
            if adx > 25: 
                regime = 'TRENDING'
            elif adx < 18 or is_squeeze: # Reduced from 20 to admit more ranging context
                regime = 'RANGING'
            else:
                regime = 'TRANSITION'
            
            result = {
                'regime': regime,
                'adx': round(adx, 2),
                'bb_width': round(bb_width, 2),
                'is_squeeze': is_squeeze,
                'updated_at': time.time()
            }
            
            self.market_regime_cache[symbol] = result
            return result
            
        except Exception as e:
            logger.warning(f"V27.0 Market Regime Error for {symbol}: {e}")
            return {'regime': 'TRANSITION', 'adx': 20, 'bb_width': 0}

    # ═══════════════════════════════════════════════════════════════
    # [V55.0] SMART MONEY CONCEPTS (SMC) — FVG, CHoCH & Spring
    # ═══════════════════════════════════════════════════════════════

    async def detect_fvg(self, symbol: str, interval: str = "5") -> list:
        """
        [V55.0] Detects Fair Value Gaps (Imbalances).
        An FVG is a gap between the High of candle 1 and the Low of candle 3 
        (for Long) or Low of candle 1 and High of candle 3 (for Short).
        """
        try:
            klines = await okx_rest_service.get_klines(symbol=symbol, interval=interval, limit=10)
            if not klines or len(klines) < 3: return []
            
            # Klines: [newest, ..., oldest] -> Revers para [oldest, ..., newest]
            c = klines[::-1]
            fvgs = []
            
            for i in range(len(c) - 2):
                c1, c2, c3 = c[i], c[i+1], c[i+2]
                h1, l1 = float(c1[2]), float(c1[3])
                h3, l3 = float(c3[2]), float(c3[3])
                
                # Bullsih FVG (Gap Up)
                if l3 > h1:
                    fvgs.append({
                        "type": "BULLISH_FVG",
                        "top": l3,
                        "bottom": h1,
                        "mid": (l3 + h1) / 2,
                        "size_pct": (l3 - h1) / h1 * 100,
                        "index": i + 2
                    })
                # Bearish FVG (Gap Down)
                elif h3 < l1:
                    fvgs.append({
                        "type": "BEARISH_FVG",
                        "top": l1,
                        "bottom": h3,
                        "mid": (l1 + h3) / 2,
                        "size_pct": (l1 - h3) / h3 * 100,
                        "index": i + 2
                    })
            return fvgs
        except Exception as e:
            logger.error(f"FVG Detection error for {symbol}: {e}")
            return []

    async def detect_choch_and_bos(self, symbol: str) -> dict:
        """
        [V55.0] Detects Market Structure: Change of Character (CHoCH) and Break of Structure (BoS).
        CHoCH = First reversal of trend.
        BoS = Confirmation of existing trend.
        """
        try:
            klines = await okx_rest_service.get_klines(symbol=symbol, interval="15", limit=20)
            if not klines or len(klines) < 15: return {"trend": "NEUTRAL"}
            
            c = klines[::-1]
            highs = [float(x[2]) for x in c]
            lows = [float(x[3]) for x in c]
            closes = [float(x[4]) for x in c]
            
            # Find recent Swing High / Swing Low
            swing_high = max(highs[-15:-2])
            swing_low = min(lows[-15:-2])
            
            curr_close = closes[-1]
            prev_close = closes[-2]
            
            status = "NEUTRAL"
            if curr_close > swing_high:
                status = "BULLISH_BOS" if prev_close > swing_high else "BULLISH_CHoCH"
            elif curr_close < swing_low:
                status = "BEARISH_BOS" if prev_close < swing_low else "BEARISH_CHoCH"
                
            return {
                "status": status,
                "swing_high": swing_high,
                "swing_low": swing_low,
                "current": curr_close
            }
        except Exception:
            return {"status": "NEUTRAL"}

    async def detect_spring(self, symbol: str) -> dict:
        """
        [V55.0] Detects Wyckoff 'Spring' (Liquidity Sweep of a major low).
        Requirement: Break below recent low + Immediate reclaim (fake breakout).
        """
        try:
            klines = await okx_rest_service.get_klines(symbol=symbol, interval="5", limit=12)
            if not klines or len(klines) < 6: return {"detected": False}
            
            c = klines[::-1]
            lows = [float(x[3]) for x in c]
            closes = [float(x[4]) for x in c]
            
            # Major Low in previous 10 candles
            major_low = min(lows[:-2])
            
            last_low = lows[-1]
            last_close = closes[-1]
            
            # SPRING: Low broke major_low but close is ABOVE it
            if last_low < major_low and last_close > major_low:
                return {"detected": True, "type": "SPRING", "reclaim_pct": (last_close - major_low) / major_low * 100}
                
            # UPTHRUST (Short version): High broke major_high but close is BELOW it
            highs = [float(x[2]) for x in c]
            major_high = max(highs[:-2])
            last_high = highs[-1]
            
            if last_high > major_high and last_close < major_high:
                return {"detected": True, "type": "UPTHRUST", "reclaim_pct": (major_high - last_close) / major_high * 100}

            return {"detected": False}
        except Exception:
            return {"detected": False}

    async def detect_lrt_setup(self, symbol: str, zones_15m: dict) -> dict:
        """
        [V110.960 LRT] Detects Liquidity Sweep / Varredura de Liquidez.
        Checks if the last candles swept the 2H macro support/resistance and rejected quickly
        with a massive wick (>= 60% of total candle size) and climactic volume.
        """
        try:
            klines_15m = await okx_rest_service.get_klines(symbol=symbol, interval="15", limit=15)
            if not klines_15m or len(klines_15m) < 10:
                return {"detected": False}
            
            candles = klines_15m[::-1]
            closes = [float(c[4]) for c in candles]
            highs = [float(c[2]) for c in candles]
            lows = [float(c[3]) for c in candles]
            opens = [float(c[1]) for c in candles]
            volumes = [float(c[5]) for c in candles]
            
            last_low = lows[-1]
            last_high = highs[-1]
            last_close = closes[-1]
            last_open = opens[-1]
            last_volume = volumes[-1]
            
            support = zones_15m.get('support', 0)
            resistance = zones_15m.get('resistance', 0)
            
            # 1. Volume confirmation (2.0x above average of previous 10 candles)
            avg_vol_10 = sum(volumes[-11:-1]) / 10 if len(volumes) >= 11 else 1
            if last_volume < (avg_vol_10 * 2.0):
                return {"detected": False}
                
            total_range = last_high - last_low
            if total_range <= 0:
                return {"detected": False}
                
            body_top = max(last_close, last_open)
            body_bottom = min(last_close, last_open)
            
            # 2. Rejection Sweep Check (Wick >= 60%)
            # LONG Sweep (Touch support and wick up)
            if support > 0 and abs(last_low - support) / support < 0.005:
                lower_wick = body_bottom - last_low
                if (lower_wick / total_range) >= 0.60 and last_close > last_open:
                    return {"detected": True, "side": "Long", "type": "LRT_SUPPORT_SWEEP"}
                    
            # SHORT Sweep (Touch resistance and wick down)
            if resistance > 0 and abs(last_high - resistance) / resistance < 0.005:
                upper_wick = last_high - body_top
                if (upper_wick / total_range) >= 0.60 and last_close < last_open:
                    return {"detected": True, "side": "Short", "type": "LRT_RESISTANCE_SWEEP"}
                    
            return {"detected": False}
        except Exception as err:
            logger.error(f"Erro ao detectar setup LRT para {symbol}: {err}")
            return {"detected": False}

    async def detect_fas_setup(self, symbol: str) -> dict:
        """
        [V110.960 FAS] Detects Funding Squeeze setup.
        Checks for extreme funding rates matching CVD flow indicators.
        """
        try:
            funding_rate = await okx_rest_service.get_funding_rate(symbol)
            cvd_5m = okx_ws_public_service.get_cvd_score_time(symbol, 300)
            
            # Extreme Negative Funding Squeeze (Long opportunity)
            if funding_rate < -0.0010 and cvd_5m > 50000:
                return {"detected": True, "side": "Long", "type": "FAS_LONG_SQUEEZE", "rate": funding_rate}
                
            # Extreme Positive Funding Squeeze (Short opportunity)
            if funding_rate > 0.0015 and cvd_5m < -50000:
                return {"detected": True, "side": "Short", "type": "FAS_SHORT_SQUEEZE", "rate": funding_rate}
                
            return {"detected": False}
        except Exception as err:
            logger.error(f"Erro ao detectar setup FAS para {symbol}: {err}")
            return {"detected": False}


    # ═══════════════════════════════════════════════════════════════
    # [V42.0] RANGING SNIPER ALGORITHMS (V-Recovery & Box Breakout)
    # ═══════════════════════════════════════════════════════════════

    async def detect_v_recovery(self, symbol: str) -> dict:
        """
        V42.0: Detects fast 'V-Shaped' price recoveries.
        Looks for a deep wick below/above recent structure followed by a fast return.
        """
        try:
            klines = await okx_rest_service.get_klines(symbol=symbol, interval="5", limit=12)
            if not klines or len(klines) < 6: return {"detected": False}
            
            candles = klines[::-1]
            closes = [float(c[4]) for c in candles]
            highs = [float(c[2]) for c in candles]
            lows = [float(c[3]) for c in candles]
            
            # Detect Long Wick at the bottom (Bullish V)
            last_candle_low = lows[-1]
            last_candle_high = highs[-1]
            last_candle_close = closes[-1]
            last_candle_open = float(candles[-1][1])
            body_size = abs(last_candle_close - last_candle_open)
            
            # LONG V: Long wick at the bottom
            wick_low_size = min(last_candle_close, last_candle_open) - last_candle_low
            if wick_low_size > (body_size * 2) and last_candle_close > last_candle_low:
                return {"detected": True, "type": "LONG_V", "side": "Long", "strength": 85}
                
            # SHORT V: Long wick at the top
            wick_high_size = last_candle_high - max(last_candle_close, last_candle_open)
            if wick_high_size > (body_size * 2) and last_candle_close < last_candle_high:
                return {"detected": True, "type": "SHORT_V", "side": "Short", "strength": 85}
                
            return {"detected": False}
        except Exception:
            return {"detected": False}

    async def detect_box_breakout(self, symbol: str) -> dict:
        """
        V42.0: Detects breakouts from consolidation boxes.
        """
        try:
            klines = await okx_rest_service.get_klines(symbol=symbol, interval="60", limit=24)
            if not klines or len(klines) < 20: return {"detected": False}
            
            closes = [float(c[4]) for c in klines[::-1]]
            high_box = max(closes[-20:-1])
            low_box = min(closes[-20:-1])
            box_range_pct = (high_box - low_box) / low_box * 100
            
            current_price = closes[-1]
            if box_range_pct < 3.0: 
                if current_price > high_box:
                    return {"detected": True, "type": "BOX_EXIT_UP", "side": "Long", "range": box_range_pct}
                elif current_price < low_box:
                    return {"detected": True, "type": "BOX_EXIT_DOWN", "side": "Short", "range": box_range_pct}
            return {"detected": False}
        except Exception:
            return {"detected": False}

    async def get_btc_direction_filter(self) -> dict:
        """
        V27.0: BTC Directional Analysis (not just volatility).
        Uses EMA12 vs EMA26 (MACD-lite) on BTC 1H to determine clear direction.
        Returns: {'direction': 'UP'|'DOWN'|'NEUTRAL', 'strength': 0-100, 'aligned_with': 'Long'|'Short'|'Both'}
        """
        try:
            if (time.time() - self.btc_direction_cache.get('updated_at', 0)) < self.btc_direction_cache_ttl:
                return self.btc_direction_cache
            
            klines = await okx_rest_service.get_klines(symbol="BTCUSDT.P", interval="60", limit=30)
            
            if not klines or len(klines) < 26:
                return {'direction': 'NEUTRAL', 'strength': 0, 'aligned_with': 'Both', 'updated_at': time.time()}
            
            candles = klines[::-1]  # Chronological order
            closes = [float(c[4]) for c in candles]
            
            # EMA12
            mult_12 = 2 / (12 + 1)
            ema12 = sum(closes[:12]) / 12
            for price in closes[12:]:
                ema12 = (price - ema12) * mult_12 + ema12
            
            # EMA26
            mult_26 = 2 / (26 + 1)
            ema26 = sum(closes[:26]) / 26
            for price in closes[26:]:
                ema26 = (price - ema26) * mult_26 + ema26
            
            # MACD line (simplified)
            macd = ema12 - ema26
            macd_pct = (macd / ema26) * 100 if ema26 > 0 else 0
            
            # Also check last 6 candles momentum (are closes rising or falling?)
            recent = closes[-6:]
            momentum = (recent[-1] - recent[0]) / recent[0] * 100 if recent[0] > 0 else 0
            
            # Direction classification
            btc_var_15m = okx_ws_public_service.btc_variation_15m
            
            # [V110.36.10] FORCE DIRECTION FROM ADX REGIME
            m_adx = getattr(okx_ws_public_service, "btc_adx", 20.0)
            
            # Se o ADX  muito forte, no permitimos NEUTRAL se houver qualquer vis
            if m_adx >= 30:
                if macd_pct > 0.05 or btc_var_15m > 0:
                    direction = 'UP'
                    strength = 95
                    aligned_with = 'Long'
                elif macd_pct < -0.05 or btc_var_15m < 0:
                    direction = 'DOWN'
                    strength = 95
                    aligned_with = 'Short'
                else:
                    direction = 'ROARING-LATERAL' # Rare case: high volatility but no direction
                    strength = 95
                    aligned_with = 'Both'
            elif btc_var_15m < -0.4:
                direction = 'DOWN'
                strength = 90
                aligned_with = 'Short'
                # logger.info(f"🚨 [V42.0] FAST BTC DOWN DETECTED (15m: {btc_var_15m:.2f}%)")
            elif btc_var_15m > 0.4:
                direction = 'UP'
                strength = 90
                aligned_with = 'Long'
                logger.info(f"🚀 [V42.0] FAST BTC UP DETECTED (15m: {btc_var_15m:.2f}%)")
            elif macd_pct > 0.05 and momentum > 0.1:
                direction = 'UP'
                strength = min(100, int(abs(macd_pct) * 50 + abs(momentum) * 20))
                aligned_with = 'Long'
            elif macd_pct < -0.05 and momentum < -0.1:
                direction = 'DOWN'
                strength = min(100, int(abs(macd_pct) * 50 + abs(momentum) * 20))
                aligned_with = 'Short'
            else:
                direction = 'NEUTRAL'
                strength = 0
                aligned_with = 'Both'
            
            result = {
                'direction': direction,
                'strength': strength,
                'aligned_with': aligned_with,
                'macd_pct': round(macd_pct, 4),
                'momentum': round(momentum, 4),
                'btc_var_15m': round(btc_var_15m, 4),
                'updated_at': time.time()
            }
            
            self.btc_direction_cache = result
            
            # [V110.35.0] Sync BTC Direction with Oracle
            try:
                from services.agents.oracle_agent import oracle_agent
                if direction != 'NEUTRAL': # Don't sync neutral to prevent panic kills
                    await oracle_agent.update_market_data("signal_generator", {"btc_direction": direction})
            except Exception as e:
                logger.error(f"Error syncing BTC direction to Oracle: {e}")
                
            logger.info(f"📊 [V27.0] BTC Direction: {direction} | Strength: {strength} | MACD%: {macd_pct:.4f} | Var 15m: {btc_var_15m:.2f}%")
            return result
            
        except Exception as e:
            logger.warning(f"V27.0 BTC Direction Error: {e}")
            return {'direction': 'NEUTRAL', 'strength': 0, 'aligned_with': 'Both', 'updated_at': time.time()}

    async def detect_btc_decorrelation(self, symbol: str, alt_cvd: float = None, alt_ls_ratio: float = None, alt_oi: float = None) -> Any:
        try:
            from services.okx_ws_public import okx_ws_public_service
            from services.redis_service import redis_service
            
            # Fetch missing data if not provided
            if alt_cvd is None:
                alt_cvd = okx_ws_public_service.get_cvd_score(symbol)
            if alt_ls_ratio is None:
                alt_ls_ratio = await redis_service.get_ls_ratio(symbol)
            
            # 1. Pearson Correlation Check (Statistical Independence)
            correlation_data = {"is_decorrelated": False, "correlation": 1.0}
            try:
                # Fetch last 15 1h candles for both
                btc_klines = await okx_rest_service.get_klines(symbol="BTCUSDT.P", interval="60", limit=15)
                sym_klines = await okx_rest_service.get_klines(symbol=symbol, interval="60", limit=15)
                
                if btc_klines and sym_klines and len(btc_klines) >= 10 and len(sym_klines) >= 10:
                    btc_returns = []
                    for i in range(1, len(btc_klines)):
                        ret = (float(btc_klines[i][4]) - float(btc_klines[i-1][4])) / float(btc_klines[i-1][4])
                        btc_returns.append(ret)
                    sym_returns = []
                    for i in range(1, len(sym_klines)):
                        ret = (float(sym_klines[i][4]) - float(sym_klines[i-1][4])) / float(sym_klines[i-1][4])
                        sym_returns.append(ret)
                    
                    mean_btc = sum(btc_returns) / len(btc_returns)
                    mean_sym = sum(sym_returns) / len(sym_returns)
                    
                    # Normal Pearson (15h)
                    num = sum((b - mean_btc) * (s - mean_sym) for b, s in zip(btc_returns, sym_returns))
                    den = (sum((b - mean_btc)**2 for b in btc_returns) * sum((s - mean_sym)**2 for s in sym_returns))**0.5
                    correlation = num / den if den > 0 else 1.0

                    # Short-term Pearson (4h) - Last 4 entries of returns list
                    corr_short = 1.0
                    try:
                        b4, s4 = btc_returns[-4:], sym_returns[-4:]
                        m_b4, m_s4 = sum(b4)/4, sum(s4)/4
                        n4 = sum((b - m_b4) * (s - m_s4) for b, s in zip(b4, s4))
                        d4 = (sum((b - m_b4)**2 for b in b4) * sum((s - m_s4)**2 for s in s4))**0.5
                        corr_short = n4 / d4 if d4 > 0 else 1.0
                    except: pass
                    
                    correlation_data = {
                        "is_decorrelated": correlation < 0.45,
                        "correlation": round(correlation, 2),
                        "correlation_short": round(corr_short, 2)
                    }
            except Exception as e:
                logger.warning(f"Pearson calculation error for {symbol}: {e}")

            # 2. Captura estado do BTC
            btc_var = okx_ws_public_service.btc_variation_1h
            btc_cvd = okx_ws_public_service.get_cvd_score("BTCUSDT")
            abs_btc_var = abs(btc_var)
            abs_btc_cvd = abs(btc_cvd)
            
            # 3. Captura variação da altcoin
            alt_price = okx_ws_public_service.get_current_price(symbol)
            if alt_price <= 0:
                return {'is_decorrelated': False, 'confidence': 0.0, 'direction': 'Neutral', 'signals': [], 'reason': 'no_price', 'correlation': 1.0}
            
            klines = await okx_rest_service.get_klines(symbol=symbol, interval="60", limit=2)
            if not klines or len(klines) < 2:
                return {'is_decorrelated': False, 'confidence': 0.0, 'direction': 'Neutral', 'signals': [], 'reason': 'no_klines', 'correlation': 1.0}
            
            prev_close = float(klines[1][4])
            alt_var_1h = ((alt_price - prev_close) / prev_close) * 100 if prev_close > 0 else 0
            abs_alt_var = abs(alt_var_1h)
            
            # 4. Detectar modo de decorrelação
            # Relaxed BTC lateral condition (e.g., variation < 0.4%, no strict CVD lock)
            btc_is_lateral = abs_btc_var < 0.4 and abs_btc_cvd < 1500000
            btc_moving = abs_btc_var > 0.4
            directions_opposite = (btc_var > 0 and alt_var_1h < 0) or (btc_var < 0 and alt_var_1h > 0)
            is_anticorrelated = btc_moving and directions_opposite and abs_alt_var > 0.3
            
            decorrelation_mode = None
            if btc_is_lateral and abs_alt_var > 0.35:
                decorrelation_mode = "RANGING"
            elif is_anticorrelated:
                decorrelation_mode = "ANTICORRELATION"
            
            # [V57.0] Determination of active mode
            if not decorrelation_mode: 
                if correlation_data["is_decorrelated"]:
                    decorrelation_mode = "STATISTICAL"

            # 5. Ratio de decorrelação
            decorrelation_ratio = abs_alt_var / max(abs_btc_var, 0.01)
            
            # 6. [V46.0] Injeção de Liquidez & Smart Money
            oi_status = "STABLE"
            try:
                oi_history = await okx_rest_service.get_open_interest_history(symbol, interval="5min", limit=5)
                if len(oi_history) >= 2:
                    o1 = float(oi_history[0].get("openInterest", 0))
                    o2 = float(oi_history[1].get("openInterest", 0))
                    if o2 > 0:
                        oi_chg_pct = (o1 / o2 - 1) * 100
                        if oi_chg_pct > 0.05: oi_status = "RISING"
                        elif oi_chg_pct < -0.05: oi_status = "FALLING"
            except: pass

            # 7. Confiança e Sinais
            confidence = 0
            signals = [f"MODE:{decorrelation_mode}", f"OI:{oi_status}"]
            if correlation_data["is_decorrelated"]:
                confidence += 20
                signals.append(f"PEARSON({correlation_data['correlation']})")

            if decorrelation_mode == "ANTICORRELATION":
                confidence += 20
                signals.append(f"ANTI_BTC(alt:{alt_var_1h:+.2f}%,btc:{btc_var:+.2f}%)")
            elif decorrelation_mode == "RANGING":
                # If BTC is lateral but altcoin is moving hard, it is breaking out
                confidence += 20
                signals.append(f"RANGE_BREAK(alt:{abs_alt_var:.2f}%)")
            
            if alt_ls_ratio > 1.6 or alt_ls_ratio < 0.7:
                confidence += 30
                signals.append(f"LS_TRAP({alt_ls_ratio:.2f})")

            abs_alt_cvd = abs(alt_cvd)
            if abs_alt_cvd > 20000:
                confidence += 25
                signals.append(f"CVD_DIR({alt_cvd/1000:.0f}k)")

            if oi_status == "RISING":
                confidence += 15
                signals.append("SMART_ENTRY(OI+)")

            if decorrelation_ratio > 2.0:
                confidence += 25
                signals.append(f"RATIO({decorrelation_ratio:.1f})")
            elif decorrelation_ratio > 1.2:
                confidence += 15
                signals.append(f"RATIO({decorrelation_ratio:.1f})")
            
            is_decorrelated = correlation_data["is_decorrelated"] and confidence >= 45
            
            direction = "Long" if alt_cvd > 0 else "Short"
            if alt_ls_ratio > 1.5: direction = "Short"
            elif alt_ls_ratio < 0.8: direction = "Long"
            
            logger.info(f"🔍 [DECOR] {symbol}: PASS={is_decorrelated} CONF={confidence} MODE={decorrelation_mode} PEARSON={correlation_data['correlation']} RATIO={decorrelation_ratio:.2f} BTC_VAR={btc_var:.2f}% ALT_VAR={alt_var_1h:.2f}%")

            # [V57.0] Return Dictionary for full compatibility with tests and legacy
            reason = None
            if not is_decorrelated:
                if btc_moving: reason = "btc_not_lateral"
                else: reason = "not_decorrelated"

            return {
                'is_decorrelated': is_decorrelated,
                'confidence': float(confidence),
                'direction': direction,
                'signals': signals,
                'reason': reason,
                'correlation': correlation_data.get('correlation', 1.0),
                'pearson': correlation_data.get('correlation', 1.0), # Duplicate for UI/Radar compatibility
                'pearson_short': correlation_data.get('correlation_short', 1.0)
            }
        except Exception as e:
            logger.warning(f"[V46.0] Decorrelation error for {symbol}: {e}")
            return {'is_decorrelated': False, 'confidence': 0.0, 'direction': 'Neutral', 'signals': [], 'reason': 'error'}

    async def get_4h_trend_analysis(self, symbol: str) -> dict:
        """
        V12.0: Fetch 4H candles for macro trend filter.
        Returns: {'trend': 'bullish'|'bearish'|'sideways', 'ema20': float, 'current_price': float}
        """
        try:
            # Check cache first
            cached = self.trend_cache_4h.get(symbol)
            if cached and (time.time() - cached.get('updated_at', 0)) < self.trend_cache_4h_ttl:
                return cached
            
            klines = await okx_rest_service.get_klines(
                symbol=symbol,
                interval="240",  # 4H
                limit=24  # Last 4 days
            )
            
            if not klines or not isinstance(klines, list) or len(klines) == 0:
                return {'trend': 'sideways', 'ema20': 0, 'current_price': 0}
            
            candles = klines[::-1]  # Chronological order
            closes = [float(c[4]) for c in candles]
            
            if len(closes) < 20:
                return {'trend': 'sideways', 'ema20': 0, 'current_price': closes[-1] if closes else 0}
            
            # Calculate EMA20 (Exponential Moving Average)
            multiplier = 2 / (20 + 1)
            ema20 = sum(closes[:20]) / 20  # Initial SMA
            for price in closes[20:]:
                ema20 = (price - ema20) * multiplier + ema20
            
            current_price = closes[-1]
            pct_diff = ((current_price - ema20) / ema20) * 100
            
            if pct_diff > 0.5:
                trend = 'bullish'
            elif pct_diff < -0.5:
                trend = 'bearish'
            else:
                trend = 'sideways'
            
            result = {
                'trend': trend,
                'ema20': round(ema20, 8),
                'current_price': current_price,
                'pct_from_ema': round(pct_diff, 2),
                'updated_at': time.time()
            }
            
            self.trend_cache_4h[symbol] = result
            return result
            
        except Exception as e:
            logger.warning(f"V12.0 4H Trend Analysis Error for {symbol}: {e}")
            return {'trend': 'sideways', 'ema20': 0, 'current_price': 0}

    async def get_15m_zones(self, symbol: str) -> dict:
        """
        V12.0: Detect 15m support/resistance zones for proximity validation.
        Returns: {'support': float, 'resistance': float, 'distance_to_zone_pct': float, 'near_zone': bool}
        """
        try:
            # Check cache first
            cached = self.zones_cache_15m.get(symbol)
            if cached and (time.time() - cached.get('updated_at', 0)) < self.zones_cache_15m_ttl:
                return cached
            
            klines = await okx_rest_service.get_klines(
                symbol=symbol,
                interval="15",  # 15m
                limit=48  # Last 12 hours
            )
            
            if not klines or not isinstance(klines, list) or len(klines) == 0:
                return {'support': 0, 'resistance': 0, 'distance_to_zone_pct': 100, 'near_zone': False}
            
            candles = klines[::-1]
            highs = [float(c[2]) for c in candles]
            lows = [float(c[3]) for c in candles]
            closes = [float(c[4]) for c in candles]
            
            current_price = closes[-1]
            
            # Find support (recent swing lows)
            support = min(lows[-24:])  # Last 6 hours of 15m candles
            
            # Find resistance (recent swing highs)
            resistance = max(highs[-24:])
            
            # Calculate distance to nearest zone
            dist_to_support = abs(current_price - support) / current_price * 100
            dist_to_resistance = abs(current_price - resistance) / current_price * 100
            distance_to_zone = min(dist_to_support, dist_to_resistance)
            
            # Near zone if within 0.5% of S/R
            near_zone = distance_to_zone < 0.5
            
            result = {
                'support': round(support, 8),
                'resistance': round(resistance, 8),
                'current_price': current_price,
                'distance_to_zone_pct': round(distance_to_zone, 3),
                'near_zone': near_zone,
                'updated_at': time.time()
            }
            
            self.zones_cache_15m[symbol] = result
            return result
            
        except Exception as e:
            logger.warning(f"V12.0 15m Zones Error for {symbol}: {e}")
            return {'support': 0, 'resistance': 0, 'distance_to_zone_pct': 100, 'near_zone': False}

    async def get_2h_macro_analysis(self, symbol: str) -> dict:
        """
        V15.3: Shadow Sentinel Protocol - Fetch 120m (2H) candles for macro structure.
        Detects SMAs, Pivot levels, and calculates structural targets for dynamic TP.
        [V28.1] Master SMA Shield - Replaced SMA20 with SMA8 and SMA21 crossovers.
        """
        try:
            cached = self.trend_cache_2h.get(symbol)
            if cached and (time.time() - cached.get('updated_at', 0)) < self.trend_cache_2h_ttl:
                return cached
            
            klines = await okx_rest_service.get_klines(symbol=symbol, interval="120", limit=50)
            if not klines:
                return {'trend': 'sideways', 'pivot': 0, 'sma8': 0, 'sma21': 0}
                
            candles = klines[::-1]
            closes = [float(c[4]) for c in candles]
            highs = [float(c[2]) for c in candles]
            lows = [float(c[3]) for c in candles]
            
            # [V28.1] SMA 8 and SMA 21 Crossover System
            sma8 = sum(closes[-8:]) / 8 if len(closes) >= 8 else sum(closes) / len(closes)
            sma21 = sum(closes[-21:]) / 21 if len(closes) >= 21 else sum(closes) / len(closes)
            
            # Pivot Point (Recent structural support/resistance)
            pivot_low = min(lows[-12:]) # Last 24h
            pivot_high = max(highs[-12:])
            
            current_price = closes[-1]
            
            # [V28.1] Master Trend Identification
            if sma8 > sma21:
                trend = 'BULLISH_ARMED'
            elif sma8 < sma21:
                trend = 'BEARISH_ARMED'
            else:
                trend = 'NEUTRAL'
            
            # V15.3: ATR de 2H para cálculo do target estendido
            atr_values = []
            for i in range(1, len(closes)):
                tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
                atr_values.append(tr)
            atr_2h = sum(atr_values[-14:]) / min(14, len(atr_values)) if atr_values else 0
            
            # V15.3: Structural Targets
            # Conservative: próximo pivot (resistência para Long, suporte para Short)
            # Extended: pivot + 2×ATR_2H (busca 4-6% quando tendência forte)
            target_long = pivot_high  # Alvo para Longs
            target_short = pivot_low  # Alvo para Shorts
            target_long_ext = pivot_high + (2.0 * atr_2h)  # Alvo estendido Long
            target_short_ext = pivot_low - (2.0 * atr_2h)  # Alvo estendido Short
            
            # [V127] Calcular RSI 14 clássico com suavização de Wilder
            rsi_2h = 50.0
            if len(closes) > 14:
                gains = []
                losses = []
                for i in range(1, len(closes)):
                    diff = closes[i] - closes[i-1]
                    if diff > 0:
                        gains.append(diff)
                        losses.append(0.0)
                    else:
                        gains.append(0.0)
                        losses.append(-diff)
                
                # Média simples inicial
                avg_gain = sum(gains[:14]) / 14
                avg_loss = sum(losses[:14]) / 14
                
                # Suavização de Wilder
                for i in range(14, len(gains)):
                    avg_gain = (avg_gain * 13 + gains[i]) / 14
                    avg_loss = (avg_loss * 13 + losses[i]) / 14
                
                if avg_loss == 0:
                    rsi_2h = 100.0
                else:
                    rs = avg_gain / avg_loss
                    rsi_2h = round(100.0 - (100.0 / (1.0 + rs)), 2)

            result = {
                'trend': trend,
                'sma8': round(sma8, 8),
                'sma21': round(sma21, 8),
                'pivot_low': round(pivot_low, 8),
                'pivot_high': round(pivot_high, 8),
                'current_price': current_price,
                'atr_2h': round(atr_2h, 8),
                'target_long': round(target_long, 8),
                'target_short': round(target_short, 8),
                'target_long_ext': round(target_long_ext, 8),
                'target_short_ext': round(target_short_ext, 8),
                'rsi_2h': rsi_2h,
                'updated_at': time.time()
            }
            self.trend_cache_2h[symbol] = result
            return result
        except Exception as e:
            logger.error(f"Error in 2h macro analysis for {symbol}: {e}")
            return {'trend': 'sideways', 'pivot_low': 0, 'pivot_high': 0, 'sma8': 0, 'sma21': 0, 'atr_2h': 0, 'rsi_2h': 50.0}

    async def get_30m_tactical_analysis(self, symbol: str) -> dict:
        """
        [V40.2] HYBRID TACTICAL — 30min SMA8/SMA21 crossover for timing.
        The 2H tells us the MACRO direction. The 30min tells us WHEN to enter.
        Only when both align, we trigger is_swing_macro.
        Also measures "freshness" — how many candles since the crossover.
        """
        try:
            cached = self.trend_cache_30m.get(symbol)
            if cached and (time.time() - cached.get('updated_at', 0)) < self.trend_cache_30m_ttl:
                return cached

            klines = await okx_rest_service.get_klines(symbol=symbol, interval="30", limit=30)
            if not klines or len(klines) < 21:
                return {'trend': 'NEUTRAL', 'sma8': 0, 'sma21': 0, 'freshness': 0, 'slope': 0, 'updated_at': time.time()}

            candles = klines[::-1]  # Chronological order
            closes = [float(c[4]) for c in candles]

            # SMA 8 and SMA 21 on 30min
            sma8 = sum(closes[-8:]) / 8
            sma21 = sum(closes[-21:]) / 21
            current_price = closes[-1]

            # Trend from crossover
            if sma8 > sma21:
                trend = 'BULLISH_TACTICAL'
            elif sma8 < sma21:
                trend = 'BEARISH_TACTICAL'
            else:
                trend = 'NEUTRAL'

            # Freshness: how many recent candles have the same crossover direction?
            # This tells us if the crossover JUST happened (fresh) or happened long ago (stale)
            freshness = 0
            if len(closes) >= 21:
                for lookback in range(1, min(10, len(closes) - 20)):
                    idx = -lookback
                    sma8_lb = sum(closes[idx-8:idx]) / 8 if abs(idx) + 8 <= len(closes) else 0
                    sma21_lb = sum(closes[idx-21:idx]) / 21 if abs(idx) + 21 <= len(closes) else 0
                    if sma8_lb == 0 or sma21_lb == 0:
                        break
                    same_direction = (sma8_lb > sma21_lb and trend == 'BULLISH_TACTICAL') or \
                                     (sma8_lb < sma21_lb and trend == 'BEARISH_TACTICAL')
                    if same_direction:
                        freshness += 1
                    else:
                        break

            # Slope of SMA8 (acceleration) — positive = accelerating up
            if len(closes) >= 10:
                sma8_prev = sum(closes[-10:-2]) / 8
                slope = ((sma8 - sma8_prev) / sma8_prev * 100) if sma8_prev > 0 else 0
            else:
                slope = 0

            # Distance from SMA: is price near or stretched?
            dist_from_sma8 = ((current_price - sma8) / sma8 * 100) if sma8 > 0 else 0

            result = {
                'trend': trend,
                'sma8': round(sma8, 8),
                'sma21': round(sma21, 8),
                'freshness': freshness,  # 0-1 = fresh crossover (ideal), >5 = stale
                'slope': round(slope, 4),
                'dist_from_sma8': round(dist_from_sma8, 4),
                'current_price': current_price,
                'updated_at': time.time()
            }
            self.trend_cache_30m[symbol] = result
            return result

        except Exception as e:
            logger.warning(f"[V40.2] 30m Tactical Error for {symbol}: {e}")
            return {'trend': 'NEUTRAL', 'sma8': 0, 'sma21': 0, 'freshness': 0, 'slope': 0, 'updated_at': time.time()}

    async def get_fibonacci_levels(self, symbol: str, interval: str = "60", limit: int = 48) -> dict:
        """
        [V7.0] THE PERFECT ENTRY: Precision Fibonacci Retracement.
        Identifies the current 'Swing' (High and Low) and calculates retracement levels.
        Intervals: '60' (1h) for Macro, '15' for Tactical.
        """
        try:
            klines = await okx_rest_service.get_klines(symbol=symbol, interval=interval, limit=limit)
            if not klines or len(klines) < 10:
                return {}

            # Klines chronological order: [oldest, ..., newest]
            candles = klines[::-1]
            highs = [float(c[2]) for c in candles]
            lows = [float(c[3]) for c in candles]
            closes = [float(c[4]) for c in candles]

            current_price = closes[-1]
            swing_high = max(highs)
            swing_low = min(lows)
            diff = swing_high - swing_low

            if diff == 0:
                return {}

            # Determine direction of the swing to identify if we are in a pullback
            # If the high happened before the low, the main move is DOWN (we want to sell the rally)
            # If the low happened before the high, the main move is UP (we want to buy the dip)
            high_idx = highs.index(swing_high)
            low_idx = lows.index(swing_low)
            move_direction = "UP" if low_idx < high_idx else "DOWN"

            levels = {}
            if move_direction == "UP":
                # Retracement levels for a Bullish Move (Pullback to the downside)
                levels['0.0'] = swing_high
                levels['0.236'] = swing_high - (diff * 0.236)
                levels['0.382'] = swing_high - (diff * 0.382)
                levels['0.5'] = swing_high - (diff * 0.5)
                levels['0.618'] = swing_high - (diff * 0.618)
                levels['0.786'] = swing_high - (diff * 0.786)
                levels['1.0'] = swing_low
            else:
                # Retracement levels for a Bearish Move (Pullback to the upside)
                levels['0.0'] = swing_low
                levels['0.236'] = swing_low + (diff * 0.236)
                levels['0.382'] = swing_low + (diff * 0.382)
                levels['0.5'] = swing_low + (diff * 0.5)
                levels['0.618'] = swing_low + (diff * 0.618)
                levels['0.786'] = swing_low + (diff * 0.786)
                levels['1.0'] = swing_high

            return {
                'symbol': symbol,
                'direction': move_direction,
                'levels': levels,
                'golden_zone': (levels['0.5'], levels['0.618']),
                'current_price': current_price,
                'swing_high': swing_high,
                'swing_low': swing_low,
                'updated_at': time.time()
            }
        except Exception as e:
            logger.error(f"Error calculating Fibonacci for {symbol}: {e}")
            return {}

    async def get_fib_extension_levels(self, symbol: str, entry_price: float, side: str, interval: str = "240", limit: int = 60) -> dict:
        """
        [V110.118] Fibonacci EXTENSION levels for Harvester targeting.
        
        Calcula ONDE a pernada atual tende a terminar (resistência), usando o swing
        antes da entrada como âncora. Diferente de get_fibonacci_levels() que retorna
        suportes de retração — este retorna alvos de extensão ACIMA da entrada (para LONG).
        
        Metodologia:
        - Encontra o swing LOW mais significativo do H4 antes da entrada (para LONG)
        - diff = entry_price - swing_low  ← tamanho da pernada anterior
        - Projeta extensões acima da entrada:
            * 1.0x  = entry + diff * 1.0  → típica pernada de 5-6% (Measured Move)
            * 1.272 = entry + diff * 1.272 → pernada forte 7-8%
            * 1.414 = entry + diff * 1.414 → extensão dourada média
            * 1.618 = entry + diff * 1.618 → Golden Extension, onde moves extremos terminam
        
        Args:
            symbol: Par de trading
            entry_price: Preço de entrada da ordem/Moonbag
            side: 'Buy' (Long) ou 'Sell' (Short)
            interval: Timeframe H4 = '240'
            limit: Quantidade de velas para analisar
        """
        try:
            klines = await okx_rest_service.get_klines(symbol=symbol, interval=interval, limit=limit)
            if not klines or len(klines) < 10:
                return {}

            candles = klines[::-1]  # Ordem cronológica: [oldest → newest]
            highs = [float(c[2]) for c in candles]
            lows  = [float(c[3]) for c in candles]

            side_norm = (side or "Buy").upper()
            extensions = {}
            diff = 0.0

            if side_norm == "BUY":
                # LONG: âncora no swing LOW do H4. A pernada foi de lá até aqui.
                # Apenas considera lows ABAIXO da entrada (lows acima são de outra pernada)
                valid_lows = [l for l in lows if l < entry_price]
                if not valid_lows:
                    return {}
                swing_low = min(valid_lows)
                diff = entry_price - swing_low
                if diff <= 0 or (diff / entry_price) < 0.005:  # Diff mínimo de 0.5%
                    return {}
                # Projeto as extensões ACIMA da entrada
                extensions = {
                    "1.0_ext":   round(entry_price + diff * 1.0,   8),  # Measured Move (~5-6%)
                    "1.272_ext": round(entry_price + diff * 1.272, 8),  # Forte (~7-8%)
                    "1.414_ext": round(entry_price + diff * 1.414, 8),  # Semi-Dourado (~8-9%)
                    "1.618_ext": round(entry_price + diff * 1.618, 8),  # Golden (~10%+)
                }
            else:  # SELL / SHORT
                # SHORT: âncora no swing HIGH do H4
                valid_highs = [h for h in highs if h > entry_price]
                if not valid_highs:
                    return {}
                swing_high = max(valid_highs)
                diff = swing_high - entry_price
                if diff <= 0 or (diff / entry_price) < 0.005:
                    return {}
                # Projeta as extensões ABAIXO da entrada (queda)
                extensions = {
                    "1.0_ext":   round(entry_price - diff * 1.0,   8),
                    "1.272_ext": round(entry_price - diff * 1.272, 8),
                    "1.414_ext": round(entry_price - diff * 1.414, 8),
                    "1.618_ext": round(entry_price - diff * 1.618, 8),
                }

            # Calcular o ROI teórico de cada nível (para logging e UI)
            ext_roi = {}
            leverage = 50
            for label, price in extensions.items():
                if side_norm == "BUY":
                    move_pct = (price - entry_price) / entry_price
                else:
                    move_pct = (entry_price - price) / entry_price
                ext_roi[label] = round(move_pct * leverage * 100, 1)

            return {
                "symbol": symbol,
                "side": side_norm,
                "entry_price": entry_price,
                "swing_anchor": swing_low if side_norm == "BUY" else swing_high,
                "leg_size_pct": round((diff / entry_price) * 100, 2),
                "extensions": extensions,
                "extensions_roi": ext_roi,  # Ex: {"1.0_ext": 280.0, "1.618_ext": 453.0}
                "updated_at": time.time()
            }
        except Exception as e:
            logger.error(f"Error calculating Fibonacci extensions for {symbol}: {e}")
            return {}

    async def get_orderbook_walls(self, symbol: str) -> dict:
        """
        [V7.0] THE PERFECT ENTRY: Liquidity Wall Detection.
        Identifies significant buy/sell walls nearby to avoid entering into a wall.
        """
        try:
            ob = await okx_rest_service.get_orderbook(symbol, limit=50)
            if not ob:
                return {'buy_walls': [], 'sell_walls': [], 'obi': 0}

            bids = [[float(p), float(q)] for p, q in ob.get('b', [])]
            asks = [[float(p), float(q)] for p, q in ob.get('a', [])]
            
            if not bids or not asks:
                return {'buy_walls': [], 'sell_walls': [], 'obi': 0}

            # OBI calculation: (Total Bids - Total Asks) / (Total Bids + Total Asks)
            total_bids = sum(q for p, q in bids)
            total_asks = sum(q for p, q in asks)
            obi = (total_bids - total_asks) / (total_bids + total_asks) if (total_bids + total_asks) > 0 else 0

            # Wall Detection: Any level with > 4x the average volume of the book
            avg_bid_vol = total_bids / len(bids)
            avg_ask_vol = total_asks / len(asks)
            
            buy_walls = [p for p, q in bids if q > avg_bid_vol * 4]
            sell_walls = [p for p, q in asks if q > avg_ask_vol * 4]
            
            return {
                'buy_walls': buy_walls[:3],
                'sell_walls': sell_walls[:3],
                'obi': round(obi, 3),
                'top_bid': bids[0][0],
                'top_ask': asks[0][0]
            }
        except Exception as e:
            logger.error(f"Error analyzing orderbook walls for {symbol}: {e}")
            return {'buy_walls': [], 'sell_walls': [], 'obi': 0}

    async def is_price_stretched(self, symbol: str, current_price: float) -> tuple:
        """
        [V15.1] Shadow Sentinel - Adaptive ATR: Detecta se o preço está em uma "agulhada".
        Garante que não entamos contra um movimento parabólico sem esperar a exaustão.
        """
        try:
            # 1. Fetch 1m candles for velocity check
            klines = await okx_rest_service.get_klines(symbol=symbol, interval="1", limit=10)
            if not klines or len(klines) < 5:
                return False, 0.0

            # Klines order: [newest, ..., oldest]
            closes = [float(k[4]) for k in klines]
            price_5m_ago = closes[min(5, len(closes)-1)]
            
            # Stretch = % de variação nos últimos 5 minutos
            stretch_pct = abs(current_price - price_5m_ago) / price_5m_ago * 100
            
            # [V15.1] Dynamic Threshold based on ATR
            atr = okx_ws_public_service.atr_cache.get(symbol, 0)
            if atr > 0 and current_price > 0:
                # O gatilho é 1.5x a volatilidade média (ATR de 1h)
                atr_pct = (atr / current_price) * 100
                dynamic_threshold = max(0.5, min(1.5, atr_pct * 1.5))
            else:
                dynamic_threshold = 0.8 # Fallback

            is_spike = stretch_pct > dynamic_threshold
            return is_spike, stretch_pct
        except Exception as e:
            logger.error(f"Error checking stretch for {symbol}: {e}")
            return False, 0.0

    async def get_1m_scalp_analysis(self, symbol: str) -> dict:
        """
        [V19.0] SCALP PRECISION PROTOCOL: Fetch 1m candles for extreme RSI + CVD exhaustion.
        Returns: {'scalp_valid': bool, 'rsi_1m': float, 'cvd_condition': str}
        """
        try:
            klines = await okx_rest_service.get_klines(symbol=symbol, interval="1", limit=15)
            if not klines or len(klines) < 15:
                return {'scalp_valid': False, 'rsi_1m': 50, 'cvd_condition': 'unknown'}
                
            closes = [float(k[4]) for k in klines]
            
            # [V20.4] Wilder's Smoothing RSI (matches TradingView/institutional standard)
            gains = []
            losses = []
            for i in range(1, len(closes)):
                diff = closes[i] - closes[i-1]
                if diff >= 0:
                    gains.append(diff)
                    losses.append(0)
                else:
                    gains.append(0)
                    losses.append(abs(diff))
                    
            if not gains or len(gains) < 2:
                rsi = 50
            else:
                # Wilder's EMA: first value is SMA, then smooth
                avg_gain = gains[0]
                avg_loss = losses[0]
                for i in range(1, len(gains)):
                    avg_gain = (avg_gain * 13 + gains[i]) / 14
                    avg_loss = (avg_loss * 13 + losses[i]) / 14
                
                if avg_loss == 0:
                    rsi = 100
                else:
                    rs = avg_gain / avg_loss
                    rsi = 100 - (100 / (1 + rs))
                
            # Check real-time CVD for exhaustion
            cvd = okx_ws_public_service.get_cvd_score(symbol)
            cvd_condition = 'neutral'
            if cvd > 100000: cvd_condition = 'exhausted_buy'
            elif cvd < -100000: cvd_condition = 'exhausted_sell'
                
            # Validation: Extreme RSI + Extreme CVD
            scalp_valid = False
            if rsi < 25 and cvd_condition == 'exhausted_sell': 
                scalp_valid = True # Peak oversold, ready to bounce Long
            elif rsi > 75 and cvd_condition == 'exhausted_buy':
                scalp_valid = True # Peak overbought, ready to fade Short
                
            return {
                'scalp_valid': scalp_valid,
                'rsi_1m': round(rsi, 2),
                'cvd_condition': cvd_condition
            }
        except Exception as e:
            logger.warning(f"1m Scalp Analysis Error for {symbol}: {e}")
            return {'scalp_valid': False, 'rsi_1m': 50, 'cvd_condition': 'unknown'}

    async def detect_micro_mss(self, symbol: str, side: str) -> dict:
        """
        [V68.0] MARKET STRUCTURE SHIFT (MSS) - 1m Confirmation.
        Verifies if price has broken the previous candle's extreme to confirm a shift.
        Logic:
        - Long: Current Close > Previous High
        - Short: Current Close < Previous Low
        """
        try:
            klines = await okx_rest_service.get_klines(symbol=symbol, interval="1", limit=3)
            if not klines or len(klines) < 2:
                return {'confirmed': False, 'reason': 'insufficient_data'}
            
            # klines: [newest, ..., oldest]
            current_close = float(klines[0][4])
            prev_open = float(klines[1][1])
            prev_close = float(klines[1][4])
            prev_body_high = max(prev_open, prev_close)
            prev_body_low = min(prev_open, prev_close)
            
            side_norm = side.lower()
            if side_norm == "buy" or side_norm == "long":
                confirmed = current_close > prev_body_high
                reason = "MSS_BOS_UP" if confirmed else "WAITING_FOR_BOS_UP"
                target_level = prev_body_high
            else:
                confirmed = current_close < prev_body_low
                reason = "MSS_BOS_DOWN" if confirmed else "WAITING_FOR_BOS_DOWN"
                target_level = prev_body_low
                
            return {
                'confirmed': confirmed,
                'reason': reason,
                'current_close': current_close,
                'target_level': target_level
            }
        except Exception as e:
            logger.error(f"Error in detect_micro_mss for {symbol}: {e}")
            return {'confirmed': False, 'reason': f'error: {e}'}

    async def get_1h_trend_analysis(self, symbol: str) -> dict:
        """
        V9.0: Fetch 1H candles and analyze trend + patterns.
        Returns: {'trend': 'bullish'|'bearish'|'sideways', 'pattern': str, 'trend_strength': 0-100}
        """
        try:
            # Check cache first
            cached = self.trend_cache.get(symbol)
            if cached and (time.time() - cached.get('updated_at', 0)) < self.trend_cache_ttl:
                return cached
            
            klines = await okx_rest_service.get_klines(
                symbol=symbol,
                interval="60",  # 1H
                limit=24  # Last 24 hours
            )
            
            if not klines or not isinstance(klines, list) or len(klines) == 0:
                return {'trend': 'sideways', 'pattern': 'unknown', 'trend_strength': 0}
            
            candles = klines
            # Bybit returns newest first, so reverse for chronological order
            candles = candles[::-1]
            
            # Extract close prices
            closes = [float(c[4]) for c in candles]
            highs = [float(c[2]) for c in candles]
            lows = [float(c[3]) for c in candles]
            
            if len(closes) < 10:
                return {'trend': 'sideways', 'pattern': 'unknown', 'trend_strength': 0}
            
            # Calculate trend using SMA20 vs current price
            sma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else sum(closes) / len(closes)
            current = closes[-1]
            
            # Calculate ATR for volatility context
            atr_values = []
            for i in range(1, len(closes)):
                tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
                atr_values.append(tr)
            atr = sum(atr_values[-14:]) / min(14, len(atr_values)) if atr_values else 0
            
            # Trend determination
            pct_diff = ((current - sma20) / sma20) * 100
            
            if pct_diff > 0.5:
                trend = 'bullish'
            elif pct_diff < -0.5:
                trend = 'bearish'
            else:
                trend = 'sideways'
            
            trend_strength = min(100, abs(pct_diff) * 20)
            
            # Pattern Detection
            pattern = 'none'
            
            # 1. Pullback Detection: Price retraced but bounced from SMA/support
            recent_low = min(lows[-5:])
            recent_high = max(highs[-5:])
            if trend == 'bullish' and current > sma20 and recent_low < sma20:
                pattern = 'pullback_bounce'
            elif trend == 'bearish' and current < sma20 and recent_high > sma20:
                pattern = 'pullback_rejection'
            
            # 2. Liquidity Sweep & Reclaim: SWING TRAP PROTECTION [V19.0]
            # Requires price to sweep liquidity (break below/above previous low/high)
            # AND the current close MUST reclaim the broken level.
            if len(closes) >= 10:
                prev_low = min(lows[-10:-5])
                prev_high = max(highs[-10:-5])
                curr_low = min(lows[-3:])
                curr_high = max(highs[-3:])
                
                # [V68.0] Institutional Liquidity Sweep & Reclaim
                # Requires price to sweep liquidity (break below/above previous low/high)
                # AND show rejection (pavio/wick) + current close must reclaim.
                is_long_sweep = False
                is_short_sweep = False
                
                if curr_low < prev_low:
                    # Check anatomy of the lowest candle in the sweep zone
                    # (Simple approximation: if curr_low is much lower than close, it's a wick)
                    sweep_wick_size = min(closes[-3:]) - curr_low
                    total_candle_size = max(highs[-3:]) - curr_low
                    wick_ratio = sweep_wick_size / total_candle_size if total_candle_size > 0 else 0
                    
                    if current > prev_low and closes[-2] > prev_low and wick_ratio > 0.15:
                        is_long_sweep = True
                        
                elif curr_high > prev_high:
                    sweep_wick_size = curr_high - max(closes[-3:])
                    total_candle_size = curr_high - min(lows[-3:])
                    wick_ratio = sweep_wick_size / total_candle_size if total_candle_size > 0 else 0
                    
                    if current < prev_high and closes[-2] < prev_high and wick_ratio > 0.15:
                        is_short_sweep = True

                if is_long_sweep:
                    pattern = 'sweep_and_reclaim_long'
                elif is_short_sweep:
                    pattern = 'sweep_and_reclaim_short'
            # 4. Accumulation Box Detection (Consolidation)
            # Find periods where price is range-bound in the last 24h
            accumulation_boxes = []
            box_min_candles = 10
            for i in range(len(highs) - box_min_candles):
                window_highs = highs[i:i+box_min_candles]
                window_lows = lows[i:i+box_min_candles]
                window_range = max(window_highs) - min(window_lows)
                # If range is tight (< 0.5% of price), mark as accumulation
                if window_range < closes[i] * 0.005:
                    accumulation_boxes.append({
                        'top': max(window_highs),
                        'bottom': min(window_lows),
                    })
            
            # Detect Box Exit
            if accumulation_boxes:
                last_box = accumulation_boxes[-1]
                if current > last_box['top'] and closes[-2] <= last_box['top']:
                    pattern = 'accumulation_box_exit_up'
                elif current < last_box['bottom'] and closes[-2] >= last_box['bottom']:
                    pattern = 'accumulation_box_exit_down'
            
            # 5. Liquidity Zones (1H Highs/Lows)
            # Identify key support/resistance levels from recent peaks/troughs
            liquidity_zones = []
            max_24h = max(highs)
            min_24h = min(lows)
            
            # Simple version: the absolute 24h extreme values are the strongest liquidity zones
            liquidity_zones.append({'price': max_24h, 'type': 'high'})
            liquidity_zones.append({'price': min_24h, 'type': 'low'})
            
            # Add secondary zones (e.g., first 12h extremes if different)
            if len(highs) >= 24:
                max_12h = max(highs[:12])
                min_12h = min(lows[:12])
                if abs(max_12h - max_24h) / max_24h > 0.002: # 0.2% difference
                    liquidity_zones.append({'price': max_12h, 'type': 'high_secondary'})
                if abs(min_12h - min_24h) / min_24h > 0.002:
                    liquidity_zones.append({'price': min_12h, 'type': 'low_secondary'})

            # [V44.2] ADX Slope (Acceleration) Integration
            # We fetch ADX from the regime cache (calculated in detect_market_regime)
            regime_data = self.market_regime_cache.get(symbol, {})
            adx_val = regime_data.get('adx', 0)
            adx_prev = regime_data.get('adx_prev', 0)
            adx_slope = adx_val - adx_prev if adx_prev > 0 else 0

            result = {
                'trend': trend,
                'pattern': pattern,
                'trend_strength': round(trend_strength, 1),
                'atr': round(atr, 6),
                'sma20': round(sma20, 6),
                'accumulation_boxes': accumulation_boxes[-2:], # Return last 2 detected boxes
                'liquidity_zones': liquidity_zones,
                'adx_val': round(adx_val, 2),
                'adx_slope': round(adx_slope, 2),
                'updated_at': time.time()
            }
            
            # Update cache
            self.trend_cache[symbol] = result
            return result
            
        except Exception as e:
            logger.warning(f"V9.0 Trend Analysis Error for {symbol}: {e}")
            return {'trend': 'sideways', 'pattern': 'unknown', 'trend_strength': 0}


    async def calculate_rest_cvd(self, symbol: str) -> float:
        """
        [V16.0] REST Proxy CVD calculation.
        Simulates CVD score by fetching recent trade history via HTTP.
        """
        try:
            # [V20.4] Increased from 80 to 200 for more accurate CVD calculation
            trades = await okx_rest_service.get_public_trade_history(symbol, limit=200)
            if not trades: return 0.0
            
            rest_cvd = 0.0
            for t in trades:
                side = t.get("side", "Buy")
                size = float(t.get("size", 0))
                price = float(t.get("price", 0))
                delta = (size * price) if side == "Buy" else -(size * price)
                rest_cvd += delta
            
            return rest_cvd
        except Exception as e:
            logger.warning(f"Failed to calculate REST CVD for {symbol}: {e}")
            return 0.0

    async def _get_fleet_confluence_score(self, symbol: str) -> dict:
        """
        [V27.2] Fleet Intelligence simplified — agents removed.
        Returns neutral defaults (previously agents always returned defaults anyway).
        """
        return {
            "score": 0,
            "macro_risk": 5,
            "sentiment": 50,
            "whale_bias": "NEUTRAL",
            "all_defaults": True
        }

    async def _macro_sync_loop(self):
        """
        [V38.0] Background loop to keep 2H SMA state updated for all symbols without slowing down the radar.
        Runs every 15 minutes to cache the macro trend.
        """
        logger.info("🪐 [MACRO SYNC] Iniciando sincronização em background do Gráfico de 2H...")
        while self.is_running:
            try:
                symbols = getattr(okx_ws_public_service, 'active_symbols', [])
                if not symbols:
                    await asyncio.sleep(10)
                    continue
                    
                for symbol in symbols:
                    await self.get_2h_macro_analysis(symbol)
                    await asyncio.sleep(0.5) # Spread API calls (~40s total)
                
                logger.debug("✅ [MACRO SYNC] Estados da SMA de 2H atualizados.")
                await asyncio.sleep(900) # 15 minutes
            except Exception as e:
                logger.error(f"Error in macro sync loop: {e}")
                await asyncio.sleep(60)

    async def _30m_sync_loop(self):
        """
        [V40.2] Background loop to keep 30min SMA state updated.
        Runs every 5 minutes (30min candles change faster than 2H).
        """
        logger.info("⏱️ [30M SYNC] Iniciando sincronização em background do Gráfico de 30min...")
        while self.is_running:
            try:
                symbols = getattr(okx_ws_public_service, 'active_symbols', [])
                if not symbols:
                    await asyncio.sleep(10)
                    continue

                for symbol in symbols:
                    await self.get_30m_tactical_analysis(symbol)
                    await asyncio.sleep(0.3)  # Spread API calls

                logger.debug("✅ [30M SYNC] Cache de 30min atualizado.")
                await asyncio.sleep(300)  # 5 minutes
            except Exception as e:
                logger.error(f"Error in 30m sync loop: {e}")
                await asyncio.sleep(60)

    async def monitor_and_generate(self):
        """
        [V14.0] FUNIL INTELIGENTE DE SINAIS — 3-Stage Smart Funnel.
        Mantém todos os ~85 pares mas aplica filtros progressivos para minimizar chamadas API.
        [V16.0] Added REST Fallback for low-latency/WS-blocked environments.
        """
        self.is_running = True
        logger.info("🎯 [V15.1] Funil Inteligente de Sinais ONLINE. Tactical + Elite Stages.")
        
        # [V38.0] Start the background 2H macro sync loop
        asyncio.create_task(self._macro_sync_loop())
        # [V40.2] Start the background 30min tactical sync loop
        asyncio.create_task(self._30m_sync_loop())

        # V12.0: Define local helper for Stage 2
        async def stage2_analyze(candidate):
            """Stage 2: Tactical Analysis (1H Trend + Patterns + 1m Scalp Precision)"""
            try:
                symbol = candidate['symbol']
                side_label = candidate['side_label']
                
                # Determine intended trade type (Scalp vs Swing) based on slot availability
                # We query VaultService indirectly. For Stage 2, we assume SCALP if ROI targets are low.
                # A simpler approach for the generator is checking if we just want a quick entry.
                # Let's run both and let Stage 3 decide, but we must provide the data.
                
                trend_1h = await self.get_1h_trend_analysis(symbol)
                scalp_1m = await self.get_1m_scalp_analysis(symbol)
                
                trend = trend_1h.get('trend', 'sideways')
                pattern = trend_1h.get('pattern', 'none')
                
                # 1. SCALP PRECISION (V19.0)
                scalp_valid = scalp_1m.get('scalp_valid', False)
                scalp_bonus = 30 if scalp_valid else 0
                
                # 2. TRAP EXPLOITATION & PULLBACK VALIDATION (V28.3)
                trend_bonus = 0
                pattern_bonus = 0
                trap_exploited = False
                pullback_sniped = False
                
                # Align Trend
                if (side_label == "Long" and trend == "bullish") or (side_label == "Short" and trend == "bearish"):
                    trend_bonus = 15
                elif trend == "sideways":
                    trend_bonus = 0
                else:
                    trend_bonus = -20 # Strong counter-trend
                
                # [V33.1] Decorrelation has PRIORITY over Trap Pivot — direction already set by Hunter
                is_dec = candidate.get('is_decorrelated', False)
                
                # [V86.2] HYBRID PIVOT: Permitir inversao de direcao mesmo em Decorrelated
                # Antes o is_dec travava a direcao (locked), agora ele apenas soma bonus e permite o Pivot.
                if is_dec:
                    pattern_bonus += 25  
                    logger.debug(f"🎯 [V86.2] {symbol} Decorrelation active. Pattern bonus applied.")

                if side_label == "Long" and pattern == 'sweep_and_reclaim_short':
                    # Varejo comprando topo, mas gráfico mostra Sweep/Rejection de topo (Bull Trap)
                    side_label = "Short"
                    pattern_bonus += 60  
                    trap_exploited = True
                    trend_bonus = 15 if trend == "bearish" else 0 
                    logger.info(f"🦇 [TRAP EXPLOITATION V86.2] {symbol} Varejo em Long (Bull Trap detectado). Bot virou canhão para SHORT!")
                    
                elif side_label == "Short" and pattern == 'sweep_and_reclaim_long':
                    # Varejo vendendo fundo, mas gráfico mostra Sweep de fundo (Bear Trap)
                    side_label = "Long"
                    pattern_bonus += 60  
                    trap_exploited = True
                    trend_bonus = 15 if trend == "bullish" else 0
                    logger.info(f"🦇 [TRAP EXPLOITATION V86.2] {symbol} Varejo em Short (Bear Trap detectado). Bot virou canhão para LONG!")
                    
                # Pullback Sniper Logic
                elif (side_label == "Long" and pattern == 'pullback_bounce') or \
                     (side_label == "Short" and pattern == 'pullback_rejection'):
                    pattern_bonus = 35  # Entrada limpa a favor da tendência
                    pullback_sniped = True
                    logger.info(f"🎯 [PULLBACK SNIPER] {symbol} Pegando recuo limpo em EMA a favor do {side_label}")
                    
                # Standard Patterns (Confluence)
                elif pattern in ['sweep_and_reclaim_long', 'sweep_and_reclaim_short']:
                    # Se coincidir de já estar no lado certo do sweep
                    pattern_bonus = 30
                elif pattern in self.valid_entry_patterns:
                    pattern_bonus = 10
                elif pattern in ['none', 'unknown']:
                    pattern_bonus = -15 # [V31.0] Relaxed from -30 to allow more signals through
                
                # Final Tactical Score
                tactical_score = candidate['preliminary_score'] + trend_bonus + pattern_bonus + scalp_bonus
                if candidate.get('is_swing_macro'):
                    tactical_score += 40  # Massive priority bump for Macro Swing
                
                candidate.update({
                    'tactical_score': round(tactical_score, 1),
                    'trend': trend,
                    'pattern': pattern,
                    'scalp_valid': scalp_valid,
                    'rsi_1m': scalp_1m.get('rsi_1m', 50),
                    'side_label': side_label, # Pode ter sido invertido pelo Trap Pivot
                    'trap_exploited': trap_exploited,
                    'pullback_sniped': pullback_sniped
                })
                
                # V12.3: Funnel filter (only top tactical candidates move to Stage 3)
                is_swing_macro = candidate.get('is_swing_macro', False)
                if symbol.replace('.P', '') in ['SPXUSDT', 'JASMYUSDT', 'TIAUSDT']: logger.info(f"🔎 [TRACE] {symbol} end Stage 2. tactical={tactical_score}, is_swing={is_swing_macro}")
                
                if tactical_score < 30 and not is_swing_macro:
                    if symbol.replace('.P', '') in ['SPXUSDT', 'JASMYUSDT', 'TIAUSDT']: logger.info(f"🔎 [TRACE] {symbol} dropped Stage 2: tactical={tactical_score} < 30")
                    return None
                    
                return candidate
            except Exception as e:
                logger.error(f"Error in stage2_analyze for {candidate.get('symbol')}: {e}")
                return None

        while self.is_running:
            try:
                from services.sentinel_auditor import sentinel_auditor
                sentinel_auditor.record_heartbeat("signal_generator")

                # [V38.1] PRE-WARM 2H CACHE — Once on startup before first Stage 1 runs
                if not hasattr(self, '_2h_warmup_done'):
                    self._2h_warmup_done = True
                    warmup_symbols = await okx_rest_service.get_elite_50x_pairs()
                    logger.info(f"🔥 [MACRO WARMUP] Pré-aquecendo cache 2H + 30min para {len(warmup_symbols)} pares...")
                    async def warmup_worker(wsym):
                        try:
                            await asyncio.gather(
                                self.get_2h_macro_analysis(wsym),
                                self.get_30m_tactical_analysis(wsym)
                            )
                        except: pass
                    
                    # Use a semaphore to avoid overwhelming the API during warmup
                    w_semaphore = asyncio.Semaphore(15)
                    async def sem_warmup(s):
                        async with w_semaphore: await warmup_worker(s)
                        
                    await asyncio.gather(*(sem_warmup(wsym) for wsym in warmup_symbols))
                    logger.info("✅ [MACRO WARMUP] Cache 2H + 30min pronto em paralelo! Iniciando varredura...")

                # ... (rest of the loop initialization code)
                # 0. V5.1.0: Update Market Context (BTC Variation, ATR, etc.)
                now = time.time()
                if now - self.last_context_update > 15:
                    # [V16.3.1] Run in background to prevent funnel deadlock
                    asyncio.create_task(okx_ws_public_service.update_market_context())
                    self.last_context_update = now
                    
                    # Update Drag Mode State
                    btc_var = okx_ws_public_service.btc_variation_1h
                    btc_cvd = okx_ws_public_service.get_cvd_score("BTCUSDT")
                    btc_price = okx_ws_public_service.get_current_price("BTCUSDT")
                    
                    abs_btc_cvd = abs(btc_cvd)
                    base_exhaustion = (abs_btc_cvd / 1000000) * 100
                    var_boost = abs(btc_var) * 15
                    self.exhaustion_level = min(99.0, base_exhaustion + var_boost)

                    # [V110.17.0] btc_drag_mode determination moved below to use ADX
                    pass
                    
                    if btc_price == 0:
                        try:
                            ticker = await okx_rest_service.get_tickers(symbol="BTCUSDT")
                            btc_price = float(ticker.get("result", {}).get("list", [{}])[0].get("lastPrice", 0))
                            logger.info(f"📊 [SIG-GEN] BTC Fallback REST: ${btc_price:,.0f}")
                        except Exception as e:
                            logger.warning(f"⚠️ [SIG-GEN] BTC Fallback REST Failed: {e}")
                    
                    # [V110.36.6] M-ADX SSOT para Telemetria UI (Zero Flicker)
                    # Utiliza desde o início o M-ADX calculado pelo Websocket, 
                    # removendo as amnésias causadas por detect_market_regime.
                    btc_adx_inner = getattr(okx_ws_public_service, 'btc_adx', 0)
                    if btc_adx_inner == 0:
                        # Fallback se ws ainda não tiver aquecido
                        _fallback_regime = await self.detect_market_regime("BTCUSDT.P")
                        btc_adx_inner = _fallback_regime.get("adx", 0)

                    if btc_price > 0:
                        logger.info(f"📊 [SIG-GEN] BTC Command Center: ${btc_price:,.0f} | Var: {btc_var:.2f}% | CVD: ${btc_cvd/1000000:.2f}M")
                        
                        # 🆕 [V110.32.1] Fetch Validated Context from Oracle
                        oracle_ctx = None
                        # [V110.36.9] Injetar Direção Real baseada no ADX para evitar "ICE LATERAL" fantasma na UI
                        inferred_dir = "LATERAL"
                        if btc_adx_inner >= 30: inferred_dir = "ROARING"
                        elif btc_adx_inner >= 25: inferred_dir = "TRENDING"

                        await firebase_service.update_pulse_drag(
                            self.btc_drag_mode, abs_btc_cvd, self.exhaustion_level,
                            okx_ws_public_service.btc_price, okx_ws_public_service.btc_variation_1h,
                            btc_adx_inner, 0, okx_ws_public_service.btc_variation_24h,
                            btc_direction=inferred_dir, # <-- Fix: Direção Real
                            oracle_context=oracle_ctx
                        )

                    
                # [V29.0 OVERRIDE] Always use DB slots to match Frontend UI
                slots = await firebase_service.get_active_slots()
                # A slot is only truly occupied if it has a symbol, AND qty > 0 AND entry_price > 0.
                occupied_count = sum(1 for s in slots if s.get("symbol") and float(s.get("qty", 0)) > 0 and float(s.get("entry_price", 0)) > 0)
                
                # [V110.36.3] Usar M-ADX do okx_ws_public (Fonte Única de Verdade) em vez de recalcular.
                # Elimina conflito entre ADX 1H (22.46) e M-ADX ponderado (34.0).
                m_adx = getattr(okx_ws_public_service, 'btc_adx', 0)
                if m_adx and m_adx > 0:
                    btc_adx = m_adx
                    logger.debug(f"🔮 [S1-ADX] Usando M-ADX={btc_adx:.1f} (Fonte: okx_ws_public)")
                elif 'btc_adx_inner' in dir():
                    btc_adx = btc_adx_inner
                else:
                    btc_regime_data = await self.detect_market_regime("BTCUSDT.P")
                    btc_adx = btc_regime_data.get("adx", 0)
                is_btc_lateral = btc_adx < 28  # [V110.12.2] Anti-Microspike Buffer
                
                # [V110.17.0] UNIFY DRAG MODE: Sync UI status with ADX logic
                btc_var_15m = okx_ws_public_service.btc_variation_15m
                if not is_btc_lateral:
                    self.btc_drag_mode = "UP" if btc_var_15m >= 0 else "DOWN"
                    # [V14.0 Log]
                    logger.info(f"🦅 V14.0: BTC DRAG MODE ACTIVE ({self.btc_drag_mode}) | ADX: {btc_adx:.1f} | Var: {btc_var_15m:.2f}% | CVD: ${okx_ws_public_service.get_cvd_score('BTCUSDT')/1000000:.2f}M")
                else:
                    self.btc_drag_mode = False
                    
                # Update Pulse DRAG for UI — [V110.36.1] Always uses real btc_adx (no more 0.0 flicker)
                # [V110.36.9] Injetar Direção Real baseada no ADX no Fallback
                inferred_dir = "LATERAL"
                if btc_adx >= 30: inferred_dir = "ROARING"
                elif btc_adx >= 25: inferred_dir = "TRENDING"

                await firebase_service.update_pulse_drag(
                    self.btc_drag_mode, 
                    abs(okx_ws_public_service.get_cvd_score("BTCUSDT")), getattr(self, 'exhaustion_level', 0),
                    okx_ws_public_service.btc_price, okx_ws_public_service.btc_variation_1h,
                    btc_adx, 0, okx_ws_public_service.btc_variation_24h,
                    btc_direction=inferred_dir, # <-- Fix: Direção Real
                    oracle_context=oracle_ctx
                )

                # 🆕 [V110.999] BTC CLIMATE & TSUNAMI DETECTOR
                try:
                    from services.agents.macro_analyst import macro_analyst
                    btc_dominance = await macro_analyst._get_btc_dominance()
                except Exception:
                    btc_dominance = 58.0
                
                if btc_dominance <= 0:
                    btc_dominance = 58.0
                
                btc_var_1h = okx_ws_public_service.btc_variation_1h
                self.is_btc_tsunami = (btc_dominance > 55.0) and (btc_adx > 30.0) and (btc_var_1h > 0)
                if self.is_btc_tsunami:
                    logger.warning(f"🚨 [BTC CLIMATE] TSUNAMI DETECTADO! Dominancia BTC: {btc_dominance:.1f}% | ADX: {btc_adx:.1f} | Var 1h: {btc_var_1h:.2f}%. Shorts em altcoins serao bloqueados globalmente.")



                # [V71.1] HYSTERESIS ANTI-FLAP: Require N consecutive readings before switching mode
                if is_btc_lateral:
                    self._radar_ranging_streak += 1
                    self._radar_trending_streak = 0
                else:
                    self._radar_trending_streak += 1
                    self._radar_ranging_streak = 0
                
                # Only switch mode after sustained confirmation
                if self.current_radar_mode == "SCAVENGER_RANGE" and self._radar_trending_streak >= self._RADAR_HYSTERESIS_THRESHOLD:
                    self.current_radar_mode = "ELITE_30_TREND"
                    self._last_ws_rebalance = 0  # Force immediate rebalance
                    logger.info(f"🔄 [V75.2 HYSTERESIS] Radar switched to ELITE_30_TREND after {self._RADAR_HYSTERESIS_THRESHOLD} consecutive TRENDING readings.")
                elif self.current_radar_mode == "ELITE_30_TREND" and self._radar_ranging_streak >= self._RADAR_HYSTERESIS_THRESHOLD:
                    self.current_radar_mode = "SCAVENGER_RANGE"
                    self._last_ws_rebalance = 0  # Force immediate rebalance
                    logger.info(f"🔄 [V75.2 HYSTERESIS] Radar switched to SCAVENGER_RANGE after {self._RADAR_HYSTERESIS_THRESHOLD} consecutive RANGING readings.")

                # [V71.0] HYBRID FUNNEL: Global Radar (600) -> Focused WS (90) OR Elite 30
                all_liquid_symbols = await okx_rest_service.get_elite_50x_pairs() # Now returns 600
                
                # [V75.2] Elite 50 — Almirante's Selection (Expanded for Variety)
                ELITE_50_PAIRS = [
                    # Original Elite 30
                    "ADAUSDT.P", "DOGEUSDT.P", "AAVEUSDT.P", "POLUSDT.P", "GALAUSDT.P",
                    "LINKUSDT.P", "AVAXUSDT.P", "NEARUSDT.P", "APTUSDT.P", "SUIUSDT.P",
                    "DOTUSDT.P", "INJUSDT.P", "LTCUSDT.P", "BCHUSDT.P", "ICPUSDT.P",
                    "LDOUSDT.P", "RENDERUSDT.P", "ENAUSDT.P", "OPUSDT.P", "ARBUSDT.P",
                    "TIAUSDT.P", "SEIUSDT.P", "AXSUSDT.P", "FETUSDT.P", "TAOUSDT.P",
                    "IMXUSDT.P", "FTMUSDT.P", "STXUSDT.P", "BEAMUSDT.P", "PYTHUSDT.P",
                    # Expanded Elite +20
                    "SOLUSDT.P", "ETHUSDT.P", "XRPUSDT.P", "PEPEUSDT.P", "WIFUSDT.P",
                    "BONKUSDT.P", "SHIB1000USDT.P", "ATOMUSDT.P", "FILUSDT.P", "STMXUSDT.P",
                    "JUPUSDT.P", "STRKUSDT.P", "DYDXUSDT.P", "GMXUSDT.P", "CRVUSDT.P",
                    "LUNA2USDT.P", "EGLDUSDT.P", "GRTUSDT.P", "THETAUSDT.P", "VETUSDT.P"
                ]

                # Periodic rebalance of WebSocket (every 60s)
                if now - getattr(self, '_last_ws_rebalance', 0) > 60:
                    try:
                        if self.current_radar_mode == "ELITE_30_TREND":
                            # [V71.0] If trending, lock to the Majors. No need to rank decorrelation.
                            top_90 = ELITE_50_PAIRS
                            logger.info(f"📡 [V71.0 DYNAMIC RADAR] BTC TRENDING! Locking WebSocket to ELITE 50 Majors.")
                        else:
                            # [V127] LOCK LATERAL MARKET TO DECOR_HUNTER 19 PAIRS ONLY
                            # The user explicitly requested that the "Arrastao" bypass should ONLY allow the 19 shielded pairs
                            # instead of scanning the top 40 or 90.
                            from config import settings
                            watchlist = getattr(settings, 'RADAR_WATCHLIST', [])
                            if not watchlist:
                                watchlist = [
                                    "SOLUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT", "NEARUSDT",
                                    "INJUSDT", "APTUSDT", "ARBUSDT", "ATOMUSDT", "LTCUSDT",
                                    "ETCUSDT", "AAVEUSDT", "UNIUSDT", "SANDUSDT", "CHZUSDT",
                                    "XLMUSDT", "XRPUSDT", "TRXUSDT", "FILUSDT", "SUIUSDT",
                                ]
                            top_90 = [sym if sym.endswith('.P') else sym + '.P' for sym in watchlist]
                            if "BTCUSDT.P" not in top_90: top_90.insert(0, "BTCUSDT.P")
                            logger.info(f"📡 [V71.0 DYNAMIC RADAR] BTC RANGING! Locking WebSocket to 20 Decorrelated Pairs (DECOR_HUNTER MODE).")
                            
                        await okx_ws_public_service.sync_topics(top_90)
                        self._last_ws_rebalance = now
                    except Exception as rb_err:
                        logger.error(f"Failed to rebalance WS: {rb_err}")

                active_symbols_ws = okx_ws_public_service.active_symbols
                
                # [V32.0] PERIODIC DASHBOARD SYNC (BTC Context & Radar)
                if now - self.last_radar_sync > 10:
                    asyncio.create_task(self._sync_radar_rtdb())
                    self.last_radar_sync = now



                trading_allowed, reason = await vault_service.is_trading_allowed()
                
                if not trading_allowed:
                    self.system_message = reason
                    self.occupied_count = 0
                    if self.system_state != "PAUSED" or (time.time() * 1000 - self.last_state_update > 30000):
                        self.system_state = "PAUSED"
                        self.last_state_update = time.time() * 1000
                        from services.agents.captain import captain_agent
                        lr = getattr(captain_agent, 'last_reconciliation_time', 0)
                        await firebase_service.update_system_state("PAUSED", 0, reason, protocol="Sniper V15.1", last_reconciliation=lr)
                        logger.info(f"🔴 V15.1: System → PAUSED ({reason})")
                    await asyncio.sleep(5) 
                    continue
                
                # [V42.0] SCANNING Logic Override for Lateral Markets
                # If BTC is lateral, we use the specific V42.0 scanning message
                desired_scanning_msg = "Buscando sinais descorrelacionados do BTC (V42.0)" if is_btc_lateral else "Buscando oportunidades..."
                
                force_update = (occupied_count < 4 and is_btc_lateral and "V42.0" not in self.system_message)
                
                if self.system_state == "PAUSED" or force_update or (time.time() * 1000 - self.last_state_update > 60000):
                    self.system_state = "SCANNING"
                    self.system_message = desired_scanning_msg
                    self.last_state_update = time.time() * 1000
                    from services.agents.captain import captain_agent
                    lr = getattr(captain_agent, 'last_reconciliation_time', 0)
                    await firebase_service.update_system_state("SCANNING", occupied_count, desired_scanning_msg, protocol="Sniper V15.1", last_reconciliation=lr)
                    logger.info(f"[STAGE-0] V15.1: System -> SCANNING ({desired_scanning_msg})")

                # [V34.2] Update occupied_count for all cases
                self.occupied_count = occupied_count


                if occupied_count >= 4:
                    self.system_message = "Slots preenchidos 4/4"
                    if self.system_state != "MONITORING" or (time.time() - self.last_state_update > 30):
                        self.system_state = "MONITORING"
                        self.last_state_update = time.time()
                        from services.agents.captain import captain_agent
                        lr = getattr(captain_agent, 'last_reconciliation_time', 0)
                        await firebase_service.update_system_state("MONITORING", occupied_count, self.system_message, protocol="Sniper V15.1", last_reconciliation=lr)
                        logger.info(f"[STAGE-0] V15.1: MONITORING (4/4 slots ocupados). Scan CONTINUO ativo para o Radar.")
                

                
                # ═══════════════════════════════════════════════════════════════
                # ████ ESTÁGIO 1 — TRIAGEM RÁPIDA (0 API calls / 1 Fallback) ████
                # Usa APENAS dados em memória: CVD do WebSocket + RSI cache
                # ═══════════════════════════════════════════════════════════════
                # [V110.36.4] USA O M-ADX GLOBAL DO LOOP.
                # Removida a chamada redundante detect_market_regime() que corrompia o M-ADX.
                # is_btc_lateral já está corretamente definido pela fonte única (okx_ws_public_service.btc_adx)

                # [V43.0] PARALLEL RADAR STAGE 1
                async def stage1_worker(symbol, is_btc_lateral):
                    try:
                        norm_sym = symbol.replace(".P", "").upper() if symbol else symbol
                        if norm_sym in self.asset_blocklist_permanent: return None
                        
                        auto_block = self.auto_blocked_assets.get(norm_sym)
                        if auto_block and time.time() < auto_block.get('blocked_until', 0): return None
                        
                        cvd_val = okx_ws_public_service.get_cvd_score(symbol)
                        ws_freshness = getattr(okx_ws_public_service, '_last_trade_ts', {}).get(symbol, 0)
                        cvd_is_stale = (time.time() - ws_freshness > 30) if ws_freshness > 0 else False
                        
                        # [V20.4] REST Fallback if WS CVD is zero/stale
                        if cvd_val == 0 or cvd_is_stale:
                            cvd_val = await self.calculate_rest_cvd(symbol)
                            
                        abs_cvd = abs(cvd_val)
                        macro_2h = self.trend_cache_2h.get(symbol) or self.trend_cache_2h.get(norm_sym, {})
                        trend_2h = macro_2h.get('trend', 'NEUTRAL')
                        tactical_30m = self.trend_cache_30m.get(symbol) or self.trend_cache_30m.get(norm_sym, {})
                        trend_30m = tactical_30m.get('trend', 'NEUTRAL')
                        freshness_30m = tactical_30m.get('freshness', 99)
                        dist_from_sma = tactical_30m.get('dist_from_sma8', 0)
                        
                        is_swing_macro = False
                        macro_bonus = 0
                        side_label = "Long" if cvd_val > 0 else "Short"
                        
                        # 🆕 [V110.999] BTC TSUNAMI SHORT BLOCK
                        if getattr(self, 'is_btc_tsunami', False) and side_label == "Short":
                            logger.debug(f"🔒 [BTC TSUNAMI BLOCK S1] SHORT em {symbol} bloqueado preventivamente pela dominancia/forca do BTC!")
                            return None
                        
                        if trend_2h == 'BULLISH_ARMED' and trend_30m == 'BULLISH_TACTICAL':
                            if freshness_30m <= 5 and dist_from_sma < 1.5:
                                side_label, is_swing_macro, macro_bonus = "Long", True, 40
                        elif trend_2h == 'BEARISH_ARMED' and trend_30m == 'BEARISH_TACTICAL':
                            if freshness_30m <= 5 and dist_from_sma > -1.5:
                                side_label, is_swing_macro, macro_bonus = "Short", True, 40
                        elif trend_2h in ('BULLISH_ARMED', 'BEARISH_ARMED'):
                            btc_ctx = self.btc_direction_cache
                            btc_dir_s1, btc_str_s1 = btc_ctx.get('direction', 'NEUTRAL'), btc_ctx.get('strength', 0)
                            if btc_dir_s1 == 'UP' and btc_str_s1 > 30 and cvd_val > -50000: side_label = "Long"
                            elif btc_dir_s1 == 'DOWN' and btc_str_s1 > 30 and cvd_val < 50000: side_label = "Short"
                        else:
                            btc_ctx = self.btc_direction_cache
                            btc_dir_s1, btc_str_s1 = btc_ctx.get('direction', 'NEUTRAL'), btc_ctx.get('strength', 0)
                            if btc_dir_s1 == 'UP' and btc_str_s1 > 30 and cvd_val > -50000: side_label = "Long"
                            elif btc_dir_s1 == 'DOWN' and btc_str_s1 > 30 and cvd_val < 50000: side_label = "Short"

                        # [V44.3] ADX Slope (Acceleration) & Temporal CVD (5m)
                        trend_1h_data = self.trend_cache.get(symbol) or self.trend_cache.get(norm_sym, {})
                        adx_slope = trend_1h_data.get('adx_slope', 0)
                        cvd_5m = okx_ws_public_service.get_cvd_score_time(symbol, 300) # 5m window
                        
                        adx_slope_score = min(20, adx_slope * 10) if adx_slope > 0 else 0
                        cvd_5m_score = min(25, (abs(cvd_5m) / 100000.0) * 25.0) if (cvd_5m > 0 and side_label == "Long") or (cvd_5m < 0 and side_label == "Short") else 0

                        rsi = okx_ws_public_service.rsi_cache.get(symbol, 50)
                        oi_val = okx_ws_public_service.oi_cache.get(symbol, 0)
                        ls_ratio = okx_ws_public_service.ls_ratio_cache.get(symbol, 1.0)
                        ls_score = 15 if (side_label == "Long" and ls_ratio < 0.9) or (side_label == "Short" and ls_ratio > 1.5) else 0
                        rsi_score = min(30.0, ((65 - rsi) / 35.0) * 30.0) if (side_label == "Long" and rsi < 65) else (min(30.0, ((rsi - 35) / 35.0) * 30.0) if (side_label == "Short" and rsi > 35) else 0)
                        whale_bonus = 20 if abs_cvd > 250000 else 0
                        cvd_score = min(40.0, (abs_cvd / 300000.0) * 40.0) # Slightly reduced base CVD to make room for 5m
                        
                        mean_reversion_score = 55 if not self.btc_drag_mode and ((rsi > 75 and side_label == "Short") or (rsi < 25 and side_label == "Long")) else 0
                        
                        # Ensure variables are defined before gather
                        v_rec_t = self.detect_v_recovery(symbol)
                        box_brk_t = self.detect_box_breakout(symbol)
                        decor_t = self.detect_btc_decorrelation(symbol, cvd_val, ls_ratio, oi_val)
                        
                        v_rec, box_brk, decor_data = await asyncio.gather(v_rec_t, box_brk_t, decor_t)
                        
                        v42_pattern = {'detected': False}
                        if v_rec.get('detected') and v_rec.get('side', '').capitalize() == side_label: v42_pattern = {'detected': True, 'type': 'V-RECOVERY'}
                        elif box_brk.get('detected') and box_brk.get('side', '').capitalize() == side_label: v42_pattern = {'detected': True, 'type': 'BOX-BREAKOUT'}
                        
                        is_decorrelated = decor_data.get('is_decorrelated', False)
                        
                        # [V44.3] Final Preliminary Score with new Acceleration Metrics
                        preliminary_score = cvd_score + cvd_5m_score + rsi_score + whale_bonus + ls_score + \
                                            mean_reversion_score + macro_bonus + adx_slope_score
                        
                        if v42_pattern.get('detected'): preliminary_score += 20
                        if is_decorrelated: preliminary_score += 25

                        hot_data = self.hot_assets.get(norm_sym)
                        if hot_data and (time.time() - hot_data.get('last_win_at', 0)) < self.hot_asset_ttl:
                            if hot_data.get('wins', 0) >= 2: preliminary_score += 15
                            
                        # [V110.12.6] ASSET FILTER: Ignore non-crypto assets
                        if norm_sym in self.asset_blocklist_permanent:
                            logger.debug(f"🚫 [BLOCKLIST] Ignorando {symbol} (Ativo em blocklist permanente).")
                            return None

                        # [V120] LATERAL-LOCK S1 REMOVIDO — Todos os sinais passam direto para Captain decidir.
                        # Radar removido: sinais agora viram ordens diretas. Sem filtro lateral no S1.
                        if is_btc_lateral:
                            logger.info(f"🔓 [S1-LATERAL-PASS] {symbol} Score={preliminary_score:.0f} | Decor={is_decorrelated} → Passando para Captain (ordem direta).")
                            
                            
                        # [V44.3] Relaxation: Allow entries with lower total CVD if 5m CVD is explosive OR ADX is accelerating
                        significant_move = abs_cvd > 1500 or abs(cvd_5m) > 20000 or adx_slope > 0.5
                        if not significant_move and ls_score == 0 and not is_decorrelated and not is_swing_macro: return None
                        
                        return {
                            'symbol': symbol, 'cvd_val': cvd_val, 'abs_cvd': abs_cvd, 'rsi': rsi, 'side_label': side_label,
                            'cvd_score': cvd_score, 'rsi_score': rsi_score, 'whale_bonus': whale_bonus, 'ls_score': ls_score,
                            'oi_val': oi_val, 'preliminary_score': preliminary_score, 'decorrelation_data': decor_data,
                            'is_decorrelated': is_decorrelated, 'is_mean_reversion': mean_reversion_score > 0,
                            'is_swing_macro': is_swing_macro, 'v42_pattern': v42_pattern,
                            'is_market_ranging': is_btc_lateral, # Pass context to execution protocol
                            'is_shadow_strike': False # [V110.20.0] Shadow Strike Desativado
                        }
                    except Exception as e:
                        logger.error(f"Error in stage1_worker for {symbol}: {e}")
                        return None

                s1_semaphore = asyncio.Semaphore(15)
                async def sem_worker(s):
                    async with s1_semaphore: return await stage1_worker(s, is_btc_lateral)
                
                s1_tasks = [sem_worker(s) for s in active_symbols_ws]
                start_s1 = time.time()
                stage1_results = await asyncio.gather(*s1_tasks)
                s1_duration = time.time() - start_s1
                stage1_candidates = [r for r in stage1_results if r is not None]
                logger.info(f"⚡ [RADAR-PERF] Estágio 1 Paralelo: {len(active_symbols_ws)} ativos em {s1_duration:.2f}s. Encontrados {len(stage1_candidates)} candidatos.")

                # [V28.2] Radar Expansion: Relaxed to $3M (was $5M) for more signal diversity in Paper Mode
                # Filter for candidates
                s1_filtered = []
                for candidate in stage1_candidates:
                    symbol = candidate['symbol']
                    turnover_24h = okx_ws_public_service.turnover_24h_cache.get(symbol, 0)
                    
                    # [V38.0] Macro Swing needs less liquidity ($500k) because it trades slow timeframes
                    min_turnover = 500000 if candidate.get('is_swing_macro') else 1000000
                    
                    if turnover_24h < min_turnover:
                        if symbol in ['SPXUSDT', 'JASMYUSDT', 'TIAUSDT']: logger.info(f"🔎 [TRACE] {symbol} dropped Stage 1 (Liquidity): turnover={turnover_24h/1000000:.1f}M < min={min_turnover/1000000:.1f}M")
                        continue
                    if symbol in ['SPXUSDT', 'JASMYUSDT', 'TIAUSDT']: logger.info(f"🔎 [TRACE] {symbol} survived Stage 1 filtering!")
                    s1_filtered.append(candidate)
                stage1_candidates = s1_filtered
                
                # Run Stage 2 in parallel (max 20 symbols)
                s2_results = await asyncio.gather(*(stage2_analyze(c) for c in stage1_candidates))
                stage2_candidates = [r for r in s2_results if r is not None]
                
                # [V28.2] Sort by tactical score and take top 8 (was 5) for more signal throughput
                stage2_candidates.sort(key=lambda x: x['tactical_score'], reverse=True)
                stage2_candidates = stage2_candidates[:8]  # [V33.1] Expanded back to 8 for better radar diversity
                
                s2_count = len(stage2_candidates)
                
                # ═══════════════════════════════════════════════════════════════
                # ████ ESTÁGIO 3 — VALIDAÇÃO ELITE (2 API calls cada) ████
                # Full multi-timeframe: 4H EMA + 15m Zones + Shadow detection
                # ═══════════════════════════════════════════════════════════════
                # [V91.0] Relaxed to 45 — Captain has its own filters (Needle Flip, Fleet, etc)
                # [V110.7] Execution Threshold vs Anticipation
                # Real execution now requires 65+ for maximum bank safety.
                # Anticipation Shadow Mode captures 45+.
                
                # [V110.113] DYNAMIC THRESHOLDS (Threshold Calibrator)
                # Se calibrador estiver ativo, usa thresholds calibrados
                from services.threshold_calibrator import threshold_calibrator
                
                min_threshold = threshold_calibrator.get_threshold("min_score")
                anticipation_min = 65 # [V110.20.0] High anticipation
                
                if threshold_calibrator.enabled:
                    logger.debug(f"📊 [THRESH-DYNAMIC] min_score={min_threshold} (calibrado)")
                
                # Check if trace symbols made it to S3
                s3_symbols = [c['symbol'].replace('.P', '') for c in stage2_candidates]
                for tsym in ['SPXUSDT', 'JASMYUSDT', 'TIAUSDT']:
                    if tsym not in s3_symbols:
                        logger.info(f"🔎 [TRACE] {tsym} DID NOT MAKE IT TO STAGE 3. They were dropped between passing S2 and sorting S3.")
                
                async def stage3_validate(candidate):
                    from services.execution_protocol import execution_protocol
                    from config import settings as _settings  # [FIX] Import antecipado para evitar UnboundLocalError
                    async with self._api_semaphore:
                        symbol = candidate['symbol']
                        side_label = candidate['side_label']
                        cvd_val = candidate['cvd_val']
                        # [DEBUG] Audit Stage 3 Entry
                        # logger.info(f"🔍 [STAGE3] Starting validation for {symbol}...")
                    
                    # V27.0: Full Multi-Timeframe Analysis (2H + 4H + 15m + Daily + Regime + BTC Direction)
                        macro_2h, trend_4h, zones_15m, daily_macro, market_regime, btc_dir, btc_regime_data = await asyncio.gather(
                            self.get_2h_macro_analysis(symbol),
                            self.get_4h_trend_analysis(symbol),
                            self.get_15m_zones(symbol),
                            self.get_daily_macro_filter(symbol),
                            self.detect_market_regime(symbol),
                            self.get_btc_direction_filter(),
                            self.detect_market_regime("BTCUSDT.P") # [V42.9] RANGING BTC Guard
                        )
                    
                    # [V110.960] Determina alinhamento com a tendência da SMA de 2H
                    trend_2h = macro_2h.get('trend', 'NEUTRAL')
                    is_sma_2h_aligned = False
                    if side_label == "Long" and trend_2h == "BULLISH_ARMED":
                        is_sma_2h_aligned = True
                    elif side_label == "Short" and trend_2h == "BEARISH_ARMED":
                        is_sma_2h_aligned = True

                    # 🆕 [V110.999] ZONE NEUTRA DE FLEXIBILIZAÇÃO (FLEX_MODE) & DVAP STRATEGY DETECTOR
                    rsi_2h = macro_2h.get('rsi_2h', 50.0)
                    is_flex_mode = (43.0 <= rsi_2h <= 57.0)
                    is_dvap_play = False
                    dvap_targets = None
                    
                    try:
                        # Buscar velas de 30M para cálculo de Divergência, Volume e CHoCH
                        klines_30m = await okx_rest_service.get_klines(symbol=symbol, interval="30", limit=100)
                        if klines_30m and len(klines_30m) >= 40:
                            candles_30m = klines_30m[::-1]
                            closes_30m = [float(c[4]) for c in candles_30m]
                            highs_30m = [float(c[2]) for c in candles_30m]
                            lows_30m = [float(c[3]) for c in candles_30m]
                            volumes_30m = [float(c[5]) for c in candles_30m]
                            
                            # 1. Divergência IFR (RSI 14)
                            div_type = self.check_ifr_divergence(closes_30m, highs_30m, lows_30m)
                            # 2. Volume Clímax (absorção)
                            vol_climax = self.check_volume_climax(volumes_30m, std_multiplier=1.8)
                            
                            if div_type and vol_climax:
                                # 3. Encontrar Pivots táticos de 30M
                                p_high, p_low = self.find_pivots_30m(highs_30m, lows_30m)
                                current_close = closes_30m[-1]
                                prev_close = closes_30m[-2]
                                
                                # 4. Gatilho CHoCH
                                is_choch_buy = (current_close > p_high) and (prev_close <= p_high) and (div_type == "BULLISH")
                                is_choch_sell = (current_close < p_low) and (prev_close >= p_low) and (div_type == "BEARISH")
                                
                                if is_choch_buy and side_label == "Long":
                                    is_dvap_play = True
                                    tp1, tp2 = self.calculate_fibonacci_targets("BUY", current_close, p_low)
                                    dvap_targets = {"tp1": tp1, "tp2": tp2, "sl": p_low}
                                    logger.info(f"💎 [DVAP STRATEGY TRIGGERED] {symbol} LONG! Divergencia: {div_type} | Volume Climax | CHoCH: {p_high} | SL = {p_low} | TP1 = {tp1}")
                                elif is_choch_sell and side_label == "Short":
                                    is_dvap_play = True
                                    tp1, tp2 = self.calculate_fibonacci_targets("SELL", current_close, p_high)
                                    dvap_targets = {"tp1": tp1, "tp2": tp2, "sl": p_high}
                                    logger.info(f"💎 [DVAP STRATEGY TRIGGERED] {symbol} SHORT! Divergencia: {div_type} | Volume Climax | CHoCH: {p_low} | SL = {p_high} | TP1 = {tp1}")
                    except Exception as dv_err:
                        logger.error(f"Erro ao avaliar setup DVAP para {symbol}: {dv_err}")

                    # [V110.960 LRT] Detecta Liquidity Sweep
                    is_lrt_play = False
                    try:
                        lrt_res = await self.detect_lrt_setup(symbol, zones_15m)
                        if lrt_res.get("detected") and lrt_res.get("side") == side_label:
                            is_lrt_play = True
                            logger.info(f"🦇 [LRT STRATEGY TRIGGERED] {symbol} {side_label} via {lrt_res.get('type')}")
                    except Exception as lrt_err:
                        logger.error(f"Erro ao avaliar setup LRT para {symbol}: {lrt_err}")

                    # [V110.960 FAS] Detecta Funding Squeeze
                    is_fas_play = False
                    try:
                        fas_res = await self.detect_fas_setup(symbol)
                        if fas_res.get("detected") and fas_res.get("side") == side_label:
                            is_fas_play = True
                            logger.info(f"🔥 [FAS STRATEGY TRIGGERED] {symbol} {side_label} via {fas_res.get('type')} (Rate={fas_res.get('rate')})")
                    except Exception as fas_err:
                        logger.error(f"Erro ao avaliar setup FAS para {symbol}: {fas_err}")

                    # Detecta MOLA (Squeeze de Volatilidade)
                    is_mola_play = False
                    try:
                        # [FIX-ALPHA-SHIELD] Usar bb_width real do regime do ativo em vez de 3.5 hardcoded
                        asset_bb_width = market_regime.get('bb_width', 5.0)
                        squeeze_res = await self.detect_squeeze(symbol, bb_width=asset_bb_width)
                        is_mola_play = squeeze_res.get("is_squeeze", False)
                        if is_mola_play:
                            logger.info(f"🌊 [MOLA STRATEGY TRIGGERED] {symbol} BB Width={asset_bb_width:.2f} < 1.2")
                    except Exception as sq_err:
                        logger.error(f"Erro ao avaliar setup MOLA para {symbol}: {sq_err}")

                    # [V110.960] Classifica a estratégia do sinal seguindo a Hierarquia Consensual
                    raw_class = "SWING"
                    if is_lrt_play:
                        raw_class = "LRT"
                    elif is_dvap_play:
                        raw_class = "DVAP"
                    elif is_fas_play:
                        raw_class = "FAS"
                    elif is_mola_play:
                        raw_class = "MOLA"
                    elif candidate.get("is_decorrelated", False):
                        raw_class = "DECOR"
                    elif candidate.get("v42_pattern", {}).get("detected", False):
                        raw_class = str(candidate.get("v42_pattern", {}).get("type", "RANGING")).upper()
                    else:
                        # Se não for nenhuma das especiais, classificamos como ABCD ou 1-2-3 baseando-se no padrão
                        pat_name = str(candidate.get("indicators", {}).get("pattern", "unknown")).upper()
                        if "ABCD" in pat_name:
                            raw_class = "ABCD"
                        elif "123" in pat_name:
                            raw_class = "1-2-3"
                        else:
                            raw_class = "TREND"

                    # [FIX-ALPHA-SHIELD] LRT agora classificado como ALPHA SHIELD (antes caia no else como VELOCITY FLOW)
                    if raw_class in ("DVAP", "MOLA", "FAS", "LRT"):
                        strategy_class = "ALPHA SHIELD"
                    elif raw_class in ("DECOR", "DECOR_HUNTER"):
                        strategy_class = "DECOR SHADOW"
                    else:
                        strategy_class = "VELOCITY FLOW"

                    # 2. Executa Filtros Rígidos de Consenso por Estratégia
                    # [NOTA] O Regime Gating (bloqueio de V.F em LATERAL e D.S em TENDENCIA)
                    # foi movido EXCLUSIVAMENTE para o Captain. O Radar (signal_generator)
                    # DEVE emitir todos os sinais para que o Sandbox possa testar todos os cenários.

                    if raw_class in ("LRT", "DVAP", "ABCD", "1-2-3", "TREND", "DECOR", "DECOR_HUNTER"):
                        # LRT, DVAP, ABCD, 1-2-3 e TREND exigem alinhamento direcional com a SMA de 2H
                        if not is_sma_2h_aligned:
                            reason = f"SMA 2H ALIGN: Setup {strategy_class} 30M nao alinhado com o cruzamento da SMA de 2H (Trend 2H={trend_2h})"
                            logger.info(f"🚫 [SMA2H-ALIGN-REJECT] {symbol} rejeitado: {reason}")
                            self.recent_rejections.append({"symbol": symbol, "reason": reason, "timestamp": time.time()})
                            return None
                    elif raw_class == "MOLA":
                        # MOLA exige ADX >= 25 para evitar falsos rompimentos em lateralização
                        asset_adx = market_regime.get("adx", 20.0)
                        if asset_adx < 25.0:
                            reason = f"MOLA ADX SHIELD: Setup MOLA 30M rejeitado por ADX muito baixo ({asset_adx:.1f} < 25)"
                            logger.info(f"🚫 [MOLA-ADX-REJECT] {symbol} rejeitado: {reason}")
                            self.recent_rejections.append({"symbol": symbol, "reason": reason, "timestamp": time.time()})
                            return None
                    elif raw_class == "FAS":
                        # FAS (Funding Squeeze) é isento de alinhamento com a SMA de 2H por ser puramente contra-tendência
                        logger.info(f"⚡ [FAS EXEMPTION] {symbol} {side_label} isento de alinhamento SMA 2H devido a Funding Extremo.")

                    # [V127] PROTOCOLO ALT BIAS ONLY (AltForceDirection Guard)
                    # O viés direcional macro de 2H é lei absoluta para moedas desgrudadas (is_decorrelated = True)
                    is_decorrelated_play = candidate.get('is_decorrelated', False)
                    # DVAP e FLEX_MODE ignoram o AltForceDirection Guard para evitar paralisia
                    if is_decorrelated_play and not is_dvap_play and not is_flex_mode:
                        rsi_2h = macro_2h.get('rsi_2h', 50.0)
                        trend_2h = macro_2h.get('trend', 'NEUTRAL')
                        
                        # Determina o viés macro rígido com base no RSI 2H ou cruzamento de médias SMA 2H
                        bias_2h = "NEUTRAL"
                        if rsi_2h > 50 or trend_2h == "BULLISH_ARMED":
                            bias_2h = "LONG_ONLY"
                        elif rsi_2h < 50 or trend_2h == "BEARISH_ARMED":
                            bias_2h = "SHORT_ONLY"
                            
                        if bias_2h == "LONG_ONLY" and side_label == "Short":
                            reason = f"ALT FORCE DIRECTION GUARD: {symbol} desgrudado em viés de ALTA (RSI 2H={rsi_2h:.1f}, Trend={trend_2h}). SHORT proibido!"
                            logger.warning(f"🚫 [ALT-FORCE-REJECT] {reason}")
                            self.recent_rejections.append({"symbol": symbol, "reason": reason, "timestamp": time.time()})
                            return None
                            
                        if bias_2h == "SHORT_ONLY" and side_label == "Long":
                            reason = f"ALT FORCE DIRECTION GUARD: {symbol} desgrudado em viés de BAIXA (RSI 2H={rsi_2h:.1f}, Trend={trend_2h}). LONG proibido!"
                            logger.warning(f"🚫 [ALT-FORCE-REJECT] {reason}")
                            self.recent_rejections.append({"symbol": symbol, "reason": reason, "timestamp": time.time()})
                            return None

                    # [V43.2] RANGING BTC GUARD: If BTC is ranging, only allow high ADX signals
                    # Relaxation: If BTC is UP, allow symbols with ADX > 15 (was 25)
                    btc_regime = btc_regime_data.get('regime', 'TRANSITION')
                    btc_is_up = btc_dir.get('direction') == 'UP'
                    
                    # [V110.36.5] VANGUARD PRE-QUALIFIER (S2): REMOVIDO V111.4.
                    # O CaptainAgent já possui regime gating completo (LATERAL→D.S, TRENDING→V.F).
                    # Esta guarda era redundante e bloqueava todo sinal em REAL mode com ADX<25,
                    # impedindo o D.S de operar em mercado lateral mesmo com pares desgrudados.
                    # Log mantido apenas para diagnóstico:
                    m_adx = getattr(okx_ws_public_service, 'btc_adx', 0)
                    if m_adx < _settings.ADX_TRENDING_THRESHOLD:
                        logger.info(f"🔓 [ADX-GUARD-PASS] {symbol} passou ao Captain (ADX={m_adx:.1f})")
                    
                    self._diag_counters['ema4h_pass'] += 1
                    
                    # 🔍 [V15.5] LS Ratio & Open Interest Validation
                    ls_ratio = okx_ws_public_service.ls_ratio_cache.get(symbol, 1.0)
                    oi_val = okx_ws_public_service.oi_cache.get(symbol, 0)
                    turnover_24h = okx_ws_public_service.turnover_24h_cache.get(symbol, 0)
                    
                    # 🔍 [V15.7.7] Volume Fallback: Fetch from REST if cache is zero (happens on startup)
                    if turnover_24h < 1000000:
                        try:
                            ticker_resp = await okx_rest_service.get_tickers(symbol=symbol.replace(".P", ""))
                            ticker_data = ticker_resp.get("result", {}).get("list", [{}])[0]
                            turnover_24h = float(ticker_data.get("turnover24h", 0))
                            okx_ws_public_service.turnover_24h_cache[symbol] = turnover_24h 
                            logger.info(f"📊 [V15.7.7] Volume Fallback for {symbol}: ${turnover_24h/1000000:.1f}M")
                        except Exception as e:
                            logger.warning(f"Failed turnover fallback for {symbol}: {e}")

                    # 🔍 [V15.6] Volume Filter: Liquidity Guard
                    # [V96.1] Mínimo de $1M - RELAXADO para $100k em PAPER MODE para ver sinais rolando
                    is_swing_macro_s3 = candidate.get('is_swing_macro', False)
                    if _settings.OKX_EXECUTION_MODE == "PAPER":
                        volume_min = 100000 # $100k is enough for simulation
                    else:
                        volume_min = 500000 if is_swing_macro_s3 else 1000000  # $1M / $500k
                    
                    if turnover_24h < volume_min:
                        reason = f"Low Volume (${turnover_24h/1000000:.1f}M < ${volume_min/1000000:.1f}M)"
                        # logger.info(f"🚫 [V15.6] {symbol} rejected: {reason}")
                        self.recent_rejections.append({"symbol": symbol, "reason": reason, "timestamp": time.time()})
                        # return None
                    
                    # LS Ratio Filter: Contradiction check (V15.6 Hardening)
                    # Se varejo está muito comprado (LS > 1.5), evitamos Longs. Se muito vendido (LS < 0.8), evitamos Shorts.
                    if side_label == "Long" and ls_ratio > 1.5: # V16.1: Slightly relaxed (was 1.3)
                        logger.info(f"🚫 [V15.6] {symbol} rejected: Very high LS Ratio ({ls_ratio:.2f})")
                        # return None
                    if side_label == "Short" and ls_ratio < 0.7: # V16.1: Slightly relaxed (was 0.8)
                        logger.info(f"🚫 [V15.6] {symbol} rejected: Very low LS Ratio ({ls_ratio:.2f})")
                        # return None
                        
                    # 1. Macro & Trend Confluence
                    trend_1h = candidate.get('trend', 'sideways')
                    trend_2h = macro_2h.get('trend', 'sideways')  # Agora retorna BULLISH_ARMED, BEARISH_ARMED ou NEUTRAL
                    
                    # [V28.1/V33.1] SMA Master Shield (2H Crossover)
                    # [V33.1] Decorrelation plays are exempt — counter-trend IS the edge
                    master_shield_penalty = 0
                    trend_bonus = 0
                    btc_macro_dir = btc_dir.get('direction', 'NEUTRAL')
                    btc_macro_str = btc_dir.get('strength', 0)
                    is_decorrelation_play_s3 = candidate.get('is_decorrelated', False)
                    is_exempt = is_decorrelation_play_s3 or is_dvap_play or is_flex_mode
                    
                    if is_exempt:
                        master_shield_penalty = 0
                        trend_bonus = 0
                        logger.info(f"🎯 [V110.999] {symbol} (DVAP={is_dvap_play}, FLEX={is_flex_mode}) — SMA Shield SKIPPED")
                    elif is_swing_macro_s3:
                        trend_bonus += 15  # [V40.2] Reduced from 25 to 15 (less free pass)
                        logger.info(f"🌊 [V40.2] {symbol} HYBRID SWING — SMA Shield Aligned (bonus reduced)")
                    elif side_label == "Long":
                        if trend_2h == "BEARISH_ARMED":
                            master_shield_penalty = -25 # [V42.0] Relaxed from -50 to -25
                            logger.info(f"🛡️ [SMA MASTER SHIELD] {symbol} Penalty: LONG vs BEARISH_ARMED 2H (Relaxed)")
                        elif trend_2h == "BULLISH_ARMED":
                            trend_bonus += 15
                    elif side_label == "Short":
                        if trend_2h == "BULLISH_ARMED":
                            # [V33.1] If BTC is DOWN strongly, the 2H bullish crossover is lagging
                            if btc_macro_dir == "DOWN" and btc_macro_str > 30:
                                master_shield_penalty = -10 # [V42.0] Relaxed from -15
                                logger.info(f"🛡️ [SMA MASTER SHIELD V33.1] {symbol} RELAXED: SHORT vs BULLISH_ARMED 2H (BTC DOWN override)")
                            else:
                                master_shield_penalty = -25 # [V42.0] Relaxed from -50
                                logger.info(f"🛡️ [SMA MASTER SHIELD] {symbol} Penalty: SHORT vs BULLISH_ARMED 2H (Relaxed)")
                        elif trend_2h == "BEARISH_ARMED":
                            trend_bonus += 15
                    
                    # Fallback old simple trend alignment for 1H
                    if (side_label == "Long" and trend_1h == "bullish") or (side_label == "Short" and trend_1h == "bearish"):
                        trend_bonus += 10
                    elif (side_label == "Long" and trend_1h == "bearish") or (side_label == "Short" and trend_1h == "bullish"):
                        trend_bonus -= 10
                        
                    # 4H EMA penalty
                    ema20_4h = trend_4h.get('ema20', 0)
                    current_price_4h = trend_4h.get('current_price', 0)
                    ema4h_penalty = 0
                    if ema20_4h > 0 and current_price_4h > 0:
                        pct_from_ema4h = ((current_price_4h - ema20_4h) / ema20_4h) * 100
                        if side_label == 'Long' and pct_from_ema4h < -1.0: ema4h_penalty = -15
                        elif side_label == 'Short' and pct_from_ema4h > 1.0: ema4h_penalty = -15
                        elif side_label == 'Long' and pct_from_ema4h < 0: ema4h_penalty = -5
                        elif side_label == 'Short' and pct_from_ema4h > 0: ema4h_penalty = -5
                    
                    # 15m Zone bonus
                    near_zone = zones_15m.get('near_zone', False)
                    zone_distance = zones_15m.get('distance_to_zone_pct', 100)
                    zone_bonus = 10 if near_zone else 5 if zone_distance <= 1.0 else -10 if zone_distance > 2.5 else 0
                    self._diag_counters['zone_pass'] += 1
                    
                    # [V15.5] LS Ratio Bonus/Penalty
                    ls_bonus = 0
                    if (side_label == "Long" and ls_ratio < 0.9) or (side_label == "Short" and ls_ratio > 1.5):
                        ls_bonus = 10 # Institutional favor
                    
                    # [V16.5] Fleet Intelligence Consensus
                    fleet_confluence = await self._get_fleet_confluence_score(symbol)
                    fleet_bonus = fleet_confluence.get("score", 0)
                    
                    # Final Score
                    # [V20.4] Removed +15 magic inflation — scores now reflect true quality
                    # [V27.0] Phase 3: Add Daily Macro, Market Regime, and BTC Direction influence
                    
                    # Daily Macro Penalty/Bonus
                    daily_penalty = 0
                    daily_trend = daily_macro.get('trend', 'sideways')
                    
                    # [V33.1] Decorrelation plays are BY DEFINITION counter-trend
                    # — penalizing them for going against the daily is redundant and kills the signal
                    is_decorrelation_play = candidate.get('is_decorrelated', False)
                    is_exempt = is_decorrelation_play or is_dvap_play or is_flex_mode
                    
                    # [V28.2 PAPER FIX] Penalidade relaxada de -40 para -15 quando em OKX_EXECUTION_MODE = PAPER
                    # Para permitir testes de reversão SWING no Simulador.
                    fatal_penalty = -15 if _settings.OKX_EXECUTION_MODE == 'PAPER' else -40
                    
                    if is_exempt or is_decorrelation_play:
                        daily_penalty = 0  # [V110.999] Exempt: decorrelation/DVAP/FLEX is the edge
                        logger.info(f"🎯 [V33.1] {symbol} Decorrelation Play — Daily penalty SKIPPED (counter-trend is expected)")
                    elif is_swing_macro_s3:
                        # [V40.2] HYBRID: Reactivate partial daily penalty — if daily contradicts, reduce score
                        if (side_label == 'Long' and daily_trend == 'bearish') or (side_label == 'Short' and daily_trend == 'bullish'):
                            daily_penalty = -15  # [V40.2] Reduced from bypass to -15 (was 0)
                            logger.info(f"🌊 [V40.2] {symbol} HYBRID SWING — Daily CONTRA-TREND penalty -15 (was bypassed)")
                        else:
                            daily_penalty = 5  # Small bonus for alignment
                            logger.info(f"🌊 [V40.2] {symbol} HYBRID SWING — Daily aligned (+5)")
                    else:
                        # [V43.1] FAST RECOVERY RECOVERY: If BTC 1h/15m is UP, relax daily bearish penalty
                        btc_up_strong = btc_dir.get('direction') == 'UP' and btc_dir.get('strength', 0) > 20
                        
                        if side_label == 'Long' and daily_trend == 'bearish':
                            if btc_up_strong:
                                daily_penalty = -15 # [V43.1] Relaxed from fatal_penalty (-40) to -15
                                logger.info(f"🚀 [V43.1] {symbol} DAILY PENALTY RELAXED: BTC is moving UP (${btc_dir.get('strength')}) despite Bearish Daily.")
                            else:
                                daily_penalty = fatal_penalty
                        elif side_label == 'Short' and daily_trend == 'bullish':
                            daily_penalty = fatal_penalty
                        elif (side_label == 'Long' and daily_trend == 'bullish') or (side_label == 'Short' and daily_trend == 'bearish'):
                            daily_penalty = 10  # Aligned with Daily trend = bonus
                    
                    # Market Regime Adjustment & V27.6 MTF Alignment Penalty
                    regime_penalty = 0
                    regime = market_regime.get('regime', 'TRANSITION')
                    if regime == 'RANGING':
                        regime_penalty = -10  # Ranging markets = more cautious
                    elif regime == 'TRENDING':
                        regime_penalty = 5  # Trending markets = bonus confidence
                        # [V27.6] MTF Alignment: If trending hard (ADX>25), block counter-trend wicks
                        # [V33.1] Decorrelation/DVAP/FLEX plays are exempt — counter-trend IS expected
                        if market_regime.get('adx', 0) > 25 and not is_exempt:
                            if side_label == 'Long' and trend_4h.get('trend') == 'bearish':
                                regime_penalty -= 50 # Fatal penalty for counter-trend in heavy flow
                                logger.info(f"🚫 [V27.6] MTF Alignment: {symbol} Long ignored against strong Bearish 4H (ADX > 25)")
                            elif side_label == 'Short' and trend_4h.get('trend') == 'bullish':
                                # [V33.1] Relax for shorts aligned with BTC DOWN macro direction
                                if btc_macro_dir == 'DOWN' and btc_macro_str > 30:
                                    regime_penalty -= 15
                                    logger.info(f"🛡️ [V33.1 MTF] {symbol} Short vs Bullish 4H RELAXED (-15): BTC DOWN overrides 4H lag")
                                else:
                                    regime_penalty -= 50
                                    logger.info(f"🚫 [V27.6] MTF Alignment: {symbol} Short ignored against strong Bullish 4H (ADX > 25)")
                        elif is_exempt:
                            logger.info(f"🎯 [V110.999] {symbol} Exempt Play — MTF Penalty SKIPPED")
                    
                    # [V41.0] BTC GUARD — Penalidade Inteligente (não mais fatal para sinais fortes)
                    # Sinais fracos contra BTC = mortos. Sinais fortes contra BTC = penalidade severa.
                    btc_aligned = btc_dir.get('aligned_with', 'Both')
                    btc_strength = btc_dir.get('strength', 0)
                    btc_penalty = 0
                    
                    if btc_aligned != 'Both' and btc_strength > 30:
                        if (side_label == 'Long' and btc_aligned == 'Short') or (side_label == 'Short' and btc_aligned == 'Long'):
                            # [V42.0] Sharper Crash Protection: Block bypass if BTC is dumping
                            btc_dumping = okx_ws_public_service.btc_variation_15m < -0.4 or okx_ws_public_service.btc_variation_1h < -0.6
                            
                            if is_decorrelation_play and not btc_dumping:
                                logger.info(f"🎯 [V41.0] {symbol} (Decorrelation Play) IGNOROU O GUARDA DO BTC.")
                            else:
                                if is_decorrelation_play and btc_dumping:
                                    logger.warning(f"⚠️ [V42.0] {symbol} Decorrelation bypass REVOKED: BTC is dumping ({okx_ws_public_service.btc_variation_15m:.2f}%)")
                                
                                # [V41.0] Calcular score projetado para decidir se matar ou penalizar
                                projected_score = int(candidate['tactical_score'] + zone_bonus + ema4h_penalty + ls_bonus + fleet_bonus + daily_penalty + regime_penalty + btc_penalty + master_shield_penalty)
                                if projected_score >= 65:  # [V41.1] Adjusted to 65
                                    btc_penalty = -40  # [V42.0] Increased from -20 to -40
                                    logger.warning(f"⚠️ [V42.0] {symbol} {side_label} CONTRA BTC ({btc_aligned}) mas SCORE FORTE ({projected_score}). Penalidade -40 aplicada.")
                                else:
                                    reason = f"Contra BTC ({btc_aligned}) e score projetado baixo ({projected_score})"
                                    logger.warning(f"🚫 [V42.0] {symbol} {side_label} CONTRA BTC ({btc_aligned}). {reason}. ABORTADO.")
                                    self.recent_rejections.append({"symbol": symbol, "reason": reason, "timestamp": time.time()})
                                    # return None  # 💀 Score fraco + contra BTC = morte
                        elif (side_label == 'Long' and btc_aligned == 'Long') or (side_label == 'Short' and btc_aligned == 'Short'):
                            btc_penalty = 10  # BTC supports our direction
                    
                    final_score = int(candidate['tactical_score'] + zone_bonus + ema4h_penalty + ls_bonus + fleet_bonus + daily_penalty + regime_penalty + btc_penalty + master_shield_penalty)
                    
                    # [V27.6] Sniper Zone Bonus: Rejection touching EMA50 or SMA200
                    if final_score > 0 and daily_macro.get('ema50', 0) > 0:
                         price_to_ema = abs(current_price_4h - daily_macro['ema50']) / daily_macro['ema50'] * 100
                         if price_to_ema < 0.5 and daily_penalty > 0: # Close to EMA and aligned with trend
                             final_score += 15
                             logger.info(f"🌟 [V27.6] Golden Zone Bonus: {symbol} touches EMA50 perfectly aligned.")

                    final_score = max(10, min(99, final_score))
                    
                    # [V111.4] SHORT BIAS — SHORT WR 49.12% vs LONG 47.18% no Sandbox
                    if side_label == "Short" and getattr(settings, 'SHORT_BIAS_ACTIVE', True):
                        short_boost = getattr(settings, 'SHORT_BIAS_BOOST', 8)
                        if short_boost:
                            final_score += short_boost
                            logger.info(f"📊 [SHORT-BIAS] {symbol} Short +{short_boost} pts → final_score={min(99, final_score)}")
                    
                    # [V41.1] SESSION AWARENESS: Penalidade/bônus baseado no horário
                    from datetime import datetime, timezone
                    hour_utc = datetime.now(timezone.utc).hour
                    if 0 <= hour_utc < 8:  # Sessão Asiática — [V91.0] Penalidade removida (Almirante em UTC-3)
                        pass  # final_score -= 10  # [V91.0] DISABLED: Matava sinais noturnos no Brasil
                    elif 14 <= hour_utc < 21:  # Sessão US — maior volume, melhores tendências
                        final_score += 5
                    final_score = max(10, min(99, final_score))
                    if is_dvap_play or is_lrt_play or is_fas_play:
                        final_score = 98
                        logger.info(f"💎 [PRIORITY STRATEGY BOOST] final_score forcado para {final_score} ({strategy_class}) para garantir execucao imediata!")
                    
                    # Shadow Needle Detection (uses 1m klines)
                    current_price_ws = okx_ws_public_service.get_current_price(symbol)
                    is_stretched, stretch_val = await self.is_price_stretched(symbol, current_price_ws)
                    
                    cvd_5m_ws = okx_ws_public_service.get_cvd_score_time(symbol, 300)
                    
                    if final_score >= min_threshold:
                        self._diag_counters['score_pass'] += 1
                    else:
                        # [V110.7] Shadow Mode Capture
                        if final_score >= anticipation_min:
                            shadow_data = {
                                "symbol": normalize_symbol(symbol),
                                "side": "Buy" if side_label == "Long" else "Sell",
                                "score": final_score,
                                "entry_price": current_price_ws, # [V110.7] Entry captured for Desktop ROI Study
                                "reason": "PRE-SIGNAL",
                                "indicators": {
                                    "cvd": round(cvd_val, 0),
                                    "cvd_5m": round(cvd_5m_ws, 2),
                                    "rsi": round(candidate['rsi'], 1),
                                    "trend_2h": macro_2h.get('trend', 'NEUTRAL')
                                },
                                "timestamp": time.time()
                            }
                            self.anticipation_signals.append(shadow_data)
                            logger.info(f"🕶️ [SHADOW] {symbol} {side_label} Score {final_score} captured for Desktop HUD.")
                        
                        logger.info(f"⏭️ [V41.1] {symbol} {side_label} Score {final_score} < {min_threshold}. Rejeitado para execução real.")
                        # return None
                        
                    # V15.3: Calcular targets estruturais e espaço restante
                    current_price_now = okx_ws_public_service.get_current_price(symbol)
                    if current_price_now <= 0:
                        current_price_now = current_price_ws
                    if current_price_now <= 0:
                        current_price_now = macro_2h.get('current_price', 0)
                    
                    if is_dvap_play and dvap_targets:
                        structural_target = dvap_targets["tp1"]
                        target_extended = dvap_targets["tp2"]
                        if side_label == 'Long':
                            move_room_pct = ((structural_target - current_price_now) / current_price_now * 100) if structural_target > current_price_now else 0.5
                        else:
                            move_room_pct = ((current_price_now - structural_target) / current_price_now * 100) if current_price_now > structural_target else 0.5
                        logger.info(f"📐 [DVAP FIBO TARGETS] TP1={structural_target:.6f} | TP2={target_extended:.6f} | Room={move_room_pct:.2f}%")
                    elif side_label == 'Long':
                        # [V41.1] Use target_long_ext (pivot + 2×ATR) for more realistic move room
                        structural_target = macro_2h.get('target_long_ext', macro_2h.get('target_long', 0))
                        target_extended = macro_2h.get('target_long_ext', 0)
                        move_room_pct = ((structural_target - current_price_now) / current_price_now * 100) if structural_target > current_price_now else 0
                    else:
                        # [V41.1] Use target_short_ext (pivot - 2×ATR) for more realistic move room
                        structural_target = macro_2h.get('target_short_ext', macro_2h.get('target_short', 0))
                        target_extended = macro_2h.get('target_short_ext', 0)
                        move_room_pct = ((current_price_now - structural_target) / current_price_now * 100) if structural_target > 0 and structural_target < current_price_now else 0
                    
                    # [V39.0] Dynamic Room Filter:
                    # - TRAP signals need 2.0% (contrarian entry needs compression room)
                    # - SWING MACRO signals need 1.5% (quality gate for slow timeframe)
                    # - All others minimum 0.5%
                    is_trap_signal = candidate.get('trap_exploited', False)
                    is_swing_macro_signal = candidate.get('is_swing_macro', False)
                    if is_trap_signal:
                        min_room = 2.0
                    elif is_swing_macro_signal:
                        min_room = 1.5
                    else:
                        min_room = 0.5
                    
                    # [V42.0] Relax move room for Longs in a Bullish BTC environment
                    if side_label == 'Long' and btc_macro_dir == 'UP' and move_room_pct < min_room:
                        min_room = 0.3 # Allow entries with less room if trend is strong
                        logger.info(f"🌊 [V42.0] {symbol} Long Move Room RELAXED to 0.3% due to BTC UP trend.")
                    
                    if move_room_pct < min_room:
                        logger.info(f"🚫 [V39.0] {symbol} rejeitado: move_room={move_room_pct:.2f}% (< {min_room}%). Target={structural_target:.6f} Price={current_price_now:.6f} | TRAP={is_trap_signal} SWING={is_swing_macro_signal}")
                        # return None
                    
                    # Dedup: Skip if recently signaled with similar score (but ALWAYS allow SNIPER checks to proceed)
                    norm_cached_check = normalize_symbol(symbol)
                    last_sig = self.last_sent_signals.get(norm_cached_check)
                    # [V31.0] Dedup relaxed from 180s to 90s for faster re-entry opportunities
                    if last_sig and (time.time() - last_sig['timestamp'] < 60) and (final_score - last_sig['score'] <= 5):
                        if last_sig.get('is_sniper', False):
                            return None
                    
                    # ═══════════════════════════════════════════════════
                    # [V25.1] ENTRY CONFIRMATION PROTOCOL — 2-Layer System
                    # ═══════════════════════════════════════════════════
                    side_for_trigger = "Buy" if side_label == "Long" else "Sell"
                    trigger_result = await self.get_5m_entry_triggers(symbol, side_for_trigger, zones_15m)
                    
                    if trigger_result['has_trigger']:
                        # SNIPER LAYER: Confirmed entry with 5m price action
                        signal_layer = "SNIPER"
                        # Boost score for precision entries
                        trigger_bonus = int(trigger_result['confidence'] * 0.15)
                        final_score = min(99, final_score + trigger_bonus)
                        logger.info(
                            f"🎯 [V27.6] SNIPER TRIGGER: {symbol} {side_label} | "
                            f"Type: {trigger_result['trigger_type']} | "
                            f"Confidence: {trigger_result['confidence']:.0f}%"
                        )
                    else:
                        # MOMENTUM LAYER: Good signal but no confirmed trigger
                        signal_layer = "MOMENTUM"
                        # [V27.6] SNIPER-ONLY Restriction for $5M - $1M pairs
                        if turnover_24h < 1000000 and _settings.OKX_EXECUTION_MODE != 'PAPER' and not candidate.get('is_swing_macro'):
                            logger.info(f"🚫 [V27.6] {symbol} MOMENTUM Blocked: Pairs under $1M must be SNIPER-ONLY. turnover=${turnover_24h/1000000:.1f}M")
                            # return None
                            
                        # Funding contradiction is a hard block for Momentum layer
                        if trigger_result.get('funding_contradiction'):
                            logger.info(f"🚫 [V25.1] {symbol} MOMENTUM blocked: Funding contradiction ({trigger_result['funding_rate']*100:.4f}%)")
                            # return None
                    
                    
                    # Cache the normalized symbol to avoid dupe processing
                    norm_cached = normalize_symbol(symbol)
                    self.last_sent_signals[norm_cached] = {'score': final_score, 'timestamp': time.time(), 'is_sniper': signal_layer == "SNIPER"}
                    self._diag_counters['queued'] += 1
                    
                    rsi = candidate['rsi']
                    
                    # V15.9: Pattern Classification for TradeAnalyst learning
                    trend_1h = candidate.get('trend', 'sideways')
                    trend_2h = macro_2h.get('trend', 'sideways')
                    # [V31.0] Decorrelation Play has highest priority in pattern classification
                    if candidate.get('is_decorrelated', False):
                        entry_pattern = "decorrelation_play"
                    elif is_stretched:
                        entry_pattern = "shadow_needle"
                    elif candidate.get('whale_bonus', 0) > 0:
                        entry_pattern = "whale_spike"
                    elif near_zone and zone_distance <= 0.5:
                        entry_pattern = "zone_reaction"
                    elif (side_label == "Long" and trend_1h == "bullish" and trend_2h == "bullish") or \
                         (side_label == "Short" and trend_1h == "bearish" and trend_2h == "bearish"):
                        entry_pattern = "trend_continuation"
                    elif (side_label == "Long" and rsi < 35) or (side_label == "Short" and rsi > 65):
                        entry_pattern = "reversal_bounce"
                    elif abs(cvd_val) > 100000:
                        entry_pattern = "momentum_breakout"
                    elif (side_label == "Long" and trend_1h == "bearish") or \
                         (side_label == "Short" and trend_1h == "bullish"):
                        entry_pattern = "counter_trend"
                    else:
                        entry_pattern = "standard"
                    
                    # [V42.0] Fetch Max Leverage for display in Radar
                    inst_info = await okx_rest_service.get_instrument_info(symbol)
                    max_lev = float(inst_info.get("leverageFilter", {}).get("maxLeverage", 50.0))
                    
                    norm_symbol = normalize_symbol(symbol) # Ensure norm_symbol is defined

                    # [V20.4 FIX] Obter informações detalhadas do contrato para PnL correto
                    try:
                        contract_info = await okx_rest_service.get_detailed_contract_info(symbol)
                        ct_val = contract_info.get("contract_details", {}).get("ctVal", 1.0)
                        lot_size = contract_info.get("contract_details", {}).get("lotSize", 1.0)
                        min_qty = contract_info.get("contract_details", {}).get("minQty", 1.0)
                        tick_size = contract_info.get("contract_details", {}).get("tickSize", 0.01)
                        risk_impact = contract_info.get("risk_analysis", {}).get("price_impact_per_contract", 0)
                        min_margin = contract_info.get("risk_analysis", {}).get("min_margin_required", 0)
                    except Exception as contract_err:
                        logger.warning(f"Failed to get contract info for {symbol}: {contract_err}")
                        ct_val = 1.0
                        lot_size = 1.0
                        min_qty = 1.0
                        tick_size = 0.01
                        risk_impact = 0
                        min_margin = 0
                    
                    signal_data = {
                        "id": f"sig_{int(time.time())}_{norm_symbol}",
                        "symbol": norm_symbol, 
                        "score": final_score, 
                        "type": "SHADOW_V25.1",
                        "leverage": max_lev, # [V42.0] Exposing for Radar Badge
                        "side": "Buy" if side_label == "Long" else "Sell",  # [V27.1] Exposing side for Captain
                        "entry_price_signal": current_price_now,
                        # [SANDBOX] Stop Loss fixado matematicamente em -50% ROI (5% de recuo no preco para 10x)
                        "suggested_sl": current_price_now * 0.95 if side_label == "Long" else current_price_now * 1.05,
                        "layer": "SNIPER" if (is_dvap_play or is_mola_play) else signal_layer,  # [V25.1] SNIPER or MOMENTUM
                        "is_shadow_strike": candidate.get('is_shadow_strike', False),
                        "is_trend_surf": trigger_result.get('is_trend_surf', False),
                        "market_environment": "Bullish" if cvd_val > 0 else "Bearish",
                        "market_regime": market_regime.get('regime', 'TRANSITION'),
                        "execution_style": "ATTACK" if market_regime.get("adx", 20) >= 28 else "AMBUSH",
                        "current_adx": market_regime.get("adx", 20),
                        "strategy_class": strategy_class,
                        "is_elite": True if (is_dvap_play or is_mola_play) else (signal_layer == "SNIPER"),
                        "reasoning": (
                            f"{'💎 DVAP REVERSAL | ' if is_dvap_play else ''}"
                            f"{'🦇 SHADOW STRIKE | ' if candidate.get('is_shadow_strike') else ''}"
                            f"{'🎯 SNIPER' if (is_dvap_play or signal_layer == 'SNIPER') else '⚡ MOMENTUM'} {side_label} | "
                            f"Trigger: {'CHoCH 30M' if is_dvap_play else trigger_result.get('trigger_type', 'NONE')} | "
                            f"CVD: {cvd_val/1000:,.1f}k | "
                            f"Funding: {trigger_result.get('funding_rate', 0)*100:.4f}% | "
                            f"Room: {move_room_pct:.1f}%"
                            + (f" | ⚡ SHADOW" if is_stretched else "")
                        ),
                        "indicators": {
                            "cvd": round(cvd_val, 4),
                            "cvd_5m": round(cvd_5m_ws, 2),
                            "rsi": round(rsi, 2),
                            "trend_1h": candidate.get('trend', 'sideways'),
                            "trend_2h_macro": macro_2h.get('trend', 'sideways'),
                            "pivot_2h": macro_2h.get('pivot_low' if side_label == 'Long' else 'pivot_high', 0),
                            "sma20_2h": macro_2h.get('sma20', 0),
                            "pattern": entry_pattern,
                            "fleet_intelligence": {
                                "total_bonus": fleet_bonus,
                                "macro_risk": fleet_confluence.get("macro_risk"),
                                "sentiment_score": fleet_confluence.get("sentiment"),
                                "whale_bias": fleet_confluence.get("whale_bias")
                            },
                            "ema4h_penalty": ema4h_penalty,
                            "ls_ratio": round(ls_ratio, 2),
                            "open_interest": oi_val,
                            "turnover_24h": round(turnover_24h, 2),
                            "zone_bonus": zone_bonus,
                            "scanned_at": datetime.now(timezone.utc).isoformat(),
                            "is_shadow_needle": is_stretched,
                            "stretch_pct": round(stretch_val, 2),
                            "strategy_type": strategy_class,
                            "atr": okx_ws_public_service.atr_cache.get(symbol, 0),
                            "structural_target": round(structural_target, 8),
                            "target_extended": round(target_extended, 8),
                            "move_room_pct": round(move_room_pct, 3),
                            "atr_2h": macro_2h.get('atr_2h', 0),
                            # [V25.1] New Entry Confirmation Protocol data
                            "funding_rate": trigger_result.get('funding_rate', 0),
                            "trigger_type": trigger_result.get('trigger_type'),
                            "trigger_confidence": trigger_result.get('confidence', 0),
                            "volume_confirmed": trigger_result.get('volume_confirmed', False),
                            # [V42.0] RANGING Sniper Identifiers
                            "is_ranging_sniper": candidate.get('v42_pattern', {}).get('detected', False),
                            "v42_pattern": candidate.get('v42_pattern', {'detected': False}),
                            "is_market_ranging": candidate.get('is_market_ranging', False), # [V42.9]
                            # [V31.0] Decorrelation Hunter data
                            "decorrelation_play": candidate.get('is_decorrelated', False),
                            "decorrelation_data": candidate.get('decorrelation_data')
                        },
                        # [V39.0] Swing Macro flag — TOCAIA uses this to extend patience to 60min
                        "is_swing_macro": True if (is_dvap_play or is_mola_play) else candidate.get('is_swing_macro', False),
                        # [V20.4 FIX] Informações detalhadas do contrato para cálculo correto de PnL
                        "contract_info": {
                            "ctVal": ct_val,
                            "lotSize": lot_size,
                            "minQty": min_qty,
                            "tickSize": tick_size,
                            "riskImpactPerContract": risk_impact,
                            "minMarginRequired": min_margin,
                            "symbol": symbol
                        },
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                    await firebase_service.log_signal(signal_data)
                    if self.signal_queue:
                        # [V110.118] PriorityQueue: (-score, counter, data) para processar maior score primeiro
                        # O 'counter' garante desempate sem comparar dicionários (evita TypeError)
                        self._signal_counter += 1
                        await self.signal_queue.put((-final_score, self._signal_counter, signal_data))
                    else:
                        logger.error("❌ [SIG-GEN] signal_queue is None durante put!")

                    layer_icon = "🎯" if signal_layer == "SNIPER" else "⚡"
                    logger.info(
                        f"{layer_icon} [V25.1] {signal_layer}: {norm_symbol} {side_label} | "
                        f"Score: {final_score} | Trigger: {trigger_result.get('trigger_type', 'NONE')} | "
                        f"Target: {structural_target:.6f} (+{move_room_pct:.1f}%) | "
                        f"Funding: {trigger_result.get('funding_rate', 0)*100:.4f}%"
                    )

                    # [V15.0] Sync to RTDB Radar Pulse (Instant & Real-time)
                    await self._sync_radar_rtdb()

                    return final_score
                    return None
                
                # Run Stage 3 in parallel
                if stage2_candidates:
                    await asyncio.gather(*(stage3_validate(c) for c in stage2_candidates))

                # ═══════════════════════════════════════════════════════════════
                # ████ DIAGNÓSTICO DO FUNIL (a cada 60s) ████
                # ═══════════════════════════════════════════════════════════════
                now_diag = time.time()
                # V15.7.1: Increase diagnostic frequency to 30s for better transparency (was 60s)
                if now_diag - self._last_diag_log > 30:
                    c = self._diag_counters
                    # Count candidates from current loop state
                    s1_count = len(stage1_candidates)
                    s2_count = len(stage2_candidates)
                    logger.info(
                        f"📊 [V14.0 FUNNEL] {len(active_symbols_ws)} → "
                        f"S1:{s1_count} → S2:{s2_count} → "
                        f"Score✅:{c['score_pass']} → Queued:{c['queued']} | "
                        f"CVD:{c['cvd_pass']} RSI:{c.get('rsi_pass',0)} "
                        f"Trend:{c['trend1h_pass']} EMA4H:{c['ema4h_pass']} Zone:{c['zone_pass']}"
                    )
                    self._diag_counters = {k: 0 for k in self._diag_counters}
                    self._last_diag_log = now_diag

                await asyncio.sleep(self.scan_interval)
                
            except Exception as e:
                logger.error(f"Error in Signal Generator loop: {e}")
                import traceback
                traceback.print_exc()
    async def radar_loop(self):
        """
        High-performance loop to update the Market Radar in RTDB.
        Runs independently of Signal generation.
        """
        logger.info("Market Radar (200 pairs) active via RTDB.")
        
        # V12.1: Wait for system to be ready (prevents race condition)
        while not self.is_running:
            await asyncio.sleep(1)
            
        while self.is_running:
            try:
                # Get blocked symbols from vault cycle
                cycle_status = await vault_service.get_cycle_status()
                used_symbols = [s.upper() for s in cycle_status.get("used_symbols_in_cycle", [])]
                
                radar_batch = {}
                active_symbols = okx_ws_public_service.active_symbols
                
                for symbol in active_symbols:
                    norm_sym = symbol.replace(".P", "").replace(".p", "").upper()
                    cvd = okx_ws_public_service.get_cvd_score(symbol)
                    cvd_5m = okx_ws_public_service.get_cvd_score_time(symbol, 300) # 5m window
                    
                    # Radar Heuristic: $500k USD delta = 99% intensity
                    if settings.OKX_EXECUTION_MODE == "PAPER":
                        # Em PAPER, reduzimos o threshold para preencher as cores e gerar a disputa visual no Radar
                        import random
                        score = min(99, max(30, int(abs(cvd) / 500) + random.randint(10, 40)))
                        side_val = "LONG" if cvd > 500 else "SHORT" if cvd < -500 else random.choice(["LONG", "SHORT"])
                    else:
                        score = min(99, int(abs(cvd) / 5000))
                        side_val = "LONG" if cvd > 10000 else "SHORT" if cvd < -10000 else "NEUTRAL"
                    
                    # Fetch enriched metrics
                    rsi = okx_ws_public_service.rsi_cache.get(symbol, 50)
                    trend_data = self.trend_cache.get(symbol, {})
                    trend = trend_data.get('trend', 'sideways')
                    
                    # [V45.2] Regime Context (ADX)
                    regime_data = self.market_regime_cache.get(symbol, {})
                    adx_val = regime_data.get("adx", 20)
                    
                    # Check if blocked in cycle
                    is_blocked = norm_sym in used_symbols
                    
                    # [V46.0] Real-time Liquidity & Retail Sentiment
                    ls_ratio = okx_ws_public_service.ls_ratio_cache.get(symbol, 1.0)
                    oi_prev = okx_ws_public_service.oi_cache.get(symbol, 0)
                    
                    # [V45.2] RTDB Keys: No dots. We use clean norm_sym.
                    radar_batch[norm_sym] = { 
                        "cvd": round(cvd, 2),
                        "cvd_5m": round(cvd_5m, 2),
                        "cvd_total": max(100000, abs(cvd)), # Baseline for meter
                        "adx": adx_val,
                        "adx_slope": trend_data.get("adx_slope", 0), # Pull from cache if exists
                        "score": score,
                        "rsi": round(rsi, 1),
                        "ls_ratio": round(ls_ratio, 2),
                        "trend": trend,
                        "is_blocked": is_blocked,
                        "side": side_val
                    }
                
                if radar_batch:
                    await firebase_service.update_radar_batch(radar_batch)
                    # V15.7.5: Increased frequency of status logs for better transparency (30s)
                    if time.time() - getattr(self, '_last_radar_log', 0) > 30:
                        logger.info(f"📡 [RADAR-RT] Batch updated with {len(radar_batch)} assets. Syncing...")
                        self._last_radar_log = time.time()
                else:
                    # V15.7.5: Increased frequency (30s) and added more detail for empty batches
                    if time.time() - getattr(self, '_last_radar_empty_log', 0) > 30:
                        logger.warning(f"⚠️ [RADAR-RT] Batch is EMPTY. Active symbols: {len(active_symbols)}. Check BybitWS connection.")
                        self._last_radar_empty_log = time.time()
                
                await asyncio.sleep(self.radar_interval)

                # V15.1.3: Periodic Radar Pulse Sync (independent of signal funnel)
                # Ensures frontend Radar always shows latest signals from Firestore
                if time.time() - getattr(self, '_last_radar_pulse_sync', 0) > 5:
                    try:
                        # 2. Find replacement candidates
                        recent_signals = await firebase_service.get_recent_signals(limit=20)
                        best_opportunity = None
                        
                        for r_data in recent_signals:
                            r_sym = r_data.get('symbol')
                            if not r_sym: continue
                            # Optimization: only check high confidence signals
                            if r_data.get('score', 0) < 80: continue
                            
                            d_res = await self.detect_btc_decorrelation(r_sym)
                            if d_res.get('is_decorrelated') and d_res.get('confidence', 0) >= 70:
                                best_opportunity = r_data
                                break
                        await self._sync_radar_rtdb()
                        self._last_radar_pulse_sync = time.time()
                    except Exception as rp_err:
                        logger.warning(f"⚠️ [RADAR-PULSE] Sync error: {rp_err}")
                
            except Exception as e:
                logger.error(f"Error in radar_loop: {e}")
                await asyncio.sleep(10)

    async def track_outcomes(self):
        """
        Periodically checks older signals to see if they were 'Win' or 'Loss'.
        """
        logger.info("Signal Outcome Tracker started.")
        while self.is_running:
            try:
                signals = await firebase_service.get_recent_signals(limit=50)
                now = datetime.now(timezone.utc)
                for signal in signals:
                    if signal.get("outcome") is not None:
                        continue
                    
                    ts_str = signal.get("timestamp")
                    if not ts_str:
                        continue
                        
                    try:
                        # Normalize string to include timezone info
                        if ts_str.endswith("Z"):
                            ts_str = ts_str.replace("Z", "+00:00")
                        
                        ts = datetime.fromisoformat(ts_str)
                        
                        # Ensure ts is aware
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=timezone.utc)
                            
                        if (now - ts) > timedelta(minutes=5):
                            # Use the centralized service to handle .P suffix
                            ticker_resp = await okx_rest_service.get_tickers(symbol=signal["symbol"])
                            ticker_data = ticker_resp.get("result", {}).get("list", [{}])[0]
                            current_price = float(ticker_data.get("lastPrice", 0))
                            
                            # V15.9: Fix — determine win based on signal direction
                            signal_side = signal.get("side", "Buy").lower()
                            entry_price = float(signal.get("entry_price", signal.get("price", 0)))
                            if entry_price > 0 and current_price > 0:
                                if signal_side == "buy":
                                    is_win = current_price > entry_price
                                else:
                                    is_win = current_price < entry_price
                            else:
                                is_win = False
                            await firebase_service.update_signal_outcome(signal["id"], is_win)
                            logger.info(f"Signal outcome tracked for {signal['symbol']}: {'WIN' if is_win else 'LOSS'}")
                    except Exception as ts_err:
                        logger.error(f"Error parsing signal time {ts_str}: {ts_err}")

                await asyncio.sleep(300)
            except Exception as e:
                logger.error(f"Error in Outcome Tracker: {e}")
                await asyncio.sleep(60)

    def calculate_rsi(self, prices, period=14):
        """Calcula o RSI (IFR) clássico usando Pandas"""
        import pandas as pd
        df = pd.Series(prices)
        delta = df.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi.fillna(50).tolist()

    def check_ifr_divergence(self, closes, highs, lows, period=14):
        """
        [V110.999] Detecta divergências clássicas no RSI(14)
        """
        if len(closes) < 30:
            return None
            
        rsi = self.calculate_rsi(closes, period)
        last_idx = len(closes) - 1
        
        # Bullish Divergence: Preço caindo (fundos menores), RSI subindo (fundos maiores) na sobrevenda (< 35)
        fundos_preco = []
        for i in range(last_idx - 15, last_idx - 1):
            if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
                fundos_preco.append((i, lows[i], rsi[i]))
                
        if len(fundos_preco) >= 2:
            fundos_preco = fundos_preco[-2:]
            f1, f2 = fundos_preco[0], fundos_preco[1]
            if f2[1] < f1[1] and f2[2] > f1[2] and f2[2] < 35:
                return "BULLISH"

        # Bearish Divergence: Preço subindo (topos maiores), RSI caindo (topos menores) na sobrecompra (> 65)
        topos_preco = []
        for i in range(last_idx - 15, last_idx - 1):
            if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
                topos_preco.append((i, highs[i], rsi[i]))
                
        if len(topos_preco) >= 2:
            topos_preco = topos_preco[-2:]
            t1, t2 = topos_preco[0], topos_preco[1]
            if t2[1] > t1[1] and t2[2] < t1[2] and t2[2] > 65:
                return "BEARISH"
                
        return None

    def check_volume_climax(self, volumes, period=20, std_multiplier=1.8):
        """
        [V110.999] Verifica se o volume recente foi climático (absorção).
        Robustamente adaptado para considerar o pico no próprio fundo/topo da divergência (offset de até 3 candles)
        e usando limite dinâmico de 1.8 desvios padrão ou 1.8x a média (Relative Volume).
        """
        import pandas as pd
        if len(volumes) < period:
            return False
            
        vol_series = pd.Series(volumes[:-1])
        mean_vol = vol_series.rolling(period).mean().iloc[-1]
        std_vol = vol_series.rolling(period).std().iloc[-1]
        
        # 1. Standard deviation threshold
        threshold_std = mean_vol + (std_multiplier * std_vol)
        # 2. Relative volume threshold (1.8x mean volume is a massive spike)
        threshold_rel = mean_vol * 1.8
        
        final_threshold = min(threshold_std, threshold_rel)
        
        # O clímax de volume capitulação costuma ocorrer no candle do próprio fundo/topo (L-3 ou L-4)
        # ou na confirmação (L-2). Por isso pegamos o volume máximo entre os últimos 3 candles fechados.
        target_volume = max(volumes[-2], volumes[-3], volumes[-4])
        
        return target_volume > final_threshold

    def find_pivots_30m(self, highs, lows, window=2):
        """
        [V110.999] Identifica Topos (Pivot High) e Fundos (Pivot Low) locais
        """
        length = len(highs)
        pivot_highs = []
        pivot_lows = []
        
        for i in range(window, length - window):
            is_high = True
            for w in range(1, window + 1):
                if highs[i] <= highs[i-w] or highs[i] <= highs[i+w]:
                    is_high = False
                    break
            if is_high:
                pivot_highs.append(highs[i])
                
            is_low = True
            for w in range(1, window + 1):
                if lows[i] >= lows[i-w] or lows[i] >= lows[i+w]:
                    is_low = False
                    break
            if is_low:
                pivot_lows.append(lows[i])
                
        last_high = pivot_highs[-1] if pivot_highs else highs[-2]
        last_low = pivot_lows[-1] if pivot_lows else lows[-2]
        
        return last_high, last_low

    def calculate_fibonacci_targets(self, signal_type, entry_price, stop_loss):
        """
        [V110.999] Calcula as expansões de Fibonacci (1.618 e 2.618) com base na amplitude do CHoCH.
        """
        amplitude = abs(entry_price - stop_loss)
        
        if signal_type == "BUY":
            tp1 = entry_price + (amplitude * 1.618)
            tp2 = entry_price + (amplitude * 2.618)
        else:
            tp1 = entry_price - (amplitude * 1.618)
            tp2 = entry_price - (amplitude * 2.618)
            
        return round(tp1, 6), round(tp2, 6)

    def _load_auto_blocks(self):
        """[V100.1] Loads the persistent blocklist from disk."""
        import json
        self.auto_blocked_assets = {}
        if os.path.exists(self.BLOCKLIST_STORAGE_FILE):
            try:
                with open(self.BLOCKLIST_STORAGE_FILE, 'r') as f:
                    data = json.load(f)
                    # Convert old format (float) to new format (dict) if needed
                    for s, t in data.items():
                        if isinstance(t, (int, float)):
                            self.auto_blocked_assets[s] = {'blocked_until': t, 'consecutive_losses': 1}
                        else:
                            self.auto_blocked_assets[s] = t
                
                # Cleanup expired blocks
                now = time.time()
                self.auto_blocked_assets = {s: d for s, d in self.auto_blocked_assets.items() 
                                          if d.get('blocked_until', 0) > now}
            except Exception as e:
                logger.error(f"Error loading auto_blocks: {e}")

    def _save_auto_blocks(self):
        """[V100.1] Saves the persistent blocklist to disk."""
        import json
        try:
            with open(self.BLOCKLIST_STORAGE_FILE, 'w') as f:
                json.dump(self.auto_blocked_assets, f)
        except Exception as e:
            logger.error(f"Error saving auto_blocks: {e}")

    async def is_symbol_blocked(self, symbol: str) -> tuple:
        """[V100.1] Checks if a symbol is currently blocked (permanently or temporarily)."""
        norm = symbol.replace(".P", "").upper()
        if norm in self.asset_blocklist_permanent:
            return True, 999999
        
        # Check auto blocks
        now = time.time()
        block = self.auto_blocked_assets.get(norm, {})
        expiry = block.get('blocked_until', 0)
        if expiry > now:
            return True, int(expiry - now)
            
        return False, 0

signal_generator = SignalGenerator()
