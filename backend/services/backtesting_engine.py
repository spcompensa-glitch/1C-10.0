# -*- coding: utf-8 -*-
"""
V27.0 Phase 4: Backtesting Engine
Replay histórico de sinais para validar estratégia.
Comparação de performance: SNIPER vs MOMENTUM historicamente.
Otimização de parâmetros (score threshold, SL phases).
"""

import asyncio
import logging
import time
import json
import os
from datetime import datetime, timezone, timedelta
from config import settings

logger = logging.getLogger("BacktestEngine")


class HistoricalDataFetcher:
    """
    Downloads and caches historical kline data from Bybit REST API.
    Bybit limits to 200 candles per request, so we paginate automatically.
    """
    
    CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', 'backtest_cache')
    
    def __init__(self):
        os.makedirs(self.CACHE_DIR, exist_ok=True)
    
    def _cache_path(self, symbol: str, interval: str) -> str:
        clean_symbol = symbol.replace('.P', '').replace('/', '_')
        return os.path.join(self.CACHE_DIR, f"{clean_symbol}_{interval}.json")
    
    async def fetch_klines(self, symbol: str, interval: str = "60", days: int = 90) -> list:
        """
        Fetches historical klines for a symbol.
        Returns chronological list of candles: [timestamp, open, high, low, close, volume, turnover]
        """
        from services.okx_rest import okx_rest_service
        
        cache_path = self._cache_path(symbol, interval)
        
        # Check cache (valid for 24 hours)
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r') as f:
                    cached = json.load(f)
                if time.time() - cached.get('fetched_at', 0) < 86400:  # 24h
                    logger.info(f"📂 [Backtest] Using cached data for {symbol} ({len(cached['candles'])} candles)")
                    return cached['candles']
            except Exception:
                pass
        
        # Calculate time range
        end_time = int(time.time() * 1000)
        start_time = end_time - (days * 24 * 3600 * 1000)
        
        all_candles = []
        current_end = end_time
        batch_count = 0
        max_batches = 50  # Safety limit
        
        logger.info(f"🔄 [Backtest] Fetching {days} days of {interval} data for {symbol}...")
        
        while current_end > start_time and batch_count < max_batches:
            try:
                klines = await okx_rest_service.get_klines(
                    symbol=symbol,
                    interval=interval,
                    limit=200
                )
                
                if not klines or len(klines) == 0:
                    break
                
                # Bybit returns newest first, so reverse for chronological
                batch = klines[::-1]
                all_candles = batch + all_candles
                
                # Move end time to before the oldest candle in this batch
                oldest_ts = int(klines[-1][0])
                if oldest_ts >= current_end:
                    break  # No progress
                current_end = oldest_ts
                
                batch_count += 1
                await asyncio.sleep(0.2)  # Rate limit protection
                
            except Exception as e:
                logger.error(f"Error fetching klines batch {batch_count}: {e}")
                break
        
        # Deduplicate by timestamp and sort chronologically
        seen = set()
        unique_candles = []
        for c in all_candles:
            ts = c[0]
            if ts not in seen:
                seen.add(ts)
                unique_candles.append(c)
        
        unique_candles.sort(key=lambda x: int(x[0]))
        
        # Cache results
        try:
            with open(cache_path, 'w') as f:
                json.dump({'candles': unique_candles, 'fetched_at': time.time(), 'symbol': symbol}, f)
        except Exception as e:
            logger.warning(f"Failed to cache klines: {e}")
        
        logger.info(f"✅ [Backtest] Fetched {len(unique_candles)} candles for {symbol} ({batch_count} API calls)")
        return unique_candles


class BacktestResult:
    """Structured backtest result with all performance metrics."""
    
    def __init__(self):
        self.trades = []
        self.total_trades = 0
        self.wins = 0
        self.losses = 0
        self.total_pnl = 0.0
        self.max_drawdown = 0.0
        self.peak_equity = 0.0
        self.sharpe_ratio = 0.0
        self.sniper_stats = {'trades': 0, 'wins': 0, 'pnl': 0.0}
        self.momentum_stats = {'trades': 0, 'wins': 0, 'pnl': 0.0}
        self.best_params = {}
    
    @property
    def win_rate(self) -> float:
        return (self.wins / self.total_trades * 100) if self.total_trades > 0 else 0
    
    def to_dict(self) -> dict:
        return {
            'total_trades': self.total_trades,
            'wins': self.wins,
            'losses': self.losses,
            'win_rate': round(self.win_rate, 2),
            'total_pnl': round(self.total_pnl, 2),
            'max_drawdown': round(self.max_drawdown, 2),
            'sharpe_ratio': round(self.sharpe_ratio, 4),
            'sniper': {
                'trades': self.sniper_stats['trades'],
                'wins': self.sniper_stats['wins'],
                'win_rate': round(self.sniper_stats['wins'] / max(1, self.sniper_stats['trades']) * 100, 2),
                'pnl': round(self.sniper_stats['pnl'], 2)
            },
            'momentum': {
                'trades': self.momentum_stats['trades'],
                'wins': self.momentum_stats['wins'],
                'win_rate': round(self.momentum_stats['wins'] / max(1, self.momentum_stats['trades']) * 100, 2),
                'pnl': round(self.momentum_stats['pnl'], 2)
            },
            'best_params': self.best_params,
            'recent_trades': self.trades[-20:]  # Last 20 trades for UI display
        }


