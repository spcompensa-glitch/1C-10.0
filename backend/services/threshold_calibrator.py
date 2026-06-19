# -*- coding: utf-8 -*-
"""
[V110.113] THRESHOLD CALIBRATOR
Sistema de calibração automática de thresholds baseado em backtesting.

FUNCIONAMENTO:
1. A cada 24h, roda backtest dos últimos 7 dias
2. Testa combinações de thresholds (Score, M-ADX, CVD, Volume)
3. Encontra combinação que maximiza Profit Factor (lucro/prejuízo)
4. Atualiza thresholds ativos no signal_generator
5. Persiste histórico no Firestore

GUARDRAILS:
- Nunca muda mais de 10% por vez
- Só recalibra se tiver 50+ trades no histórico
- Se backtest inconclusivo → mantém thresholds anteriores
- DESATIVADO POR PADRÃO (ativar manualmente via config)
"""

import logging
import time
import asyncio
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
import json

logger = logging.getLogger("ThresholdCalibrator")

# Thresholds Padrão (V110.113)
DEFAULT_THRESHOLDS = {
    "min_score": 90,
    "min_m_adx": 28,
    "min_cvd": 15000,
    "min_volume_24h": 1000000,  # $1M
}

# Faixas Permitidas
THRESHOLD_RANGES = {
    "min_score": {"min": 75, "max": 92, "step": 1},
    "min_m_adx": {"min": 20, "max": 35, "step": 1},
    "min_cvd": {"min": 10000, "max": 40000, "step": 2500},
    "min_volume_24h": {"min": 500000, "max": 3000000, "step": 250000},
}

# Limites de Mudança (max 10% por vez)
MAX_CHANGE_PCT = 0.10

