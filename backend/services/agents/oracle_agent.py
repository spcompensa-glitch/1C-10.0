import logging
import asyncio
import time
from typing import Dict, Any, List
from services.agents.aios_adapter import AIOSAgent
from services.firebase_service import firebase_service
from config import settings

logger = logging.getLogger("OracleAgent")

class OracleAgent(AIOSAgent):
    def __init__(self):
        super().__init__(
            agent_id="agent-oracle-v1",
            role="oracle",
            capabilities=["market_integrity", "amnesia_guard", "data_validation"]
        )
        self.boot_time = time.time()
        self.stabilization_period = 150 # 2.5 minutes (150s) - User requested 2-3 min
        self.market_context = {
            "regime": "TRANSITION",
            "btc_direction": "NEUTRAL",
            "btc_adx": 20.0,
            "btc_price": 0.0,
            "btc_variation_1h": 0.0,
            "btc_variation_24h": 0.0,
            "btc_variation_15m": 0.0,
            "dominance": 50.0,
            "status": "BOOTING",
            "is_stale": False,
            "last_updated": 0,
            "remaining_wait": 150
        }
        self.last_save_time = 0
        self._is_initialized = False

    async def initialize(self):
        if self._is_initialized: return
        
        # 🟢 Amnesia Guard: Load LKG from Firestore
        try:
            lkg_context = await firebase_service.get_oracle_context()
            if lkg_context:
                lkg_adx = lkg_context.get('btc_adx', 0)
                logger.info(f"🔮 [ORACLE] LKG Context Recovered: ADX {lkg_adx} | Direction: {lkg_context.get('btc_direction')}")
                
                # Update metrics
                self.market_context.update({
                    k: v for k, v in lkg_context.items() 
                    if k in [
                        "regime",
                        "btc_direction",
                        "btc_adx",
                        "btc_price",
                        "btc_variation_1h",
                        "btc_variation_15m",
                        "btc_variation_24h",
                        "dominance",
                    ]
                })
                self._refresh_market_labels()
                
                # ⚡ [V110.50] Amnesia Fast-Pass: If LKG is robust (>15 ADX), reduce stabilization wait to 15s
                if lkg_adx > 15:
                    logger.info("⚡ [ORACLE] Robust LKG detected. Shortening stabilization period to 15s.")
                    # Adjust boot_time so that uptime (now - boot_time) appears larger
                    self.boot_time = time.time() - (self.stabilization_period - 15)
                
                self.market_context["status"] = "BOOTING_RECOVERED"
        except Exception as e:
            logger.error(f"Failed to load LKG: {e}")
        
        self._is_initialized = True
        logger.info("🔮 Oracle Agent Initialized & Watching Data Integrity.")
        asyncio.create_task(self.run_loop())

    async def on_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = message.get("type")
        if msg_type == "GET_CONTEXT":
            return {"status": "SUCCESS", "data": self.get_validated_context()}
        return {"status": "ERROR", "message": "Unknown type"}

    def get_validated_context(self) -> Dict[str, Any]:
        """Returns the validated context with security rigor check (2-3 min wait)."""
        now = time.time()
        uptime = now - self.boot_time
        self._refresh_market_labels()
        
        # 🛡️ Rigor de Segurança: 2-3 min de espera após boot
        if uptime < self.stabilization_period:
            self.market_context["status"] = "STABILIZING"
            self.market_context["remaining_wait"] = int(self.stabilization_period - uptime)
            # Durante estabilização, os dados podem estar vindo do LKG ou brutos, mas status é STABILIZING
            # Isso impede que o Captain/Guardian tomem decisões até o fim do período.
        else:
            self.market_context["remaining_wait"] = 0
            # Check staleness (5 min)
            if (now - self.market_context["last_updated"]) > 300:
                self.market_context["status"] = "STALE_DATA"
                self.market_context["is_stale"] = True
            elif self.market_context.get("btc_adx", 0) <= 0.01:
                self.market_context["status"] = "ERROR_ZERO_ADX"
                self.market_context["is_stale"] = True
            else:
                self.market_context["status"] = "SECURE"
                self.market_context["is_stale"] = False
        
        self.market_context["boot_time"] = self.boot_time
        return self.market_context

    def _refresh_market_labels(self):
        """Deriva regime e direção do BTC usando a mesma grade do guardian."""
        adx = float(self.market_context.get("btc_adx", 0.0) or 0.0)
        var_1h = float(self.market_context.get("btc_variation_1h", 0.0) or 0.0)
        var_15m = float(self.market_context.get("btc_variation_15m", 0.0) or 0.0)

        if adx >= settings.ADX_STRONG_TREND_THRESHOLD:
            regime = "ROARING"
        elif adx >= settings.ADX_TRENDING_THRESHOLD:
            regime = "TRENDING"
        elif adx >= settings.ADX_MIN_ENTRY:
            regime = "TRANSITION"
        else:
            regime = "RANGING"

        direction = "LATERAL"
        if adx >= settings.ADX_MIN_ENTRY:
            if var_15m > 0 and var_1h > 0:
                direction = "UP"
            elif var_15m < 0 and var_1h < 0:
                direction = "DOWN"

        self.market_context["regime"] = regime
        self.market_context["btc_direction"] = direction

    async def update_market_data(self, source: str, data: dict):
        """Receives data from sources (BybitWS, SignalGenerator, MacroAnalyst)."""
        now = time.time()
        
        # 🛡️ Data Sanitization
        if "btc_adx" in data:
            new_adx = float(data["btc_adx"])
            
            # [AMNESIA-FIX] Reject Zero ADX entirely
            if new_adx <= 0.01:
                logger.warning(f"🔮 [ORACLE] Rejecting ZERO ADX Update: {new_adx}")
                del data["btc_adx"] # Remove to not update
            # [AMNESIA-FIX] Reject suspicious drops from relevant ADX to near 0
            elif self.market_context["btc_adx"] > 20 and new_adx < 10 and (now - self.boot_time > 60):
                 logger.warning(f"🔮 [ORACLE] Rejecting SUSPICIOUS ADX Drop: {self.market_context['btc_adx']} -> {new_adx}")
                 del data["btc_adx"]

        # Update core metrics
        for k, v in data.items():
            if k in self.market_context:
                self.market_context[k] = v
        self._refresh_market_labels()
        
        self.market_context["last_updated"] = now
        self.market_context["last_source"] = source
        
        # [V110.62] CRASH DETECTION (Guardian Hedge Trigger)
        var_15m = data.get("btc_variation_15m", 0)
        if var_15m < -2.0: # Queda de 2% em 15 min = Pânico
            logger.warning(f"🚨 [ORACLE-PANIC] Queda violenta detectada: {var_15m:.2f}% em 15m. Guardian Hedge desabilitado conforme User Rule (Sem BTC).")
        elif var_15m > -0.5: # Recuperação ou estabilização
             try:
                from services.bankroll import bankroll_manager
                if getattr(bankroll_manager, 'hedge_active', False):
                    asyncio.create_task(bankroll_manager.auto_close_hedge(reason="Market Stabilized"))
             except Exception:
                 pass

    async def run_loop(self):
        """Persistence loop for context backup (LKG)."""
        while True:
            try:
                context = self.get_validated_context()
                # Save LKG when stable and every 2 minutes
                if context["status"] == "SECURE" and (time.time() - self.last_save_time > 120):
                    await firebase_service.save_oracle_context(context)
                    self.last_save_time = time.time()
                    logger.info("🔮 [ORACLE] Market Snapshot Persisted (LKG).")
            except Exception as e:
                logger.error(f"Oracle Loop Error: {e}")
            await asyncio.sleep(60)

# Singleton instance
oracle_agent = OracleAgent()