class BacktestEngine:
    """
    V27.0: Full backtesting engine that replays historical data through the signal generation
    and execution protocol to simulate trading performance.
    """
    
    def __init__(self):
        self.data_fetcher = HistoricalDataFetcher()
        self.is_running = False
        self.last_result = None
        self.progress = 0  # 0-100%
    
    async def run_backtest(
        self,
        symbols: list = None,
        days: int = 30,
        initial_balance: float = 10.0,
        risk_per_trade: float = 0.10,  # 10%
        leverage: int = 50,
        score_threshold: int = 60,
        sniper_target_roi: float = 2.0,  # 2% = 100% ROI at 50x
        sl_percent: float = 1.0  # 1% SL
    ) -> BacktestResult:
        """
        Runs a full backtest simulation.
        
        Args:
            symbols: List of symbols to test (default: top 5 by volume)
            days: Number of days of historical data
            initial_balance: Starting bankroll in USD
            risk_per_trade: Fraction of bankroll per trade (e.g., 0.10 = 10%)
            leverage: Trading leverage
            score_threshold: Minimum signal score to enter
            sniper_target_roi: Target ROI % for SNIPER exits
            sl_percent: Stop Loss % from entry
        """
        self.is_running = True
        self.progress = 0
        result = BacktestResult()
        
        if not symbols:
            symbols = ["ETHUSDT.P", "SOLUSDT.P", "XRPUSDT.P", "DOGEUSDT.P", "BNBUSDT.P"]
        
        balance = initial_balance
        peak = initial_balance
        pnl_list = []
        
        logger.info(f"🧪 [Backtest] Starting: {len(symbols)} symbols, {days} days, ${initial_balance} balance, {score_threshold} threshold")
        
        for sym_idx, symbol in enumerate(symbols):
            try:
                # Fetch 1H candles for signal simulation
                candles_1h = await self.data_fetcher.fetch_klines(symbol, "60", days)
                # Fetch 4H candles for trend
                candles_4h = await self.data_fetcher.fetch_klines(symbol, "240", days)
                
                if len(candles_1h) < 50:
                    logger.warning(f"[Backtest] Not enough data for {symbol}")
                    continue
                
                # Simulate signal generation on each 1H candle
                position = None  # {'side', 'entry', 'sl', 'tp', 'layer', 'entry_time'}
                
                for i in range(26, len(candles_1h)):
                    # Progress tracking
                    total_work = len(symbols) * len(candles_1h)
                    done_work = sym_idx * len(candles_1h) + i
                    self.progress = int(done_work / total_work * 100)
                    
                    current = candles_1h[i]
                    price = float(current[4])  # Close price
                    high = float(current[2])
                    low = float(current[3])
                    timestamp = int(current[0])
                    
                    # If we have a position, check for exit
                    if position:
                        entry = position['entry']
                        sl = position['sl']
                        tp = position['tp']
                        side = position['side']
                        
                        # Check SL hit
                        sl_hit = (side == 'Long' and low <= sl) or (side == 'Short' and high >= sl)
                        # Check TP hit
                        tp_hit = (side == 'Long' and high >= tp) or (side == 'Short' and low <= tp)
                        
                        if sl_hit or tp_hit:
                            if tp_hit and not sl_hit:
                                exit_price = tp
                                reason = 'TP_HIT'
                            else:
                                exit_price = sl
                                reason = 'SL_HIT'
                            
                            # Calculate PnL
                            margin = balance * risk_per_trade
                            if side == 'Long':
                                pnl_pct = (exit_price - entry) / entry
                            else:
                                pnl_pct = (entry - exit_price) / entry
                            
                            pnl_usd = pnl_pct * leverage * margin
                            balance += pnl_usd
                            
                            is_win = pnl_usd > 0
                            result.total_trades += 1
                            if is_win:
                                result.wins += 1
                            else:
                                result.losses += 1
                            result.total_pnl += pnl_usd
                            pnl_list.append(pnl_usd)
                            
                            # Track by layer
                            layer = position.get('layer', 'MOMENTUM')
                            if layer == 'SNIPER':
                                result.sniper_stats['trades'] += 1
                                result.sniper_stats['pnl'] += pnl_usd
                                if is_win: result.sniper_stats['wins'] += 1
                            else:
                                result.momentum_stats['trades'] += 1
                                result.momentum_stats['pnl'] += pnl_usd
                                if is_win: result.momentum_stats['wins'] += 1
                            
                            # Track drawdown
                            if balance > peak:
                                peak = balance
                            dd = (peak - balance) / peak * 100 if peak > 0 else 0
                            if dd > result.max_drawdown:
                                result.max_drawdown = dd
                            
                            result.trades.append({
                                'symbol': symbol,
                                'side': side,
                                'layer': layer,
                                'entry': entry,
                                'exit': exit_price,
                                'pnl': round(pnl_usd, 2),
                                'reason': reason,
                                'timestamp': timestamp,
                                'balance_after': round(balance, 2)
                            })
                            
                            position = None
                            continue
                    
                    # No position — check for entry signal
                    if position is None and balance > 1.0:
                        score = self._simulate_score(candles_1h, candles_4h, i)
                        
                        if score >= score_threshold:
                            # Determine side from recent momentum
                            recent_closes = [float(candles_1h[j][4]) for j in range(max(0, i-5), i+1)]
                            momentum = (recent_closes[-1] - recent_closes[0]) / recent_closes[0] * 100 if recent_closes[0] > 0 else 0
                            
                            side = 'Long' if momentum > 0 else 'Short'
                            entry_price = price
                            
                            # SL and TP
                            if side == 'Long':
                                sl_price = entry_price * (1 - sl_percent / 100)
                                tp_price = entry_price * (1 + sniper_target_roi / 100)
                            else:
                                sl_price = entry_price * (1 + sl_percent / 100)
                                tp_price = entry_price * (1 - sniper_target_roi / 100)
                            
                            # Determine layer (SNIPER if score >= 75, MOMENTUM otherwise)
                            layer = 'SNIPER' if score >= 75 else 'MOMENTUM'
                            
                            position = {
                                'side': side,
                                'entry': entry_price,
                                'sl': sl_price,
                                'tp': tp_price,
                                'layer': layer,
                                'entry_time': timestamp
                            }
                
            except Exception as e:
                logger.error(f"[Backtest] Error processing {symbol}: {e}")
                continue
        
        # Calculate Sharpe Ratio
        if pnl_list and len(pnl_list) > 1:
            avg_pnl = sum(pnl_list) / len(pnl_list)
            variance = sum((p - avg_pnl) ** 2 for p in pnl_list) / len(pnl_list)
            std_dev = variance ** 0.5
            result.sharpe_ratio = (avg_pnl / std_dev) if std_dev > 0 else 0
        
        result.peak_equity = peak
        result.best_params = {
            'score_threshold': score_threshold,
            'sniper_target_roi': sniper_target_roi,
            'sl_percent': sl_percent,
            'leverage': leverage,
            'risk_per_trade': risk_per_trade
        }
        
        self.last_result = result
        self.is_running = False
        self.progress = 100
        
        logger.info(
            f"✅ [Backtest] Complete: {result.total_trades} trades, "
            f"Win Rate: {result.win_rate:.1f}%, "
            f"PnL: ${result.total_pnl:.2f}, "
            f"Max DD: {result.max_drawdown:.1f}%, "
            f"Sharpe: {result.sharpe_ratio:.4f}"
        )
        
        return result
    
    def _simulate_score(self, candles_1h: list, candles_4h: list, current_index: int) -> int:
        """
        Simulates a signal score based on multiple technical indicators.
        This is a simplified version of the live signal_generator for offline use.
        """
        try:
            # Get recent candles for analysis
            lookback = min(20, current_index)
            recent = candles_1h[current_index - lookback:current_index + 1]
            
            closes = [float(c[4]) for c in recent]
            highs = [float(c[2]) for c in recent]
            lows = [float(c[3]) for c in recent]
            volumes = [float(c[5]) for c in recent]
            
            if len(closes) < 10:
                return 0
            
            score = 50  # Base score
            
            # 1. RSI (14-period simplified)
            gains, losses_val = [], []
            for j in range(1, len(closes)):
                diff = closes[j] - closes[j-1]
                gains.append(max(0, diff))
                losses_val.append(max(0, -diff))
            
            avg_gain = sum(gains[-14:]) / 14 if len(gains) >= 14 else sum(gains) / max(1, len(gains))
            avg_loss = sum(losses_val[-14:]) / 14 if len(losses_val) >= 14 else sum(losses_val) / max(1, len(losses_val))
            
            rs = avg_gain / max(0.0001, avg_loss)
            rsi = 100 - (100 / (1 + rs))
            
            # RSI extreme = higher score (reversal play)
            if rsi < 30 or rsi > 70:
                score += 15
            elif rsi < 40 or rsi > 60:
                score += 5
            
            # 2. Volume spike (current vs average)
            if len(volumes) >= 10:
                avg_vol = sum(volumes[-10:]) / 10
                current_vol = volumes[-1]
                if current_vol > avg_vol * 1.5:
                    score += 10
            
            # 3. EMA trend alignment (8 vs 21)
            if len(closes) >= 21:
                ema8 = sum(closes[-8:]) / 8
                ema21 = sum(closes[-21:]) / 21
                if ema8 > ema21:
                    score += 5  # Bullish alignment
                elif ema8 < ema21:
                    score += 5  # Bearish alignment (both directions are tradeable)
            
            # 4. Price near support/resistance (zone proximity)
            recent_high = max(highs[-10:])
            recent_low = min(lows[-10:])
            current_price = closes[-1]
            range_size = recent_high - recent_low
            
            if range_size > 0:
                dist_to_support = (current_price - recent_low) / range_size
                dist_to_resistance = (recent_high - current_price) / range_size
                
                # Near zones = higher probability
                if dist_to_support < 0.2 or dist_to_resistance < 0.2:
                    score += 10
            
            # 5. 4H trend confirmation (if available)
            # Find matching 4H candle by timestamp
            current_ts = int(candles_1h[current_index][0])
            matching_4h = None
            for c4 in candles_4h:
                if abs(int(c4[0]) - current_ts) < 4 * 3600 * 1000:
                    matching_4h = c4
            
            if matching_4h:
                price_4h = float(matching_4h[4])
                # Simple trend check
                if abs(current_price - price_4h) / price_4h < 0.005:
                    score += 5  # Price aligned with 4H close
            
            # Clamp score
            return max(10, min(99, score))
            
        except Exception:
            return 0
    
    async def run_optimization(
        self,
        symbols: list = None,
        days: int = 30,
        initial_balance: float = 10.0
    ) -> dict:
        """
        Runs multiple backtests with different parameters to find optimal settings.
        Tests different score thresholds and TP/SL configurations.
        """
        self.is_running = True
        best_result = None
        best_sharpe = -999
        all_results = []
        
        # Parameter grid
        thresholds = [55, 60, 65, 70, 75]
        tp_values = [1.5, 2.0, 2.5, 3.0]
        sl_values = [0.8, 1.0, 1.2]
        
        total_configs = len(thresholds) * len(tp_values) * len(sl_values)
        config_count = 0
        
        logger.info(f"🔬 [Backtest] Starting optimization: {total_configs} configurations")
        
        for threshold in thresholds:
            for tp in tp_values:
                for sl in sl_values:
                    config_count += 1
                    self.progress = int(config_count / total_configs * 100)
                    
                    result = await self.run_backtest(
                        symbols=symbols,
                        days=days,
                        initial_balance=initial_balance,
                        score_threshold=threshold,
                        sniper_target_roi=tp,
                        sl_percent=sl
                    )
                    
                    summary = {
                        'threshold': threshold,
                        'tp': tp,
                        'sl': sl,
                        'trades': result.total_trades,
                        'win_rate': result.win_rate,
                        'pnl': result.total_pnl,
                        'sharpe': result.sharpe_ratio,
                        'max_dd': result.max_drawdown
                    }
                    all_results.append(summary)
                    
                    if result.sharpe_ratio > best_sharpe and result.total_trades >= 5:
                        best_sharpe = result.sharpe_ratio
                        best_result = summary
        
        self.is_running = False
        self.progress = 100
        
        optimization_result = {
            'best_config': best_result,
            'all_results': sorted(all_results, key=lambda x: x.get('sharpe', 0), reverse=True)[:10],
            'total_configs_tested': total_configs
        }
        
        logger.info(f"✅ [Backtest] Optimization complete. Best config: {best_result}")
        return optimization_result


# Singleton
backtest_engine = BacktestEngine()