class ThresholdCalibrator:
    """
    [V110.113] Gerencia calibração automática de thresholds.
    """
    
    def __init__(self):
        self.enabled = False  # Desativado por padrão
        self.last_calibration = 0
        self.calibration_interval = 86400  # 24h
        self.active_thresholds = DEFAULT_THRESHOLDS.copy()
        self.threshold_history = []  # Histórico de calibrações
        self._trade_history_cache = []
        self._cache_updated_at = 0
        
    def get_threshold(self, key: str) -> Any:
        """Retorna threshold ativo atual."""
        return self.active_thresholds.get(key, DEFAULT_THRESHOLDS.get(key))
    
    async def initialize(self):
        """Carrega thresholds persistidos do Firestore."""
        try:
            from services.firebase_service import firebase_service
            if not firebase_service.is_active:
                await firebase_service.initialize()
            
            if firebase_service.is_active:
                doc = firebase_service.get_doc("system/thresholds")
                if doc and doc.get("exists"):
                    data = doc.get("data", {})
                    self.active_thresholds = data.get("active", DEFAULT_THRESHOLDS)
                    self.threshold_history = data.get("history", [])
                    self.last_calibration = data.get("last_calibration", 0)
                    self.enabled = data.get("enabled", False)
                    logger.info(f"📊 [THRESH-CAL] Thresholds carregados: {self.active_thresholds}")
        except Exception as e:
            logger.error(f"Error loading thresholds: {e}")
            self.active_thresholds = DEFAULT_THRESHOLDS.copy()
    
    async def persist_thresholds(self):
        """Salva thresholds ativos no Firestore."""
        try:
            from services.firebase_service import firebase_service
            if not firebase_service.is_active:
                return False
            
            data = {
                "active": self.active_thresholds,
                "history": self.threshold_history[-20:],  # Últimas 20 calibrações
                "last_calibration": self.last_calibration,
                "enabled": self.enabled,
                "updated_at": time.time()
            }
            
            firebase_service.set_doc("system/thresholds", data)
            logger.info(f"💾 [THRESH-CAL] Thresholds persistidos no Firestore")
            return True
        except Exception as e:
            logger.error(f"Error persisting thresholds: {e}")
            return False
    
    def should_calibrate(self) -> bool:
        """Verifica se é hora de recalibrar."""
        if not self.enabled:
            return False
        
        now = time.time()
        return now - self.last_calibration >= self.calibration_interval
    
    async def _load_trade_history(self) -> List[Dict]:
        """Carrega histórico de trades dos últimos 7 dias."""
        now = time.time()
        # Cache por 1 hora
        if self._cache_updated_at and (now - self._cache_updated_at) < 3600:
            return self._trade_history_cache
        
        try:
            from services.firebase_service import firebase_service
            if not firebase_service.is_active:
                return []
            
            # Buscar trade_history dos últimos 7 dias
            seven_days_go = now - (7 * 86400)
            trades = firebase_service.get_collection("trade_history")
            
            # Filtrar trades recentes
            recent_trades = []
            for trade in trades:
                closed_at = trade.get("closed_at", 0)
                if isinstance(closed_at, str):
                    # Converter string para timestamp
                    try:
                        dt = datetime.fromisoformat(closed_at.replace("Z", "+00:00"))
                        closed_at = dt.timestamp()
                    except:
                        closed_at = 0
                
                if closed_at >= seven_days_go:
                    recent_trades.append(trade)
            
            self._trade_history_cache = recent_trades
            self._cache_updated_at = now
            
            logger.info(f"📊 [THRESH-CAL] Carregados {len(recent_trades)} trades dos últimos 7 dias")
            return recent_trades
            
        except Exception as e:
            logger.error(f"Error loading trade history: {e}")
            return []
    
    def _calculate_profit_factor(self, trades: List[Dict], thresholds: Dict) -> float:
        """
        Calcula Profit Factor simulado com thresholds testados.
        Simula quais trades teriam sido executados com esses thresholds.
        """
        if not trades:
            return 0.0
        
        total_profit = 0.0
        total_loss = 0.0
        
        min_score = thresholds["min_score"]
        min_cvd = thresholds["min_cvd"]
        
        for trade in trades:
            score = trade.get("score", 0)
            cvd = abs(trade.get("cvd_local", 0))
            pnl = trade.get("pnl", 0) or trade.get("roi", 0)
            
            # Simula se trade teria entrado com esses thresholds
            if score >= min_score and cvd >= min_cvd:
                if pnl > 0:
                    total_profit += pnl
                else:
                    total_loss += abs(pnl)
        
        if total_loss == 0:
            return total_profit if total_profit > 0 else 0.0
        
        return total_profit / total_loss
    
    async def run_calibration(self) -> Dict[str, Any]:
        """
        Roda calibração completa.
        Retorna melhor combinação de thresholds.
        """
        logger.info("🔧 [THRESH-CAL] Iniciando calibração de thresholds...")
        
        # 1. Carregar histórico
        trade_history = await self._load_trade_history()
        
        if len(trade_history) < 50:
            logger.warning(f"⚠️ [THRESH-CAL] Histórico insuficiente ({len(trade_history)} trades). Mínimo: 50")
            return {"success": False, "reason": "Insufficient trade history"}
        
        # 2. Gerar combinações de thresholds para testar
        combinations = self._generate_combinations()
        
        if not combinations:
            return {"success": False, "reason": "No valid combinations"}
        
        logger.info(f"🧪 [THRESH-CAL] Testando {len(combinations)} combinações de thresholds...")
        
        # 3. Testar cada combinação
        best_pf = 0.0
        best_combo = self.active_thresholds.copy()
        results = []
        
        for i, combo in enumerate(combinations):
            pf = self._calculate_profit_factor(trade_history, combo)
            
            results.append({
                "combo": combo,
                "profit_factor": pf,
                "trade_count": len([t for t in trade_history if t.get("score", 0) >= combo["min_score"]])
            })
            
            if pf > best_pf:
                best_pf = pf
                best_combo = combo
            
            if (i + 1) % 10 == 0:
                logger.debug(f"  Progresso: {i+1}/{len(combinations)} | Best PF: {best_pf:.2f}")
        
        # 4. Ordenar resultados
        results.sort(key=lambda x: x["profit_factor"], reverse=True)
        top_5 = results[:5]
        
        logger.info(f"🏆 [THRESH-CAL] Melhor Profit Factor: {best_pf:.2f}")
        for i, res in enumerate(top_5):
            logger.info(f"  #{i+1}: PF={res['profit_factor']:.2f} | {res['combo']}")
        
        # 5. Aplicar guardrails (max 10% de mudança)
        calibrated = self._apply_guardrails(best_combo)
        
        # 6. Atualizar thresholds ativos
        old_thresholds = self.active_thresholds.copy()
        self.active_thresholds = calibrated
        self.last_calibration = time.time()
        
        # 7. Adicionar ao histórico
        self.threshold_history.append({
            "timestamp": self.last_calibration,
            "old": old_thresholds,
            "new": calibrated,
            "profit_factor": best_pf,
            "trade_count": len(trade_history),
            "top_5": top_5
        })
        
        # 8. Persistir
        await self.persist_thresholds()
        
        logger.info(f"✅ [THRESH-CAL] Calibração concluída!")
        logger.info(f"  Anterior: {old_thresholds}")
        logger.info(f"  Novo: {calibrated}")
        
        return {
            "success": True,
            "old_thresholds": old_thresholds,
            "new_thresholds": calibrated,
            "profit_factor": best_pf,
            "trade_count": len(trade_history),
            "top_5": top_5
        }
    
    def _generate_combinations(self) -> List[Dict]:
        """
        Gera combinações de thresholds para testar.
        Usa amostragem inteligente (não força bruta total).
        """
        combinations = []
        
        # Amostragem: testa valores em intervalos estratégicos
        score_values = list(range(75, 93, 2))  # 75, 77, 79, ..., 91
        adx_values = list(range(20, 36, 3))     # 20, 23, 26, ..., 35
        cvd_values = [10000, 15000, 20000, 25000, 30000, 40000]
        vol_values = [500000, 1000000, 1500000, 2000000, 3000000]
        
        # Combinações completas (pode ser grande, limitar a ~100)
        for score in score_values:
            for adx in adx_values:
                for cvd in cvd_values:
                    for vol in vol_values:
                        combinations.append({
                            "min_score": score,
                            "min_m_adx": adx,
                            "min_cvd": cvd,
                            "min_volume_24h": vol
                        })
                        
                        if len(combinations) >= 200:
                            return combinations
        
        return combinations
    
    def _apply_guardrails(self, calibrated: Dict) -> Dict:
        """
        Aplica guardrails: muda no máximo 10% por vez.
        """
        result = {}
        
        for key in DEFAULT_THRESHOLDS.keys():
            old_val = self.active_thresholds.get(key, DEFAULT_THRESHOLDS[key])
            new_val = calibrated.get(key, old_val)
            
            # Calcular máximo de mudança
            if old_val > 0:
                max_change = old_val * MAX_CHANGE_PCT
                # Limitar mudança
                if new_val > old_val + max_change:
                    new_val = old_val + max_change
                elif new_val < old_val - max_change:
                    new_val = old_val - max_change
            
            # Arredondar para step válido
            step = THRESHOLD_RANGES[key]["step"]
            new_val = round(new_val / step) * step
            
            # Garantir dentro da faixa
            new_val = max(THRESHOLD_RANGES[key]["min"], min(THRESHOLD_RANGES[key]["max"], new_val))
            
            # Converter para int se necessário
            if isinstance(old_val, int):
                new_val = int(new_val)
            
            result[key] = new_val
        
        return result
    
    def enable(self):
        """Ativa calibração automática."""
        self.enabled = True
        logger.info("🔛 [THRESH-CAL] Calibração automática ATIVADA")
    
    def disable(self):
        """Desativa calibração automática."""
        self.enabled = False
        logger.info("🔒 [THRESH-CAL] Calibração automática DESATIVADA")
    
    def reset_to_defaults(self):
        """Reseta thresholds para valores padrão."""
        self.active_thresholds = DEFAULT_THRESHOLDS.copy()
        self.last_calibration = 0
        logger.info("🔄 [THRESH-CAL] Thresholds resetados para padrão")


# Instância global
threshold_calibrator = ThresholdCalibrator()
