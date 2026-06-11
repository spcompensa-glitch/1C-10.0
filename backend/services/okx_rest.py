# -*- coding: utf-8 -*-
import asyncio
import logging
import time
import json
import os
import httpx
from datetime import datetime, timezone
from services.time_utils import get_br_iso_str
from typing import List, Dict, Any, Optional
from pybit.unified_trading import HTTP
from config import settings
from services.resilience import with_circuit_breaker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("OKXRest")

_GLOBAL_KLINES_CACHE = {}

class OKXRest:
    def __init__(self):
        self._global_session = None # Sessão padrão do admin (legado/fallback)
        self._user_sessions = {} # Cache de sessões: {username: HTTP_Session}
        self.category = "linear"  # TODO: substituir por OKX instType='SWAP' quando pybit for removido (dead code path)
        self.time_offset = 0
        self.is_initialized = False
        
        # Paper Trading State
        self.execution_mode = settings.OKX_EXECUTION_MODE # "REAL" or "PAPER"
        self.paper_balance = settings.OKX_SIMULATED_BALANCE
        self.paper_positions = [] # List of dicts matching Bybit schema
        self.paper_moonbags = [] # [V110.0] List of emancipated trades in Paper Mode
        self.paper_orders_history = [] 
        self._paper_engine_task = None
        self._instrument_cache = {} # Cache for tickSize and stepSize
        self._open_interest_cache = {}
        self._account_ratio_cache = {}
        self._account_ratio_locks = {}
        self._account_ratio_cache_ttl = float(os.getenv("OKX_ACCOUNT_RATIO_CACHE_TTL_SECONDS", "120"))
        self.last_balance = 0.0 # V5.2.4.6: Cache for non-blocking health checks
        # [V96.5] Path fix for Paper Mode persistence
        base_dir = os.path.dirname(os.path.abspath(__file__))
        backend_dir = os.path.dirname(base_dir) # One level up from services/
        self.PAPER_STORAGE_FILE = os.path.join(backend_dir, "paper_storage.json")
        self._last_paper_load_time = 0
        
        # V5.3.4: Closure Idempotency Shield
        self.pending_closures = set()
        # V5.4.0: Distributed Lock via RedisService
        from services.redis_service import redis_service
        self.redis = redis_service
        
        # [V43.0] Position Mode Cache (Hedge vs One-Way)
        self._position_mode_cache = {} # { symbol: mode_int }
        self.emancipating_symbols = set() # { symbol }
        self._http_semaphore = asyncio.Semaphore(80) # Internal/private calls keep their own guard.
        self._public_http_semaphore = asyncio.Semaphore(int(os.getenv("OKX_PUBLIC_MAX_CONCURRENCY", "4")))
        self._public_http_lock = asyncio.Lock()
        self._public_min_interval = float(os.getenv("OKX_PUBLIC_MIN_INTERVAL_SECONDS", "0.12"))
        self._rubik_min_interval = float(os.getenv("OKX_RUBIK_MIN_INTERVAL_SECONDS", "0.75"))
        self._public_429_base_cooldown = float(os.getenv("OKX_PUBLIC_429_BASE_COOLDOWN", "2.0"))
        self._public_next_request_at = 0.0
        self._public_cooldown_until = 0.0
        self._public_429_streak = 0
        self._paper_save_lock = asyncio.Lock() # [V110.23.2] Concurrency Shield for Paper Persistence
        self.is_ready = False # [V110.25.0] Ready flag for sync loop
        
        # [V43.2] Cache for Elite Pairs to prevent API saturation
        self._elite_cache = []
        self._elite_cache_time = 0
        self._elite_cache_ttl = 900 # 15 minutes

    async def _public_rate_limited_get(
        self,
        url: str,
        timeout: float = 5.0,
        label: str = "public",
        min_interval: Optional[float] = None,
    ):
        """Throttle OKX public REST calls across radar workers to avoid 429 bursts."""
        async with self._public_http_semaphore:
            async with self._public_http_lock:
                now = time.time()
                wait_for = max(self._public_cooldown_until - now, self._public_next_request_at - now, 0.0)
                if wait_for > 0:
                    await asyncio.sleep(wait_for)
                interval = max(self._public_min_interval, min_interval or 0.0)
                self._public_next_request_at = time.time() + interval

            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url)

            if response.status_code == 429:
                retry_after = self._parse_retry_after(response)
                async with self._public_http_lock:
                    self._public_429_streak = min(self._public_429_streak + 1, 5)
                    cooldown = retry_after or min(
                        self._public_429_base_cooldown * self._public_429_streak,
                        12.0,
                    )
                    self._public_cooldown_until = max(self._public_cooldown_until, time.time() + cooldown)
                logger.warning(
                    f"⚠️ [OKX-429-GATE] {label} limitado. "
                    f"Cooldown global {cooldown:.1f}s | streak={self._public_429_streak}"
                )
            elif response.status_code < 500:
                self._public_429_streak = max(0, self._public_429_streak - 1)

            return response

    def _parse_retry_after(self, response) -> float:
        try:
            raw = response.headers.get("Retry-After")
            if raw is None:
                return 0.0
            return max(0.0, float(raw))
        except Exception:
            return 0.0

    async def _load_paper_state(self):
        """[V110.23.5] Global Loader - loads paper positions and balance from Firestore. Resilient to Cloud Run restarts."""
        if self.execution_mode != "PAPER": return
        try:
            from services.firebase_service import firebase_service
            data = await firebase_service.get_paper_state()
            
            if data:
                self.paper_positions = data.get("positions", [])
                # [V125 Sem BTC] Purga qualquer resíduo de BTCUSDT da memória Paper
                self.paper_positions = [p for p in self.paper_positions if (p.get("symbol") or "").upper().replace(".P", "") != "BTCUSDT"]
                self.paper_moonbags = data.get("moonbags", [])
                self.paper_moonbags = [p for p in self.paper_moonbags if (p.get("symbol") or "").upper().replace(".P", "") != "BTCUSDT"]
                self.paper_balance = data.get("balance", settings.OKX_SIMULATED_BALANCE)
                self.paper_orders_history = data.get("history", [])
                self._last_paper_load_time = time.time()
                # Apenas loga se houver algo ativo para reduzir ruído
                if self.paper_positions or self.paper_moonbags:
                    logger.info(f"📂 [PAPER] State Synced: {len(self.paper_positions)} Pos | {len(self.paper_moonbags)} Moons | ${self.paper_balance:.2f}")

                # [V110.28.5] Auto-Healing: Sincronia ativa com o Vault Real (Firestore)
                # Garante que se uma Moonbag existe no Vault mas não na RAM, ela seja adotada.
                if hasattr(firebase_service, "get_all_moonbags"):
                    vault_moons = await firebase_service.get_all_moonbags()
                    if vault_moons:
                        ram_symbols = {m.get("symbol") for m in self.paper_moonbags}
                        for v_moon in vault_moons:
                            symbol = v_moon.get("symbol")
                            if symbol and symbol not in ram_symbols:
                                logger.warning(f"🚑 [AUTO-ADOPT] Ordem órfã detectada no Vault: {symbol}. Adotando para o motor.")
                                # Adaptar schema Firestore para schema RAM do OKXRest
                                pos_obj = {
                                    "symbol": symbol,
                                    "side": v_moon.get("side", "Buy"),
                                    "size": str(v_moon.get("qty", 0)),
                                    "avgPrice": str(v_moon.get("entry_price", 0)),
                                    "leverage": str(v_moon.get("leverage", 50)),
                                    "status": "EMANCIPATED",
                                    "stopLoss": str(v_moon.get("current_stop", 0)),
                                    "takeProfit": "0",
                                    "is_paper": True,
                                    "entry_margin": (float(v_moon.get("qty", 10)) * float(v_moon.get("entry_price", 0))) / float(v_moon.get("leverage", 50)),
                                    "opened_at": v_moon.get("opened_at", time.time())
                                }
                                self.paper_moonbags.append(pos_obj)
                
                # [V110.61] AMNESIA-GUARD: Auto-Recovery de Slots Tativos (PAPER)
                # Se existem ordens nos slots ativos do Firestore que NÃO estão na memória local,
                # nós as restauramos para evitar a purga prematura pelo Ghostbuster.
                try:
                    firestore_slots = await firebase_service.get_active_slots(force_refresh=True)
                    if firestore_slots:
                        local_symbols = {p.get("symbol") for p in self.paper_positions}
                        for f_slot in firestore_slots:
                            symbol = f_slot.get("symbol")
                            entry_price = float(f_slot.get("entry_price", 0))
                            # [V124 FIX] Removida condição is_paper — em PAPER mode, todo slot ativo
                            # no Firestore é de paper. A condição antiga bloqueava toda recuperação
                            # porque is_paper nunca era gravado, causando sumiço de ordens no restart.
                            if symbol and symbol not in local_symbols and entry_price > 0:
                                logger.warning(f"🚑 [V124 AMNESIA-GUARD] Recuperando ordem do Firestore após restart: {symbol} @ ${entry_price}")
                                # Reconstuir objeto de posição Paper compatível com Bybit v5 Schema Fake
                                recovered_pos = {
                                    "symbol": symbol,
                                    "side": f_slot.get("side", "Buy"),
                                    "size": str(f_slot.get("qty", 0)),
                                    "avgPrice": str(f_slot.get("entry_price", 0)),
                                    "leverage": str(f_slot.get("leverage", 50)),
                                    "status": "RECOVERED",
                                    "stopLoss": str(f_slot.get("current_stop", 0)),
                                    "takeProfit": str(f_slot.get("target_price", 0)),
                                    "opened_at": f_slot.get("opened_at", time.time()),
                                    "is_paper": True,
                                    "slot_id": f_slot.get("id", 0),
                                    "entry_margin": f_slot.get("entry_margin", 0),
                                    "genesis_id": f_slot.get("genesis_id", ""),
                                    "score": f_slot.get("score", 0),
                                    "fleet_intel": f_slot.get("fleet_intel", {}),
                                    "pensamento": f_slot.get("pensamento", ""),
                                    "slot_type": f_slot.get("slot_type", "SNIPER"),
                                }
                                self.paper_positions.append(recovered_pos)
                except Exception as recovery_error:
                    logger.error(f"⚠️ [V110.61] Falha no Amnesia-Guard: {recovery_error}")


            else:
                # [V110.704] FALLBACK POSTGRESQL PARA MODO OFFLINE / SEM FIREBASE
                # Carregar o saldo, slots e moonbags diretamente do Postgres para evitar posições zumbis
                from services.database_service import database_service
                
                # 1. Carregar Banca Status e forçar override de settings.OKX_SIMULATED_BALANCE
                banca_db = await database_service.get_banca_status()
                self.paper_balance = settings.OKX_SIMULATED_BALANCE
                logger.info(f"💰 [PAPER-OVERRIDE] Banca calibrada localmente para ${self.paper_balance:.2f} conforme settings.")
                
                # 2. Carregar Slots do Postgres para self.paper_positions
                slots_db = await database_service.get_active_slots()
                self.paper_positions = []
                for f_slot in slots_db:
                    symbol = f_slot.get("symbol")
                    entry_price = float(f_slot.get("entry_price", 0))
                    # [V125 Sem BTC] Purga qualquer resíduo de BTCUSDT da memória Paper
                    if symbol and symbol.upper().replace(".P", "") != "BTCUSDT" and entry_price > 0:
                        recovered_pos = {
                            "symbol": symbol,
                            "side": f_slot.get("side", "Buy"),
                            "size": str(f_slot.get("qty", 0)),
                            "avgPrice": str(f_slot.get("entry_price", 0)),
                            "leverage": str(f_slot.get("leverage", 50)),
                            "status": "RECOVERED",
                            "stopLoss": str(f_slot.get("current_stop", 0)),
                            "takeProfit": str(f_slot.get("target_price", 0)),
                            "opened_at": f_slot.get("opened_at", time.time()),
                            "is_paper": True,
                            "slot_id": f_slot.get("id", 0),
                            "entry_margin": f_slot.get("entry_margin", 0),
                            "genesis_id": f_slot.get("genesis_id", ""),
                            "score": f_slot.get("score", 0),
                            "fleet_intel": f_slot.get("fleet_intel", {}),
                            "pensamento": f_slot.get("pensamento", ""),
                            "slot_type": f_slot.get("slot_type", "SNIPER"),
                        }
                        self.paper_positions.append(recovered_pos)
                
                # 3. Carregar Moonbags do Postgres para self.paper_moonbags
                moons_db = await database_service.get_moonbags()
                self.paper_moonbags = []
                for v_moon in moons_db:
                    symbol = v_moon.get("symbol")
                    if symbol and symbol.upper().replace(".P", "") != "BTCUSDT":
                        pos_obj = {
                            "symbol": symbol,
                            "side": v_moon.get("side", "Buy"),
                            "size": str(v_moon.get("qty", 0)),
                            "avgPrice": str(v_moon.get("entry_price", 0)),
                            "leverage": str(v_moon.get("leverage", 50)),
                            "status": "EMANCIPATED",
                            "stopLoss": str(v_moon.get("current_stop", 0)),
                            "takeProfit": "0",
                            "is_paper": True,
                            "entry_margin": (float(v_moon.get("qty", 10)) * float(v_moon.get("entry_price", 0))) / float(v_moon.get("leverage", 50)),
                            "opened_at": v_moon.get("opened_at", time.time())
                        }
                        self.paper_moonbags.append(pos_obj)
                
                self._last_paper_load_time = time.time()
                if self.paper_positions or self.paper_moonbags:
                    logger.info(f"📂 [PAPER-POSTGRES-FALLBACK] State Synced from DB: {len(self.paper_positions)} Pos | {len(self.paper_moonbags)} Moons | ${self.paper_balance:.2f}")

        except Exception as e:
            logger.error(f"❌ [PAPER] Failed to load global state: {e}")

    async def _save_paper_state(self):
        """[V110.23.5] Saves paper positions and balance to Firestore for global persistence."""
        if self.execution_mode != "PAPER": return
        async with self._paper_save_lock:
            try:
                from services.firebase_service import firebase_service
                data = {
                    "positions": self.paper_positions,
                    "moonbags": self.paper_moonbags,
                    "balance": self.paper_balance,
                    "history": self.paper_orders_history[-50:] # Keep last 50 only
                }
                await firebase_service.update_paper_state(data)
                # logger.debug("💾 [V110.23.5 PAPER] Global State saved to Firestore.")
            except Exception as e:
                logger.error(f"❌ [PAPER] Failed to save global state: {e}")

    def normalize_symbol(self, symbol: str) -> str:
        """
        [V6.0] Robust Mapping: Standardizes symbols for Bybit V5 API.
        Strips .P suffix, ensures upper case, and prevents common mapping errors.
        """
        if not symbol: return ""
        norm = symbol.strip().upper()
        if norm.endswith(".P"):
            norm = norm[:-2]
        
        # Security Guard: Ensure it ends with USDT (or USDC)
        if not (norm.endswith("USDT") or norm.endswith("USDC")):
            # Fallback: if it's just 'BTC', return 'BTCUSDT'
            if norm: norm = f"{norm}USDT"
            
        return norm

    def _strip_p(self, symbol: str) -> str:
        """Standardizes symbols for Bybit API calls."""
        return self.normalize_symbol(symbol)

    def get_session(self, api_key: str = None, api_secret: str = None, username: str = None):
        """
        [V120] Retorna uma sessão HTTP da Bybit para o usuário.
        Se credenciais forem fornecidas, cria uma sessão específica.
        Caso contrário, usa a sessão global do admin.
        """
        if self.execution_mode == "PAPER":
            return None # Paper mode não usa sessão real (motor interno)

        # 1. Se for para um usuário específico (Multitenancy)
        if api_key and api_secret and username:
            # Reutiliza sessão do cache se existir
            if username in self._user_sessions:
                return self._user_sessions[username]
            
            logger.info(f"🔌 [V120] Criando sessão Bybit privada para: @{username}")
            session = HTTP(
                testnet=settings.OKX_TESTNET,
                api_key=api_key.strip(),
                api_secret=api_secret.strip(),
                recv_window=20000 # Increased for stability
            )
            self._user_sessions[username] = session
            return session

        # 2. Fallback para sessão global (Admin)
        if not self._global_session:
             self._global_session = HTTP(
                testnet=settings.OKX_TESTNET,
                api_key=settings.OKX_API_KEY.strip() if settings.OKX_API_KEY else None,
                api_secret=settings.OKX_API_SECRET.strip() if settings.OKX_API_SECRET else None,
                recv_window=30000
            )
        return self._global_session

    async def initialize(self):
        """Inicialização assíncrona do motor Paper."""
        try:
            # [V110.29.0] Factory Reset Protocol: Se ativado, limpa tudo no boot
            if getattr(settings, "FACTORY_RESET_V110", False):
                logger.warning("☣️ [FACTORY-RESET] Iniciando purgação atômica (V110.29.0)...")
                self.paper_moonbags = []
                self.paper_positions = []
                self.paper_balance = settings.OKX_SIMULATED_BALANCE
                if os.path.exists(self.PAPER_STORAGE_FILE):
                    os.remove(self.PAPER_STORAGE_FILE)
                    logger.warning(f"🗑️ [FACTORY-RESET] Arquivo de estado deletado: {self.PAPER_STORAGE_FILE}")
                
                # Sincroniza limpo com RTDB/Firestore imediatamente
                from services.firebase_service import firebase_service
                await self._save_paper_state()
                if hasattr(firebase_service, "update_bankroll"):
                    await firebase_service.update_bankroll(self.paper_balance)
                logger.warning(f"✅ [FACTORY-RESET] Sistema purificado e balanceado em ${self.paper_balance:.2f}.")
                return # Pula o carregamento de estado normal
        except Exception as e:
            logger.error(f"❌ [FACTORY-RESET] Falha crítica na purgação: {e}")

        if self.is_initialized:
            return

        logger.info("OKXRest: Initializing sessions (No Bybit Fallback)...")
        try:
            self.time_offset = 0
            if self.execution_mode == "PAPER":
                logger.info("📂 [V110.23.5] PAPER ENGINE: Loading persistent state from Firestore...")
                await self._load_paper_state()

        except Exception as e:
            logger.error(f"Failed to initialize OKXRest state: {e}")

        # Create the actual global session
        self._global_session = self.get_session()
        self.is_initialized = True
        logger.info("OKXRest: Session initialized.")
        
        # [V53.6] Load Paper State on startup (Global Firestore Sync)
        if self.execution_mode == "PAPER":
            await self._load_paper_state()
            
        self.is_ready = True
        logger.info("OKXRest: Session and state initialized.")


    @property
    def session(self):
        """Returns the fallback global Bybit HTTP session."""
        if not self._global_session:
            self._global_session = HTTP(
                testnet=settings.OKX_TESTNET,
                api_key=settings.OKX_API_KEY.strip() if settings.OKX_API_KEY else None,
                api_secret=settings.OKX_API_SECRET.strip() if settings.OKX_API_SECRET else None,
                recv_window=30000,
            )
        return self._global_session
    async def get_elite_50x_pairs(self):
        """
        🚀 REFINAMENTO ESTRATÉGICO V6.0: Escaneia apenas pares com alavancagem >= 50x na OKX.
        [V43.2] Caching implemented to prevent event loop blocking every 5s.
        """
        now = time.time()
        if self._elite_cache and (now - self._elite_cache_time < self._elite_cache_ttl):
            return self._elite_cache

        try:
            logger.info("OKXRest: Fetching Elite 50x Instruments from OKX (Sniper Strategy)...")
            from services.okx_service import okx_service
            
            candidates = {}
            # 1. Fetch ALL SWAP instruments from OKX public API
            url_instr = "https://www.okx.com/api/v5/public/instruments?instType=SWAP"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url_instr)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("code") == "0" and data.get("data"):
                        for info in data["data"]:
                            inst_id = info.get("instId", "")
                            if not inst_id.endswith("-USDT-SWAP"):
                                continue
                            
                            # Converte para formato legacy (com sufixo .P) para check da blocklist
                            legacy_sym = okx_service.from_okx_inst_id(inst_id)
                            legacy_sym_clean = legacy_sym.replace(".P", "")
                            
                            if legacy_sym_clean in settings.ASSET_BLOCKLIST:
                                continue
                                
                            lev_str = info.get("lever", "0")
                            if not lev_str:
                                lev_str = "0"
                            max_lev = float(lev_str)
                            if max_lev >= 50.0:
                                candidates[inst_id] = legacy_sym_clean

            logger.info(f"OKXRest: Identified {len(candidates)} SWAP pairs on OKX with leverage >= 50x.")
            
            # 2. Get tickers to sort by 24h volume/turnover
            url_tickers = "https://www.okx.com/api/v5/market/tickers?instType=SWAP"
            final_candidates = []
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url_tickers)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("code") == "0" and data.get("data"):
                        for t in data["data"]:
                            inst_id = t.get("instId", "")
                            if inst_id in candidates:
                                vol_str = t.get("volCcy24h", "0")
                                if not vol_str:
                                    vol_str = "0"
                                turnover = float(vol_str) # Volume das últimas 24h na moeda de cotação (USDT)
                                legacy_sym_clean = candidates[inst_id]
                                final_candidates.append({
                                    "symbol": legacy_sym_clean,
                                    "turnover": turnover
                                })
                                # Prime turnover cache in WS
                                from services.okx_ws_public import okx_ws_public_service
                                okx_ws_public_service.turnover_24h_cache[f"{legacy_sym_clean}.P"] = turnover

            # Ordenar por volume/turnover
            final_candidates.sort(key=lambda x: x["turnover"], reverse=True)
            
            # Seleciona os top 100 ativos mais líquidos no formato esperado (.P)
            final_symbols = [f"{x['symbol']}.P" for x in final_candidates][:100]
            
            # Se a lista estiver vazia por alguma falha de rede temporária, usa o fallback da Elite Matrix do config
            if not final_symbols:
                final_symbols = [f"{s}.P" for s in settings.ELITE_40_MATRIX if f"{s}.P" not in settings.ASSET_BLOCKLIST]
                
            logger.info(f"OKXRest: Mass Sniper Elite Scan Successful (OKX Source). Monitoring Top {len(final_symbols)} high-leverage assets.")
            
            self._elite_cache = final_symbols
            self._elite_cache_time = now
            return final_symbols
            
        except Exception as e:
            logger.error(f"Error in Elite 50x scan from OKX: {e}")
            # Fallback seguro com a matriz elite definida nas configurações
            fallback = [f"{s}.P" for s in settings.ELITE_40_MATRIX if f"{s}.P" not in settings.ASSET_BLOCKLIST]
            return fallback[:20]

    def get_top_200_usdt_pairs(self):
        """Deprecated: Use get_elite_50x_pairs for Sniper Protocol."""
        return self.get_elite_50x_pairs()

    async def get_elite_focus_pairs(self):
        """[V110.175] Helper for WS Tracker. Retorna os top 20 pares."""
        pairs = await self.get_elite_50x_pairs()
        return pairs[:20] if pairs else []

    @with_circuit_breaker(breaker_name="okx_rest_public", fallback_return=0.0)
    async def get_wallet_balance(self):
        """Fetches the total equity from the Bybit account (UNIFIED or CONTRACT)."""
        # logger.info(f"[DEBUG] get_wallet_balance called. Mode: {self.execution_mode}")
        if self.execution_mode == "PAPER":
             # O saldo total no modo PAPER deve ser o saldo base configurado + lucros/prejuízos acumulados + pnl flutuante de posições táticas e moonbags.
             # Para evitar dependência circular direta com bankroll_manager que já chama get_wallet_balance, 
             # nós calculamos localmente.
             float_pnl = 0.0
             try:
                 # Calcula o pnl flutuante das posições em aberto (táticas + moonbags)
                 # Como já calculamos o preço de mercado delas, usamos o que temos ou estimamos
                 from services.okx_ws_public import okx_ws_public_service
                 for p in (self.paper_positions + self.paper_moonbags):
                     sym = p.get("symbol")
                     entry = float(p.get("avgPrice", 0))
                     qty = float(p.get("size", 0))
                     side = p.get("side", "Buy")
                     if entry > 0 and qty > 0:
                         price = okx_ws_public_service.get_current_price(sym) or entry
                         price_diff = (price - entry) / entry if side == "Buy" else (entry - price) / entry
                         # ROI = price_diff * leverage * 100
                         # PnL = (ROI / 100) * margin
                         # Simplificado: PnL = price_diff * qty * entry
                         pnl_usd = price_diff * qty * entry
                         float_pnl += pnl_usd
             except Exception as e:
                 logger.error(f"Error calculating float_pnl in get_wallet_balance paper mode: {e}")
             
             # Se for PAPER, o get_wallet_balance deve SEMPRE sincronizar com a banca de settings se ela tiver $20.00 ou se o banco estiver limpo.
             # Como o banco tem $20.00, vamos usar self.paper_balance que é atualizado dinamicamente pelo bankroll_manager baseado no banco.
             return self.paper_balance + float_pnl

        if settings.OKX_API_KEY_MASTER and self.execution_mode != "PAPER":
            from services.okx_service import okx_service
            try:
                request_path = "/api/v5/account/balance"
                url = okx_service.base_url + request_path
                headers = okx_service._get_headers("GET", request_path)
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(url, headers=headers)
                    if response.status_code == 200:
                        data = response.json()
                        if data.get("code") == "0" and data.get("data"):
                            details = data["data"][0]
                            total_eq = float(details.get("totalEq", 100.0))
                            # Se for demo trading com muito saldo virtual, limitamos a $100
                            if settings.OKX_TESTNET and total_eq > 500.0:
                                logger.info(f"💰 [OKX-REST] Saldo demo real: ${total_eq:.2f}. Limitando a banca virtual Sniper em $100 para simulação.")
                                return 100.0
                            return total_eq
            except Exception as e:
                logger.error(f"❌ [OKX-REST] Erro ao obter saldo da OKX: {e}")
            return 100.0


        async with self._http_semaphore:
            try:
                # Try UNIFIED first
                logger.info("Fetching balance (UNIFIED)...")
                try:
                    # V5.2.4.3: Added 10s timeout
                    response = await asyncio.wait_for(asyncio.to_thread(self.session.get_wallet_balance, accountType="UNIFIED"), timeout=10.0)
                    result = response.get("result", {}).get("list", [{}])[0]
                    equity = float(result.get("totalEquity", 0))
                    logger.info(f"UNIFIED Equity: {equity}")
                    self.last_balance = equity # V5.2.4.6: Update cache
                    if equity > 0: return equity
                except Exception as ue: 
                    logger.warning(f"UNIFIED balance fetch failed: {ue}")
                
                # Try CONTRACT if UNIFIED fails or is 0
                logger.info("Fetching balance (CONTRACT)...")
                # V5.2.4.3: Added 10s timeout
                response = await asyncio.wait_for(asyncio.to_thread(self.session.get_wallet_balance, accountType="CONTRACT"), timeout=10.0)
                result = response.get("result", {}).get("list", [{}])[0]
                coins = result.get("coin", [])
                usdt_coin = next((c for c in coins if c.get("coin") == "USDT"), {})
                equity = float(usdt_coin.get("equity", 0))
                logger.info(f"CONTRACT Equity: {equity}")
                self.last_balance = equity # V5.2.4.6: Update cache
                return equity
            except Exception as e:
                logger.error(f"Error fetching wallet balance: {e}")
                return self.last_balance # V5.2.4.6: Return cached on error

    @with_circuit_breaker(breaker_name="okx_rest_private", fallback_return=[])
    async def get_active_positions(self, symbol: str = None, username: str = None):
        """
        [V120] Busca posições ativas isoladas por usuário.
        """
        if settings.OKX_API_KEY_MASTER and self.execution_mode != "PAPER":
            from services.okx_service import okx_service
            try:
                okx_positions = await okx_service.get_positions()
                translated = []
                for op in okx_positions:
                    # Converte de OKX para Bybit
                    avg_px = op.get("avgPx", "0")
                    pos_qty = op.get("pos", "0")
                    
                    # Se pos for 0, ignora
                    if float(pos_qty) == 0:
                        continue
                        
                    translated_pos = {
                        "symbol": okx_service.from_okx_inst_id(op.get("instId")),
                        "side": "Buy" if op.get("posSide") == "long" else "Sell",
                        "size": pos_qty,
                        "avgPrice": avg_px,
                        "positionValue": str(float(pos_qty) * float(avg_px)),
                        "unrealisedPnl": op.get("upl", "0"),
                        "stopLoss": op.get("slTriggerPx", "0") or "0",
                        "takeProfit": op.get("tpTriggerPx", "0") or "0",
                        "leverage": "50"
                    }
                    translated.append(translated_pos)
                
                if symbol:
                    norm_symbol = self._strip_p(symbol).upper()
                    return [p for p in translated if p["symbol"].upper() == norm_symbol]
                return translated
            except Exception as e:
                logger.error(f"❌ [OKX-REST] Erro ao obter/traduzir posições da OKX: {e}")
                return []

        if self.execution_mode == "PAPER":
            combined = self.paper_positions + self.paper_moonbags
            if symbol:
                norm_symbol = self._strip_p(symbol).upper()
                return [p for p in combined if p["symbol"].upper() == norm_symbol]
            return combined

        # [V120] Multitenant Session
        session = self.get_session(username=username)


        async with self._http_semaphore:
            try:
                params = {"category": self.category, "settleCoin": "USDT"}
                if symbol: params["symbol"] = symbol
                
                # [V120] Usa a sessão específica do usuário para buscar posições
                response = await asyncio.wait_for(asyncio.to_thread(session.get_positions, **params), timeout=10.0)
                pos_list = response.get("result", {}).get("list", [])
                # Filter for positions with size > 0
                active = [p for p in pos_list if float(p.get("size", 0)) > 0]
                return active
            except Exception as e:
                logger.error(f"Error fetching positions: {e}")
                return []

    @with_circuit_breaker(breaker_name="okx_rest_public", fallback_return={"retCode": -1, "result": {"list": []}})
    async def get_tickers(self, symbol: str = None):
        """
        [V110.999] Busca preços em tempo real de forma ultra-resiliente.
        Após a migração para OKX como fonte única, sem contingência para corretora legada.
        """
        async with self._http_semaphore:
            # 1. Verificar Cache Global primeiro
            if symbol is None:
                now = time.time()
                if hasattr(self, "_global_ticker_cache") and (now - self._global_ticker_cache_time < 2.0):
                    return self._global_ticker_cache

            # 2. Tentar obter via OKX (com contingência de domínio alternativo AWS)
            from services.okx_service import okx_service
            okx_urls = []
            if symbol:
                inst_id = okx_service.to_okx_inst_id(symbol)
                okx_urls.append(f"https://www.okx.com/api/v5/market/ticker?instId={inst_id}")
                okx_urls.append(f"https://aws.okx.com/api/v5/market/ticker?instId={inst_id}")
            else:
                okx_urls.append("https://www.okx.com/api/v5/market/tickers?instType=SWAP")
                okx_urls.append("https://aws.okx.com/api/v5/market/tickers?instType=SWAP")

            okx_success = False
            translated_list = []

            for url in okx_urls:
                try:
                    async with httpx.AsyncClient(timeout=3.0) as client:
                        response = await client.get(url)
                        if response.status_code == 200:
                            data = response.json()
                            if data.get("code") == "0" and data.get("data"):
                                okx_list = data["data"]
                                for ot in okx_list:
                                    legacy_sym = okx_service.from_okx_inst_id(ot.get("instId"))
                                    legacy_sym_clean = legacy_sym.replace(".P", "")
                                    translated_list.append({
                                        "symbol": legacy_sym_clean,
                                        "lastPrice": ot.get("last", "0"),
                                        "turnover24h": ot.get("volCcy24h", "0")
                                    })
                                
                                if symbol:
                                    api_symbol = self.normalize_symbol(symbol)
                                    translated_list = [t for t in translated_list if t["symbol"] == api_symbol]
                                
                                if translated_list:
                                    okx_success = True
                                    break
                except Exception as okx_err:
                    logger.debug(f"[OKX-TICKER-TRY] Falha ao ler de {url}: {okx_err}")

            if okx_success and translated_list:
                res_payload = {"retCode": 0, "result": {"list": translated_list}}
                if symbol is None:
                    self._global_ticker_cache = res_payload
                    self._global_ticker_cache_time = time.time()
                return res_payload

            # 3. Sem contingência: OKX é a única fonte de tickers após a migração.
            # Caso a OKX falhe ou bloqueie o IP, retornamos lista vazia para o circuit breaker
            # abrir e o sistema seguir sem dependência de corretora legada.
            logger.error(f"🚨 [OKX-REST FATAL] OKX falhou em fornecer tickers para {symbol or 'GLOBAL'}. Sem contingência legada configurada.")
            return {"retCode": -1, "result": {"list": []}}

    @with_circuit_breaker(breaker_name="okx_rest_public", fallback_return={})
    async def get_instrument_info(self, symbol: str):
        """Fetches precision and lot size filtering for a symbol with local caching."""
        if settings.OKX_API_KEY_MASTER and self.execution_mode != "PAPER":
            from services.okx_service import okx_service
            try:
                api_symbol = self._strip_p(symbol)
                if api_symbol in self._instrument_cache:
                    return self._instrument_cache[api_symbol]
                
                details = await okx_service.get_instrument_details(symbol)
                tick_size = details.get("tickSize", "0.01")
                lot_size = details.get("lotSize", "1.0")
                min_sz = details.get("minSz", "1.0")
                
                info = {
                    "priceFilter": {
                        "tickSize": tick_size
                    },
                    "lotSizeFilter": {
                        "qtyStep": lot_size,
                        "minOrderQty": min_sz,
                        "ctVal": details.get("ctVal", "1.0")
                    },
                    "leverageFilter": {
                        "maxLeverage": "50.0"
                    }
                }
                self._instrument_cache[api_symbol] = info
                return info
            except Exception as e:
                logger.error(f"Error fetching instrument info from OKX for {symbol}: {e}")
                return {}

        # Fallback público direcionado para a OKX via okx_service
        try:
            api_symbol = self._strip_p(symbol)
            if api_symbol in self._instrument_cache:
                return self._instrument_cache[api_symbol]
                
            from services.okx_service import okx_service
            details = await okx_service.get_instrument_details(symbol)
            tick_size = details.get("tickSize", "0.01")
            lot_size = details.get("lotSize", "1.0")
            min_sz = details.get("minSz", "1.0")
            
            info = {
                "priceFilter": {
                    "tickSize": tick_size
                },
                "lotSizeFilter": {
                    "qtyStep": lot_size,
                    "minOrderQty": min_sz,
                    "ctVal": details.get("ctVal", "1.0")
                },
                "leverageFilter": {
                    "maxLeverage": "50.0"
                }
            }
            self._instrument_cache[api_symbol] = info
            return info
        except Exception as e:
            logger.error(f"Error fetching instrument info from OKX fallback for {symbol}: {e}")
            return {}

    async def get_leverage_info(self, symbol: str) -> Dict[str, Any]:
        """
        Compatibilidade para relatórios de contrato.
        A OKX pública nem sempre expõe o limite dinâmico por conta/posição sem auth,
        então usamos o metadado do instrumento e caímos para 50x de forma explícita.
        """
        try:
            instrument_info = await self.get_instrument_info(symbol)
            max_leverage = float(
                instrument_info.get("leverageFilter", {}).get("maxLeverage")
                or instrument_info.get("maxLvrg")
                or 50
            )
            return {
                "maxLeverage": max_leverage,
                "notionalUsd": 0,
            }
        except Exception as e:
            logger.warning(f"Failed to derive leverage info for {symbol}: {e}")
            return {
                "maxLeverage": 50,
                "notionalUsd": 0,
            }

    async def get_detailed_contract_info(self, symbol: str) -> Dict[str, Any]:
        """
        Captura informações detalhadas de contratos para relatórios e análise.
        Retorna dados completos do contrato incluindo ctVal, lotSize, leverage, etc.
        
        Args:
            symbol: Símbolo do ativo (ex: BTC-USDT-SWAP)
            
        Returns:
            Dict com informações detalhadas do contrato
        """
        try:
            # Obter informações básicas do instrumento
            instrument_info = await self.get_instrument_info(symbol)
            
            # Obter ticker atual para preço de referência
            api_symbol = self._strip_p(symbol)
            ticker = await self.get_tickers(symbol=api_symbol)
            ticker_data = ticker.get("result", {}).get("list", [])
            current_price = float(ticker_data[0].get("lastPrice", 0)) if ticker_data else 0
            
            # Obter informações de leverage disponíveis
            try:
                leverage_info = await self.get_leverage_info(symbol)
                max_leverage = leverage_info.get("maxLeverage", 50)
                notional_usd = leverage_info.get("notionalUsd", 0)
            except Exception as leverage_err:
                logger.warning(f"Failed to get leverage info for {symbol}: {leverage_err}")
                max_leverage = 50
                notional_usd = 0
            
            # Construir relatório detalhado
            contract_info = {
                "symbol": symbol,
                "timestamp": time.time(),
                "current_price": current_price,
                "contract_details": {
                    "ctVal": float(instrument_info.get("lotSizeFilter", {}).get("ctVal", "1.0")),
                    "lotSize": float(instrument_info.get("lotSizeFilter", {}).get("qtyStep", "1.0")),
                    "minQty": float(instrument_info.get("lotSizeFilter", {}).get("minOrderQty", "1.0")),
                    "tickSize": float(instrument_info.get("priceFilter", {}).get("tickSize", "0.01")),
                    "maxLeverage": float(max_leverage),
                    "notionalUsd": notional_usd
                },
                "risk_analysis": {
                    "price_impact_per_contract": current_price * float(instrument_info.get("lotSizeFilter", {}).get("ctVal", "1.0")),
                    "min_margin_required": (current_price * float(instrument_info.get("lotSizeFilter", {}).get("ctVal", "1.0"))) / max_leverage if max_leverage > 0 else 0,
                    "max_position_size": notional_usd if notional_usd > 0 else (current_price * float(instrument_info.get("lotSizeFilter", {}).get("ctVal", "1.0"))) * max_leverage if max_leverage > 0 else 0
                },
                "okx_metadata": {
                    "category": self.category,
                    "instType": "SWAP",
                    "currency": symbol.split("-")[1] if "-" in symbol else "USDT"
                }
            }
            
            logger.info(f"📋 [CONTRACT INFO] Capturadas informações detalhadas para {symbol}")
            return contract_info
            
        except Exception as e:
            logger.error(f"Error getting detailed contract info for {symbol}: {e}")
            return {
                "symbol": symbol,
                "timestamp": time.time(),
                "error": str(e),
                "contract_details": {
                    "ctVal": 1.0,
                    "lotSize": 1.0,
                    "minQty": 1.0,
                    "tickSize": 0.01,
                    "maxLeverage": 50,
                    "notionalUsd": 0
                }
            }

    async def round_price(self, symbol: str, price: float) -> float:
        """
        Rounds the price to the nearest tickSize allowed by Bybit.
        Essential for avoiding 10001 errors and ensuring 'Maker' precision.
        """
        return await self.format_precision(symbol, price)

    async def format_precision(self, symbol: str, price: float) -> float:
        """
        [V5.2.5] Precision Engine: Normaliza preços baseado no tickSize real da Bybit.
        """
        if price <= 0: return price
        
        info = await self.get_instrument_info(symbol)
        tick_size_str = info.get("priceFilter", {}).get("tickSize")
        
        if not tick_size_str:
            return price # Fallback
            
        from decimal import Decimal, ROUND_HALF_UP
        tick_size = Decimal(tick_size_str)
        price_dec = Decimal(str(price))
        
        # Formula: round(price / tickSize) * tickSize
        rounded = (price_dec / tick_size).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * tick_size
        
        # Normalize to remove trailing zeros and convert back to float
        return float(rounded.normalize())

    async def round_qty(self, symbol: str, qty: float) -> float:
        """
        [V53.0] Precisão de Quantidade: Normaliza quantidades baseado no qtyStep da Bybit.
        """
        if qty <= 0: return qty
        
        info = await self.get_instrument_info(symbol)
        qty_step_str = info.get("lotSizeFilter", {}).get("qtyStep")
        
        if not qty_step_str:
            return qty
            
        from decimal import Decimal, ROUND_HALF_UP
        qty_step = Decimal(qty_step_str)
        qty_dec = Decimal(str(qty))
        
        rounded = (qty_dec / qty_step).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * qty_step
        return float(rounded.normalize())



    @with_circuit_breaker(breaker_name="okx_rest_private", fallback_return={"retCode": -1, "retMsg": "Circuit Breaker Active"})
    async def set_leverage(self, symbol: str, leverage: int = 50):
        """
        🚀 V12.0: Ajusta a alavancagem para o símbolo antes de abrir a ordem.
        Garante que a margem calculada corresponda à alavancagem real na OKX/Bybit.
        """
        api_symbol = self._strip_p(symbol)

        if settings.OKX_API_KEY_MASTER and self.execution_mode != "PAPER":
            from services.okx_service import okx_service
            logger.info(f"🔌 [OKX] Configurando alavancagem na OKX real para {symbol} em {leverage}x...")
            res = await okx_service.set_leverage(symbol, leverage, mgn_mode="cross")
            if res and res.get("code") == "0":
                return {"retCode": 0, "result": {}}
            return {"retCode": -1, "retMsg": res.get("msg") if res else "Unknown OKX Error"}
        
        if self.execution_mode == "PAPER":
            logger.info(f"[PAPER] Setting leverage for {api_symbol} to {leverage}x")
            # Update leverage in existing paper position if it exists
            pos = next((p for p in self.paper_positions if p["symbol"] == api_symbol), None)
            if pos:
                pos["leverage"] = str(leverage)
                await self._save_paper_state()
            return {"retCode": 0, "result": {}}

        try:
            # Use synchronize thread for pybit call
            response = await asyncio.to_thread(self.session.set_leverage,
                category=self.category,
                symbol=api_symbol,
                buyLeverage=str(leverage),
                sellLeverage=str(leverage)
            )
            
            # Note: Bybit returns 110043 if leverage is already set to the same value
            if response.get("retCode") == 110043:
                logger.debug(f"Leverage for {symbol} already at {leverage}x.")
                return response
                
            logger.info(f"Leverage set for {symbol} to {leverage}x: {response}")
            return response
        except Exception as e:
            # Common error: "leverage not modified" or similar, we log but don't block
            logger.warning(f"Failed to set leverage for {symbol}: {e}")
            return {"retCode": -1, "retMsg": str(e)}

    @with_circuit_breaker(breaker_name="okx_rest_private", fallback_return=None)
    async def place_atomic_order(self, symbol: str, side: str, qty: float, sl_price: float, tp_price: float = None, slot_id: int = 0, leverage: float = 50, username: str = None, **kwargs):
        """
        [V120] Envio de Ordem Atômica com isolamento de sessão por usuário.
        """
        if settings.OKX_API_KEY_MASTER and self.execution_mode != "PAPER":
            from services.okx_service import okx_service
            logger.info(f"🔌 [OKX] Direcionando Ordem Atômica: {side} {qty} {symbol} para OKX Testnet...")
            res = await okx_service.place_atomic_order(symbol, side, qty, sl_price, tp_price, slot_id, leverage, username, **kwargs)
            if res and res.get("code") == "0":
                ord_info = res["data"][0]
                return {
                    "retCode": 0,
                    "result": {"orderId": ord_info.get("ordId"), "orderLinkId": ord_info.get("clOrdId")}
                }
            return {"retCode": -1, "retMsg": res.get("msg") if res else "Unknown OKX Error"}

        api_symbol = self._strip_p(symbol)
        
        # [V120] Seleção da Sessão
        session = self.get_session(username=username)
        
        if self.execution_mode == "PAPER":
            logger.info(f"[PAPER] Simulating Atomic Order: {side} {qty} {symbol} @ MARKET | User: {username}")
            # 1. Get current price for entry simulation
            try:
                # Need to fetch real price to simulate entry (usa sessão global para dados de mercado)
                ticker = await self.get_tickers(symbol=api_symbol)
                ticker_list = ticker.get("result", {}).get("list", [{}])
                last_price = float(ticker_list[0].get("lastPrice", 0))
                
                if last_price == 0:
                    raise Exception("Could not fetch price for paper execution")

                # [V110.65] AMBUSH ENTRY: Usa zona de lambida para entrada mais precisa
                # Se o sinal tem um ambush_price calculado e o preço já está na zona, 
                # entramos no ambush price (melhor entry = mais espaço pro Moonbag)
                ambush_price = kwargs.get("ambush_price", 0)
                if ambush_price > 0:
                    side_norm = side.lower()
                    # Verifica se o preço atual já alcançou ou ultrapassou a zona de lambida
                    is_in_ambush_zone = (side_norm == "buy" and last_price <= ambush_price) or \
                                        (side_norm == "sell" and last_price >= ambush_price)
                    if is_in_ambush_zone:
                        logger.info(f"🎯 [V110.65 AMBUSH] {symbol} Entrada na Zona de Lambida: ${ambush_price:.6f} (Market: ${last_price:.6f})")
                        last_price = ambush_price  # Simula entry no ambush price
                    else:
                        # Preço não chegou na zona, mas como é Paper e queremos testar,
                        # aceitamos entry no mercado com log de aviso
                        logger.info(f"📍 [V110.65 AMBUSH] {symbol} Market entry ${last_price:.6f} (Ambush zone: ${ambush_price:.6f} não alcançada)")

                try:
                    instrument_info = await self.get_instrument_info(symbol)
                    ct_val = float(instrument_info.get("lotSizeFilter", {}).get("ctVal", "1.0"))
                except Exception as ct_err:
                    logger.warning(f"[PAPER] Failed to fetch ctVal for {symbol}: {ct_err}. Using 1.0")
                    ct_val = 1.0
                if ct_val <= 0:
                    ct_val = 1.0

                entry_margin = (qty * last_price * ct_val) / leverage

                # 2. Create Position Object (Mocking Bybit Schema)
                new_position = {
                    "symbol": api_symbol, # Normalized
                    "side": side,
                    "size": str(qty),
                    "avgPrice": str(last_price),
                    "leverage": str(leverage),
                    "stopLoss": str(sl_price),
                    "takeProfit": str(tp_price) if tp_price else "",
                    "entry_margin": str(entry_margin),
                    "ctVal": str(ct_val),
                    "createdTime": str(int(time.time() * 1000)),
                    "opened_at": time.time(), # [V84.1] Absolute start
                    "maestria_guard_active": False, # [V84.1] Start clean
                    "slot_id": slot_id # [V96.9] Track slot for history registration
                }
                
                # Check if position already exists (Hedge mode not supported in paper simple impl, assuming One-Way)
                # If exists, we should technically add size/avg down, but for simplicity we reject or replace?
                # Let's simple append or replace.
                existing = next((p for p in self.paper_positions if p["symbol"] == api_symbol), None)
                if existing:
                    logger.warning(f"[PAPER] Overwriting existing position for {api_symbol} (Simpler than averaging).")
                    self.paper_positions.remove(existing)
                
                self.paper_positions.append(new_position)
                logger.info(f"[PAPER] Position Created: {api_symbol} Entry={last_price}")
                await self._save_paper_state()
                
                # Return fake order response
                return {
                    "retCode": 0,
                    "result": {
                        "orderId": f"PAPER-{api_symbol}-123",
                        "orderLinkId": f"PAPER-{api_symbol}-123",
                        "avgPrice": str(last_price),
                        "filledQty": str(qty),
                        "notionalUsd": str(qty * last_price * ct_val),
                        "ctVal": str(ct_val),
                        "status": "FILLED",
                    }
                }

            except Exception as e:
                logger.error(f"[PAPER] Failed to place simulated order: {e}")
                return None

        try:
            # [V5.2.5] Precision Engine: Normalizar preços antes do envio
            sl_final = await self.format_precision(symbol, sl_price)
            tp_final = await self.format_precision(symbol, tp_price) if tp_price else None

            # [V43.0] Hedge Mode support for order entry
            positionIdx = 0
            if self.execution_mode == "REAL":
                # Detect mode if not cached
                if api_symbol not in self._position_mode_cache:
                    try:
                        resp = await asyncio.to_thread(self.session.get_position_infos, category=self.category, symbol=api_symbol)
                        pos_list = resp.get("result", {}).get("list", [])
                        if pos_list:
                            # If we get multiple positions for one symbol, it's Hedge Mode
                            if len(pos_list) > 1:
                                self._position_mode_cache[api_symbol] = "HEDGE"
                            else:
                                self._position_mode_cache[api_symbol] = "ONE_WAY"
                    except Exception as pe:
                        logger.warning(f"Could not detect position mode for {symbol}: {pe}")
                
                mode = self._position_mode_cache.get(api_symbol, "ONE_WAY")
                if mode == "HEDGE":
                    positionIdx = 1 if side == "Buy" else 2
                else:
                    positionIdx = 0

            order_params = {
                "category": self.category,
                "symbol": api_symbol,
                "side": side,
                "orderType": "Market",
                "qty": str(qty),
                "stopLoss": str(sl_final) if sl_final > 0 else None,
                "tpTriggerBy": "LastPrice",
                "slTriggerBy": "LastPrice",
                "tpslMode": "Full",
                "positionIdx": positionIdx
            }
            if tp_final:
                order_params["takeProfit"] = str(tp_final)

            response = await asyncio.to_thread(session.place_order, **order_params)
            logger.info(f"Atomic order placed for {symbol} (idx:{positionIdx}) for {username}: {response}")
            return response
        except Exception as e:
            logger.error(f"Failed to place atomic order for {symbol} ({username}): {e}")
            return None

    @with_circuit_breaker(breaker_name="okx_rest_private", fallback_return=False, is_critical=True)
    async def close_position(self, symbol: str, side: str, qty: float, reason: str = "MANUAL_CLOSE", is_partial: bool = False, username: str = None) -> bool:
        """
        [V120] Encerramento Multitenant Soberano.
        """
        if settings.OKX_API_KEY_MASTER and self.execution_mode != "PAPER":
            from services.okx_service import okx_service
            logger.info(f"🔌 [OKX] Direcionando Fechamento de Posição de {symbol} para OKX Testnet...")
            success = await okx_service.close_position(symbol, side, qty, reason, username)
            return success

        norm_symbol = self._strip_p(symbol).upper()
        
        # [V120] Recupera a sessão correta
        session = self.get_session(username=username)
        
        # [V110.118] Partial closes use a lighter lock (prefix 'partial:') to allow
        # multiple harvests of the same symbol over time without blocking full closes.
        lock_key = f"partial:{norm_symbol}" if is_partial else f"close:{norm_symbol}"
        lock_acquired = await self.redis.acquire_lock(lock_key, lock_timeout=15)
        if not lock_acquired:
            logger.info(f"🛡️ [REDIS LOCK] {norm_symbol} {'partial harvest' if is_partial else 'closure'} already in progress. Skipping.")
            return False

        try:
            if not is_partial and norm_symbol in self.pending_closures:
                logger.info(f"🛡️ [OKX] {norm_symbol} already has a local pending closure. Skipping.")
                return False
            
            # [V5.3.4] Add to pending_closures immediately to prevent sync flapping
            if not is_partial:
                self.pending_closures.add(norm_symbol)
            
            if self.execution_mode == "PAPER":
                logger.info(f"[PAPER] {'Partial harvest' if is_partial else 'Closing'} position {norm_symbol} | qty={qty} | Reason: {reason}")
                # Find position in tactical or moonbags
                pos = next((p for p in self.paper_positions if self.normalize_symbol(p["symbol"]) == norm_symbol), None)
                if not pos:
                    pos = next((p for p in self.paper_moonbags if self.normalize_symbol(p["symbol"]) == norm_symbol), None)
                if pos:
                    try:
                        from services.execution_protocol import execution_protocol
                        api_symbol = self._strip_p(symbol)
                        
                        entry_price = float(pos["avgPrice"])
                        size = float(pos["size"])
                        leverage = float(pos.get("leverage", 50))
                        side_pos = pos["side"]
                        stop_price = float(pos.get("stopLoss", 0))
                        slot_id = int(pos.get("slot_id", 0) or 0)
                        
                        # [V110.118] Determinar qty real a fechar
                        close_qty = min(float(qty) if qty > 0 else size, size)  # Nunca fechar mais que o size total
                        remaining_qty = size - close_qty
                        # Re-avaliar is_partial pela qty real (proteção dupla)
                        is_partial_real = is_partial and remaining_qty > 0.000001
                        
                        reason_upper = (reason or "").upper()
                        is_sl_trigger = any(kw in reason_upper for kw in ["SL", "STOP", "RISK_ZERO", "SAFE", "STABILIZE", "FLASH", "MEGA", "PROFIT"])

                        if is_sl_trigger:
                            try:
                                from services.database_service import database_service
                                authoritative_stop = 0.0
                                if slot_id > 0:
                                    slot_state = await database_service.get_slot(slot_id)
                                    if slot_state and self.normalize_symbol(slot_state.get("symbol", "")) == norm_symbol:
                                        authoritative_stop = float(slot_state.get("current_stop") or 0)
                                if authoritative_stop <= 0:
                                    moonbags = await database_service.get_moonbags()
                                    for moon in moonbags:
                                        if self.normalize_symbol(moon.get("symbol", "")) == norm_symbol:
                                            authoritative_stop = float(moon.get("current_stop") or 0)
                                            break
                                if authoritative_stop > 0:
                                    stop_price = authoritative_stop
                                    pos["stopLoss"] = str(stop_price)
                                    logger.info(
                                        f"[PAPER] Authoritative stop resolved from ledger for {norm_symbol}: "
                                        f"${stop_price:.8f}"
                                    )
                            except Exception as stop_err:
                                logger.warning(f"[PAPER] Failed to resolve authoritative stop for {norm_symbol}: {stop_err}")
                        
                        if is_sl_trigger and stop_price > 0:
                            exit_price = stop_price
                            logger.info(f"[PAPER] SL-triggered exit: using stop price ${exit_price:.6f} as exit (not market)")
                        else:
                            # Safely fetch current price
                            try:
                                # [V110.125 FIX] Tenta pegar o preço do WebSocket (LKG) primeiro pois é mais rápido e confiável que o Ticker REST em picos
                                from services.okx_ws_public import okx_ws_public_service
                                ws_price = okx_ws_public_service.get_current_price(symbol)
                                
                                if ws_price and ws_price > 0:
                                    exit_price = ws_price
                                    logger.info(f"[PAPER] Using WS price for closure: ${exit_price:.6f}")
                                else:
                                    ticker = await self.get_tickers(symbol=api_symbol)
                                    ticker_list = ticker.get("result", {}).get("list", [])
                                    if ticker_list and float(ticker_list[0].get("lastPrice", 0)) > 0:
                                        exit_price = float(ticker_list[0].get("lastPrice", 0))
                                    else:
                                        # [V110.125 HARDEN] Se tudo falhar mas for um SL, usa o stop_price. 
                                        # Senão, usa o entry_price como último recurso (com aviso crítico).
                                        if stop_price > 0:
                                            exit_price = stop_price
                                            logger.warning(f"[PAPER] Critical Price Failure. Falling back to Stop Price: ${exit_price:.6f}")
                                        else:
                                            exit_price = entry_price 
                                            logger.error(f"[PAPER-CRITICAL] Global Price Failure. Falling back to ENTRY: ${exit_price:.6f} (PnL Zeroed)")
                            except Exception as price_err:
                                logger.warning(f"[PAPER] Failed to fetch exit price: {price_err}. Fallback: {'Stop Price' if stop_price > 0 else 'Entry Price'}")
                                exit_price = stop_price if stop_price > 0 else entry_price

                        # Obter ctVal do contrato para cálculo correto de PnL
                        try:
                            instrument_info = await self.get_instrument_info(symbol)
                            ct_val = float(instrument_info.get("lotSizeFilter", {}).get("ctVal", "1.0"))
                        except Exception as ct_err:
                            logger.warning(f"[PAPER] Failed to get ctVal for {symbol}: {ct_err}. Using default 1.0")
                            ct_val = 1.0
                        
                        # Calcular PnL da quantidade fechada com ctVal
                        final_pnl = execution_protocol.calculate_pnl(entry_price, exit_price, close_qty, side_pos, ct_val)
                        harvest_roi = execution_protocol.calculate_roi(entry_price, exit_price, side_pos)
                        
                        self.paper_balance += final_pnl
                        self.paper_orders_history.append({
                            "symbol": symbol,
                            "side": side_pos,
                            "positionValue": close_qty * entry_price, 
                            "unrealisedPnl": 0,
                            "createdTime": pos.get("createdTime") or str(int(time.time() * 1000)),
                            "avgEntryPrice": str(entry_price),
                            "avgExitPrice": str(exit_price),
                            "closedPnl": str(final_pnl),
                            "leverage": str(leverage),
                            "qty": str(close_qty),
                            "is_partial": is_partial_real,
                            "updatedTime": str(int(time.time() * 1000))
                        })
                        
                        # [V110.65] ATOMIC CLOSURE PROTOCOL
                        try:
                            from services.bankroll import bankroll_manager
                            
                            # Capture intelligence BEFORE clearing slot or removing from memory
                            fleet_intel = {}
                            unified_confidence = 50
                            pensamento = ""
                            if slot_id > 0:
                                from services.firebase_service import firebase_service
                                slot_state = await firebase_service.get_slot(slot_id)
                                if slot_state:
                                    fleet_intel = slot_state.get("fleet_intel", {})
                                    unified_confidence = slot_state.get("unified_confidence", 50)
                                    pensamento = slot_state.get("pensamento", "")

                            harvest_label = "HARVEST" if is_partial_real else "FULL_CLOSE"
                            trade_report = (
                                f"--- PAPER EXECUTION V110.118 ({'PARTIAL HARVEST' if is_partial_real else 'FULL CLOSE'}) ---\n"
                                f"Symbol: {symbol} | Side: {side_pos}\n"
                                f"Entry: ${entry_price:.6f} | Exit: ${exit_price:.6f}\n"
                                f"Qty Fechada: {close_qty:.6f} | Qty Restante: {remaining_qty:.6f}\n"
                                f"PNL: ${final_pnl:.2f} | ROI: {harvest_roi:.1f}% | Reason: {reason}\n"
                                f"{'🌾 MOONBAG SOBREVIVE com residual!' if is_partial_real else '🛑 Posição totalmente fechada.'}"
                            )
                            
                            trade_data = {
                                "symbol": symbol,
                                "side": side_pos,
                                "entry_price": entry_price,
                                "exit_price": exit_price,
                                "qty": close_qty,  # [V110.118] qty da COLHEITA, não do total
                                "order_id": f"{symbol.replace('.P','')}_{int(pos.get('opened_at', 0) or time.time())}{'_harvest' if is_partial_real else ''}",
                                "pnl": final_pnl,
                                "slot_id": slot_id,
                                "slot_type": "MOONBAG" if is_partial_real else "SNIPER",
                                "close_reason": reason,
                                "final_roi": harvest_roi,
                                "closed_at": get_br_iso_str(),
                                "opened_at": pos.get("opened_at", 0),
                                "reasoning_report": trade_report,
                                "fleet_intel": fleet_intel,
                                "unified_confidence": unified_confidence,
                                "pensamento": pensamento,
                                "entry_margin": round(close_qty * entry_price * ct_val / leverage, 2),
                                "leverage": leverage,
                                "is_partial": is_partial_real,
                                "pnl_percent": round(harvest_roi, 2)
                            }

                            # Registrar no histórico
                            await bankroll_manager.register_sniper_trade(trade_data)
                            
                            if is_partial_real:
                                # [V110.118] PARCIAL: Moonbag sobrevive — NÃO limpar slot
                                # Apenas atualizar a quantidade e margem restantes na memória
                                pos["size"] = str(remaining_qty)
                                pos["entry_margin"] = str(round(remaining_qty * entry_price / leverage, 2))
                                logger.info(
                                    f"🌾 [PAPER-HARVEST] {symbol} | Colhido {close_qty:.6f} ({(close_qty/size)*100:.1f}%) "
                                    f"| Restante: {remaining_qty:.6f} | PNL Parcial: ${final_pnl:.2f} | ROI: {harvest_roi:.1f}%"
                                )
                                # Atualizar Firebase do Moonbag (se aplicável) sem resetar o slot
                                if slot_id > 0:
                                    from services.firebase_service import firebase_service
                                    # Se é um moonbag (emancipado), atualizar o registro do vault
                                    moonbags_state = await firebase_service.get_moonbags()
                                    t_moon = next((m for m in moonbags_state if self._strip_p(m.get("symbol", "")) == norm_symbol), None)
                                    if t_moon:
                                        await firebase_service.update_moonbag(t_moon["id"], {
                                            "qty": remaining_qty,
                                            "entry_margin": round(remaining_qty * entry_price / leverage, 2),
                                            "harvest_pnl_accumulated": round(
                                                float(t_moon.get("harvest_pnl_accumulated", 0)) + final_pnl, 2
                                            ),
                                            "last_harvest_at": int(time.time()),
                                            "last_harvest_roi": round(harvest_roi, 1),
                                            "pensamento": f"🌾 Colheita de {harvest_roi:.0f}% ROI realizada | Residual: {remaining_qty:.6f}"
                                        })
                                        logger.info(f"✅ [PAPER-HARVEST] Firebase Moonbag atualizado para {symbol}.")
                            else:
                                # FECHAMENTO TOTAL: remover de memória e limpar slot
                                register_closed = getattr(bankroll_manager, "register_recently_closed", None)
                                if callable(register_closed):
                                    register_closed(norm_symbol)
                                if pos in self.paper_positions:
                                    self.paper_positions.remove(pos)
                                elif pos in self.paper_moonbags:
                                    self.paper_moonbags.remove(pos)
                                logger.info(f"🛑 [PAPER-CLOSE] Full Close: {symbol} removido das posições.")

                                if slot_id > 0:
                                    from services.firebase_service import firebase_service
                                    await firebase_service.hard_reset_slot(slot_id, reason=f"PAPER_CLOSE_ATOMIC_{reason}", pnl=final_pnl, trade_data=trade_data)
                                    logger.info(f"🧹 [PAPER-SYNC] Slot {slot_id} resetado com audit log.")

                        except Exception as atomic_err:
                            logger.error(f"❌ [PAPER-ATOMIC-FAIL] Critical failure during {'harvest' if is_partial_real else 'closure'} for {symbol}: {atomic_err}")
                            raise atomic_err

                        # Cleanup pending after a small delay to let other loops sync
                        asyncio.create_task(self._cleanup_pending_closure(norm_symbol))
                        return True


                    except Exception as e:
                        logger.error(f"[PAPER] Error during position closure: {e}")
                        if pos in self.paper_positions:
                            self.paper_positions.remove(pos)
                        self.pending_closures.discard(norm_symbol)
                        return False
                return False

            # REAL MODE
            try:
                api_symbol = self._strip_p(symbol)
                close_side = "Sell" if side == "Buy" else "Buy"
                response = await asyncio.to_thread(session.place_order,
                    category=self.category,
                    symbol=api_symbol,
                    side=close_side,
                    orderType="Market",
                    qty=str(qty),
                    reduceOnly=True
                )
                # Cleanup pending
                asyncio.create_task(self._cleanup_pending_closure(norm_symbol))
                return True
            except Exception as e:
                logger.error(f"Error closing position for {symbol}: {e}")
                self.pending_closures.discard(norm_symbol)
                return False
        finally:
            # Release Redis Lock
            await self.redis.release_lock(f"close:{norm_symbol}")

    async def _cleanup_pending_closure(self, symbol: str, delay: int = 15):
        """V5.3.4: Helper to clear pending closure flag after a delay."""
        await asyncio.sleep(delay)
        self.pending_closures.discard(symbol)

    async def get_closed_pnl(self, symbol: str, limit: int = 5):
        """
        [V43.2] Fetches final PnL for closed trades.
        Increased default limit to 5 to avoid missing rapid-fire trades during sync.
        """
        if self.execution_mode == "PAPER":
            # Filter history by symbol
            relevant = [h for h in self.paper_orders_history if h["symbol"] == symbol]
            # Return last N
            return relevant[-limit:] if relevant else []

        async with self._http_semaphore:
            try:
                api_symbol = self._strip_p(symbol)
                # [V43.2] V5 Bybit API: Fetching closed PnL with higher limit
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.session.get_closed_pnl, 
                        category=self.category, 
                        symbol=api_symbol, 
                        limit=limit
                    ), 
                    timeout=10.0
                )
                
                result_list = response.get("result", {}).get("list", [])
                if not result_list:
                    # [V43.2] Traceability: Log when no history is found despite sync trigger
                    logger.debug(f"🔍 [OKX-REST] No closed PnL found for {symbol} in last {limit} trades.")
                return result_list
            except Exception as e:
                logger.error(f"Error fetching closed PnL for {symbol}: {e}")
                return []

    async def get_public_trade_history(self, symbol: str, limit: int = 50):
        """
        [V110.999] REST Fallback para cálculo de CVD ultra-resiliente via OKX.
        Se a OKX falhar ou der rate limit, recorre à API pública da Bybit de forma blindada.
        """
        async with self._http_semaphore:
            # 1. Tentar buscar dados públicos nativos da OKX
            try:
                from services.okx_service import okx_service
                inst_id = okx_service.to_okx_inst_id(symbol)
                url = f"https://www.okx.com/api/v5/market/trades?instId={inst_id}&limit={limit}"
                
                async with httpx.AsyncClient(timeout=4.0) as client:
                    response = await client.get(url)
                    if response.status_code == 200:
                        data = response.json()
                        if data.get("code") == "0" and data.get("data"):
                            okx_trades = data["data"]
                            translated = []
                            for t in okx_trades:
                                # Normaliza side para "Buy"/"Sell"
                                raw_side = t.get("side", "buy").lower()
                                side = "Buy" if raw_side == "buy" else "Sell"
                                
                                translated.append({
                                    "id": t.get("tradeId", ""),
                                    "price": t.get("px", "0"),
                                    "size": t.get("sz", "0"),
                                    "side": side,
                                    "time": t.get("ts", "")
                                })
                            if translated:
                                return translated
            except Exception as okx_err:
                logger.debug(f"[OKX-TRADE-HISTORY] Falha ao ler da OKX: {okx_err}")

            # 2. Fallback resiliente para Bybit (se a OKX falhar)
            try:
                api_symbol = self._strip_p(symbol)
                resp = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.session.get_public_trade_history,
                        category=self.category,
                        symbol=api_symbol,
                        limit=limit
                    ),
                    timeout=4.0
                )
                return resp.get("result", {}).get("list", [])
            except Exception as e:
                # Ocultar o warning espalhafatoso se for 403 comum de IP dos EUA da Bybit
                if "403" in str(e) or "ip is from the usa" in str(e).lower() or "rate limit" in str(e).lower():
                    logger.debug(f"Bybit trade fallback skipped (IP blocked or limited): {e}")
                else:
                    logger.warning(f"Error fetching public trades fallback for {symbol}: {e}")
                return []

    async def get_orderbook(self, symbol: str, limit: int = 50) -> dict:
        """[V12.0] Fetches L2 orderbook for localized depth analysis from OKX public API."""
        try:
            from services.okx_service import okx_service
            inst_id = okx_service.to_okx_inst_id(symbol)
            url = f"https://www.okx.com/api/v5/market/books?instId={inst_id}&sz={limit}"
            async with httpx.AsyncClient(timeout=4.0) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("code") == "0" and data.get("data"):
                        ob = data["data"][0]
                        # OKX retorna bids/asks como [[px, sz, ...], ...]
                        # Bybit espera: {"b": [[px, sz], ...], "a": [[px, sz], ...]}
                        bids = [[float(b[0]), float(b[1])] for b in ob.get("bids", [])]
                        asks = [[float(a[0]), float(a[1])] for a in ob.get("asks", [])]
                        return {
                            "b": bids,
                            "a": asks
                        }
            return {"b": [], "a": []}
        except Exception as e:
            logger.error(f"Error fetching orderbook from OKX for {symbol}: {e}")
            return {"b": [], "a": []}

    async def _fetch_klines_payload_limited(self, symbol: str, interval: str, fetch_limit: int, cache_key: str):
        global _GLOBAL_KLINES_CACHE

        try:
            from services.okx_service import okx_service
            inst_id = okx_service.to_okx_inst_id(symbol)
            interval_map = {
                "1": "1m", "3": "3m", "5": "5m", "15": "15m", "30": "30m",
                "60": "1H", "120": "2H", "240": "4H", "360": "6H", "720": "12H",
                "D": "1D", "W": "1W", "M": "1M",
                "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
                "1H": "1H", "2H": "2H", "4H": "4H", "6H": "6H", "12H": "12H",
                "1D": "1D", "1W": "1W", "1M": "1M",
            }
            bar = interval_map.get(str(interval), "1H")
            url = f"https://www.okx.com/api/v5/market/candles?instId={inst_id}&bar={bar}&limit={fetch_limit}"

            for attempt in range(2):
                response = await self._public_rate_limited_get(url, timeout=5.0, label=f"klines:{symbol}:{interval}")
                if response.status_code == 429:
                    await asyncio.sleep(0.25 * (attempt + 1))
                    continue
                if response.status_code != 200:
                    break

                data = response.json()
                if data.get("code") != "0" or not data.get("data"):
                    break

                formatted = []
                for candle in data.get("data", []):
                    if len(candle) < 5 or any(v is None for v in candle[:5]):
                        continue
                    try:
                        float(candle[1])
                        float(candle[2])
                        float(candle[3])
                        float(candle[4])
                    except ValueError:
                        continue

                    formatted.append([
                        candle[0],
                        candle[1],
                        candle[2],
                        candle[3],
                        candle[4],
                        candle[5] if len(candle) > 5 and candle[5] is not None else "0",
                        candle[6] if len(candle) > 6 and candle[6] is not None else "0",
                    ])

                if formatted:
                    _GLOBAL_KLINES_CACHE[cache_key] = (time.time(), formatted)
                    return formatted

        except Exception as e:
            logger.error(f"Error fetching klines from OKX public API for {symbol}: {e}")

        logger.warning(f"⚠️ [OKX-REST KLINES FALLBACK] Ativando contingencia de candles para {symbol} (Intervalo: {interval})")
        try:
            gate_interval_map = {
                "1": "1m", "3": "1m", "5": "5m", "15": "15m", "30": "30m",
                "60": "1h", "120": "2h", "240": "4h", "D": "1d",
                "1m": "1m", "3m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
                "1H": "1h", "2H": "2h", "4H": "4h", "1D": "1d",
            }
            gate_bar = gate_interval_map.get(str(interval), "1h")
            gate_sym = symbol.replace(".P", "").replace(".p", "").upper()
            for old, new in (("SHIB1000", "SHIB"), ("PEPE1000", "PEPE"), ("LUNA2", "LUNA")):
                gate_sym = gate_sym.replace(old, new)
            gate_sym = gate_sym[:-4] + "_USDT" if gate_sym.endswith("USDT") else gate_sym + "_USDT"
            gate_url = f"https://api.gateio.ws/api/v4/futures/usdt/candlesticks?contract={gate_sym}&interval={gate_bar}&limit={fetch_limit}"

            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(gate_url)
            if response.status_code == 200:
                gate_candles = response.json()
                if isinstance(gate_candles, list) and gate_candles:
                    formatted = []
                    for candle in gate_candles:
                        if isinstance(candle, dict) and "t" in candle and "o" in candle:
                            formatted.append([
                                str(int(candle["t"]) * 1000),
                                candle["o"],
                                candle["h"],
                                candle["l"],
                                candle["c"],
                                str(candle.get("v", "0")),
                                "0",
                            ])
                    if formatted:
                        logger.info(f"✅ [KLINES FALLBACK SUCCESS] Candles publicos da Gate.io obtidos com sucesso para {symbol}.")
                        _GLOBAL_KLINES_CACHE[cache_key] = (time.time(), formatted)
                        return formatted
        except Exception as gate_err:
            logger.debug(f"[GATEIO-KLINES-FALLBACK-TRY] Falha ao obter da Gate.io: {gate_err}")

        return []

    async def get_klines(self, symbol: str, interval: str = "60", limit: int = 20, *args, **kwargs):
        """Fetches historical klines for ATR and variation calculations from OKX Mainnet public API."""
        global _GLOBAL_KLINES_CACHE
        global _GLOBAL_KLINES_LOCKS
        if '_GLOBAL_KLINES_LOCKS' not in globals():
            _GLOBAL_KLINES_LOCKS = {}
            
        # [V120 OPTIMIZATION] Ignore limit in cache key to share the same cache for all requests of this interval.
        # Always fetch 144 candles (enough for 2H, 4H EMA, Daily, etc) to maximize cache hit rate.
        cache_key = f"{symbol}_{interval}_shared"
        fetch_limit = 144
        now = time.time()
        
        # 1. Check cache WITHOUT lock (fast path)
        if cache_key in _GLOBAL_KLINES_CACHE:
            ts, cached_data = _GLOBAL_KLINES_CACHE[cache_key]
            if now - ts < 180.0:  # Cache de 180 segundos (3 minutos) para aliviar rate limits
                return cached_data[:limit]
        
        # 2. Acquire lock to prevent Thundering Herd (multiple tasks asking for the same BTC candles at the same time)
        if cache_key not in _GLOBAL_KLINES_LOCKS:
            _GLOBAL_KLINES_LOCKS[cache_key] = asyncio.Lock()
            
        async with _GLOBAL_KLINES_LOCKS[cache_key]:
            # 3. Check cache again AFTER acquiring lock (someone else might have fetched it while we waited)
            now = time.time()
            if cache_key in _GLOBAL_KLINES_CACHE:
                ts, cached_data = _GLOBAL_KLINES_CACHE[cache_key]
                if now - ts < 180.0:
                    return cached_data[:limit]

            # Keep the per-key lock while fetching, so parallel radar workers share
            # one OKX/Gate request instead of stampeding the same symbol+interval.
            formatted = await self._fetch_klines_payload_limited(symbol, interval, fetch_limit, cache_key)
            return formatted[:limit] if formatted else []
                    
        # 4. Tentar obter via OKX
        try:
            from services.okx_service import okx_service
            inst_id = okx_service.to_okx_inst_id(symbol)
            
            # Mapeamento do intervalo Bybit -> OKX
            interval_map = {
                "1": "1m", "3": "3m", "5": "5m", "15": "15m", "30": "30m",
                "60": "1H", "120": "2H", "240": "4H", "360": "6H", "720": "12H",
                "D": "1D", "W": "1W", "M": "1M",
                "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
                "1H": "1H", "2H": "2H", "4H": "4H", "6H": "6H", "12H": "12H",
                "1D": "1D", "1W": "1W", "1M": "1M"
            }
            bar = interval_map.get(str(interval), "1H")
            url = f"https://www.okx.com/api/v5/market/candles?instId={inst_id}&bar={bar}&limit={fetch_limit}"
            
            max_retries = 3
            for attempt in range(max_retries):
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(url)
                    
                    if response.status_code == 429:
                        wait_time = 1.5 * (attempt + 1)
                        logger.warning(f"⚠️ [OKX-429] Rate limit atingido em get_klines para {symbol}. Tentativa {attempt+1}/{max_retries}. Aguardando {wait_time}s...")
                        await asyncio.sleep(wait_time)
                        continue
                        
                    if response.status_code == 200:
                        data = response.json()
                        if data.get("code") == "0" and data.get("data"):
                            okx_candles = data.get("data", [])
                            # OKX retorna: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
                            # Bybit espera: [start_time, open, high, low, close, volume, turnover]
                            formatted = []
                            for c in okx_candles:
                                if len(c) >= 5:
                                    # Blindagem contra valores nulos da OKX
                                    if c[0] is None or c[1] is None or c[2] is None or c[3] is None or c[4] is None:
                                        continue
                                    try:
                                        # Valida que todos os valores de preço são conversíveis para float
                                        float(c[1])
                                        float(c[2])
                                        float(c[3])
                                        float(c[4])
                                    except ValueError:
                                        continue # Ignora candle com preços quebrados
                                        
                                    formatted.append([
                                        c[0], # ts
                                        c[1], # o
                                        c[2], # h
                                        c[3], # l
                                        c[4], # c
                                        c[5] if (len(c) > 5 and c[5] is not None) else "0", # vol
                                        c[6] if (len(c) > 6 and c[6] is not None) else "0"  # volCcy
                                    ])
                            if formatted:
                                _GLOBAL_KLINES_CACHE[cache_key] = (time.time(), formatted)
                                return formatted[:limit]
                        break # Se o response foi 200 mas algo no JSON falhou, não é rate limit, quebra o retry.
                    else:
                        break # Status != 429 e != 200 (ex: 500, 404), quebra o retry.
                        
        except Exception as e:
            logger.error(f"Error fetching klines from OKX public API for {symbol}: {e}")

        # 5. FALLBACK DE ALTA DISPONIBILIDADE: Gate.io & Bybit APIs
        logger.warning(f"⚠️ [OKX-REST KLINES FALLBACK] Ativando contingência de candles para {symbol} (Intervalo: {interval})")
        
        # A. Tentar via Gate.io (Livre de Geoblock de IPs americanos do Railway)
        try:
            gate_interval_map = {
                "1": "1m", "3": "1m", "5": "5m", "15": "15m", "30": "30m",
                "60": "1h", "120": "2h", "240": "4h", "D": "1d",
                "1m": "1m", "3m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
                "1H": "1h", "2H": "2h", "4H": "4h", "1D": "1d"
            }
            gate_bar = gate_interval_map.get(str(interval), "1h")
            
            gate_sym = symbol.replace(".P", "").replace(".p", "").upper()
            if "SHIB1000" in gate_sym:
                gate_sym = gate_sym.replace("SHIB1000", "SHIB")
            if "PEPE1000" in gate_sym:
                gate_sym = gate_sym.replace("PEPE1000", "PEPE")
            if "LUNA2" in gate_sym:
                gate_sym = gate_sym.replace("LUNA2", "LUNA")
                
            if gate_sym.endswith("USDT"):
                gate_sym = gate_sym[:-4] + "_USDT"
            else:
                gate_sym = gate_sym + "_USDT"
                
            gate_url = f"https://api.gateio.ws/api/v4/futures/usdt/candlesticks?contract={gate_sym}&interval={gate_bar}&limit={limit}"
            
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(gate_url)
                if response.status_code == 200:
                    gate_candles = response.json()
                    if isinstance(gate_candles, list) and len(gate_candles) > 0:
                        formatted = []
                        for c in gate_candles:
                            if isinstance(c, dict) and "t" in c and "o" in c:
                                formatted.append([
                                    str(int(c["t"]) * 1000), # start_time em ms
                                    c["o"], # open
                                    c["h"], # high
                                    c["l"], # low
                                    c["c"], # close
                                    str(c.get("v", "0")), # volume
                                    "0"  # turnover
                                ])
                        if formatted:
                            logger.info(f"✅ [KLINES FALLBACK SUCCESS] Candles públicos da Gate.io obtidos com sucesso para {symbol}!")
                            _GLOBAL_KLINES_CACHE[cache_key] = (time.time(), formatted)
                            return formatted[:limit]
        except Exception as gate_err:
            logger.debug(f"[GATEIO-KLINES-FALLBACK-TRY] Falha ao obter da Gate.io: {gate_err}")

        # B. Sem contingência secundária: Gate.io é a única contingência de klines após a migração.
        # Caso Gate.io e OKX falhem, retornamos lista vazia para o sistema seguir.
        return []

    async def get_open_interest(self, symbol: str, interval: str = "1h") -> float:
        """
        [V15.5] Fetches the current Open Interest for a symbol from OKX Mainnet.
        """
        try:
            cache_key = symbol.replace(".P", "").upper()
            cached = self._open_interest_cache.get(cache_key)
            if cached and time.time() - cached.get("ts", 0.0) < 30.0:
                return cached.get("oi", 0.0)

            from services.okx_service import okx_service
            inst_id = okx_service.to_okx_inst_id(symbol)
            url = f"https://www.okx.com/api/v5/public/open-interest?instId={inst_id}"
            response = await self._public_rate_limited_get(url, timeout=4.0, label=f"open-interest:{symbol}")
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == "0" and data.get("data"):
                    oi = float(data["data"][0].get("oi", 0.0))
                    self._open_interest_cache[cache_key] = {
                        "oi": oi,
                        "ts": time.time(),
                        "raw_ts": data["data"][0].get("ts", str(int(time.time() * 1000))),
                    }
                    return oi
        except Exception as e:
            logger.error(f"Error fetching Open Interest from OKX for {symbol}: {e}")
        return 0.0

    async def get_open_interest_history(self, symbol: str, interval: str = "5min", limit: int = 5) -> List[Dict[str, Any]]:
        """
        [V46.0] Fetches historical Open Interest data from OKX.
        """
        try:
            cache_key = symbol.replace(".P", "").upper()
            cached = self._open_interest_cache.get(cache_key)
            if cached and time.time() - cached.get("ts", 0.0) < 30.0:
                return [{
                    "openInterest": str(cached.get("oi", 0.0)),
                    "timestamp": cached.get("raw_ts", str(int(time.time() * 1000))),
                }]

            from services.okx_service import okx_service
            inst_id = okx_service.to_okx_inst_id(symbol)
            url = f"https://www.okx.com/api/v5/public/open-interest?instId={inst_id}"
            async with httpx.AsyncClient(timeout=4.0) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("code") == "0" and data.get("data"):
                        oi_val = data["data"][0].get("oi", "0")
                        ts = data["data"][0].get("ts", str(int(time.time() * 1000)))
                        # Retorna lista compatível com Bybit
                        return [{"openInterest": oi_val, "timestamp": ts}]
        except Exception as e:
            logger.error(f"Error fetching OI history from OKX for {symbol}: {e}")
        return []

    async def get_account_ratio(self, symbol: str, period: str = "5min") -> float:
        """
        [V15.5] Fetches the Long/Short Account Ratio for a symbol from OKX Mainnet.
        """
        try:
            from services.okx_service import okx_service
            inst_id = okx_service.to_okx_inst_id(symbol)
            ccy = inst_id.split("-")[0]

            okx_period = "5m"
            period_norm = (period or "").lower()
            if "15" in period_norm:
                okx_period = "15m"
            elif "30" in period_norm:
                okx_period = "30m"
            elif "4h" in period_norm:
                okx_period = "4h"
            elif "1h" in period_norm:
                okx_period = "1h"
            elif "1d" in period_norm or period_norm == "d":
                okx_period = "1d"

            cache_key = f"{ccy}:{okx_period}"
            cached = self._account_ratio_cache.get(cache_key)
            if cached:
                ts, ratio = cached
                if time.time() - ts < self._account_ratio_cache_ttl:
                    return ratio

            if cache_key not in self._account_ratio_locks:
                self._account_ratio_locks[cache_key] = asyncio.Lock()

            async with self._account_ratio_locks[cache_key]:
                cached = self._account_ratio_cache.get(cache_key)
                if cached:
                    ts, ratio = cached
                    if time.time() - ts < self._account_ratio_cache_ttl:
                        return ratio

                url = (
                    "https://www.okx.com/api/v5/rubik/stat/contracts/"
                    f"long-short-account-ratio?ccy={ccy}&period={okx_period}"
                )
                response = await self._public_rate_limited_get(
                    url,
                    timeout=10.0,
                    label=f"account-ratio:{ccy}:{okx_period}",
                    min_interval=self._rubik_min_interval,
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get("code") == "0" and data.get("data"):
                        ratio_data = data.get("data", [])
                        if ratio_data:
                            item = ratio_data[0]
                            if isinstance(item, dict):
                                ratio = float(item.get("ratio", 1.0))
                            elif isinstance(item, list) and len(item) >= 2:
                                ratio = float(item[1])
                            else:
                                ratio = 1.0
                            self._account_ratio_cache[cache_key] = (time.time(), ratio)
                            return ratio
                    logger.debug(
                        "[OKX REST Rubik] account ratio unavailable for %s: %s",
                        ccy,
                        data.get("msg"),
                    )
                else:
                    logger.debug(
                        "[OKX REST Rubik] HTTP %s fetching account ratio for %s",
                        response.status_code,
                        ccy,
                    )
        except Exception as e:
            logger.error(f"Error fetching Account Ratio from OKX for {symbol}: {e}")
            return 1.0
        return 1.0

    # [V25.1] Funding Rate Cache
    _funding_cache: dict = {}  # { symbol: { rate, timestamp } }
    
    async def get_funding_rate(self, symbol: str) -> float:
        """
        [V25.1] Fetches the current funding rate for a symbol from OKX public API.
        Positive rate = longs pay shorts (bearish pressure).
        Negative rate = shorts pay longs (squeeze potential for longs).
        Returns rate as decimal (e.g., 0.0001 = 0.01%).
        Cached for 60s to avoid excessive API calls.
        """
        async with self._http_semaphore:
            try:
                api_symbol = self._strip_p(symbol)
                
                # Check cache (60s TTL)
                cached = self._funding_cache.get(api_symbol)
                if cached and (time.time() - cached.get("ts", 0)) < 60:
                    return cached["rate"]
                
                from services.okx_service import okx_service
                inst_id = okx_service.to_okx_inst_id(symbol)
                url = f"https://www.okx.com/api/v5/public/funding-rate?instId={inst_id}"
                
                async with httpx.AsyncClient(timeout=4.0) as client:
                    response = await client.get(url)
                    if response.status_code == 200:
                        data = response.json()
                        if data.get("code") == "0" and data.get("data"):
                            rate = float(data["data"][0].get("fundingRate", 0))
                            # Cache result
                            self._funding_cache[api_symbol] = {"rate": rate, "ts": time.time()}
                            return rate
                            
                return 0.0
            except Exception as e:
                logger.warning(f"Error fetching funding rate from OKX for {symbol}: {e}")
                return 0.0
    
    async def set_trading_stop(self, category: str, symbol: str, stopLoss: str, slTriggerBy: str = None, tpslMode: str = None, positionIdx: int = None, side: str = None):
        """
        Sets the stop loss for a position.
        [V43.0] Hedge Mode Support: Automatically resolves positionIdx based on side if not provided.
        """
        if self.execution_mode == "PAPER":
            api_symbol = self._strip_p(symbol)
            logger.info(f"[PAPER] Updating Stop Loss for {api_symbol} to {stopLoss}")
            # [V110.28.2 FIX] Busca em paper_positions E paper_moonbags (garante Hard-Lock 110%)
            pos = next((p for p in self.paper_positions if p["symbol"] == api_symbol), None)
            if not pos:
                pos = next((p for p in self.paper_moonbags if p["symbol"] == api_symbol), None)
            if pos:
                pos["stopLoss"] = str(stopLoss)
                await self._save_paper_state()
                logger.info(f"[PAPER] Stop Loss de {api_symbol} atualizado para {stopLoss} com sucesso.")
                return {"retCode": 0, "result": {}}
            else:
                logger.warning(f"[PAPER] Position {api_symbol} não encontrada em positions nem moonbags.")
                return {"retCode": 10001, "retMsg": f"Position {api_symbol} not found in Paper Trading"}

        try:
            api_symbol = self._strip_p(symbol)
            
            # [V43.0] Hedge Mode Auto-Resolution
            if positionIdx is None:
                if side:
                    # In Hedge Mode: 1=Buy, 2=Sell. In One-Way: 0.
                    # We default to 0 but if we have a side, we can't be sure of the mode without an API call.
                    # Optimization: Fetch one position to see its structure.
                    active_pos = await self.get_active_positions(symbol=api_symbol)
                    if active_pos:
                        positionIdx = active_pos[0].get("positionIdx", 0)
                    else:
                        positionIdx = 0 
                else:
                    positionIdx = 0

            params = {
                "category": category,
                "symbol": api_symbol,
                "stopLoss": stopLoss,
                "positionIdx": positionIdx
            }
            if slTriggerBy: params["slTriggerBy"] = slTriggerBy
            if tpslMode: params["tpslMode"] = tpslMode
            
            response = await asyncio.to_thread(self.session.set_trading_stop, **params)
            logger.info(f"set_trading_stop response for {symbol} (idx:{positionIdx}): {response}")
            return response
        except Exception as e:
            logger.error(f"Error setting SL for {symbol}: {e}")
            return {"retCode": -1, "retMsg": str(e)}

    async def run_real_execution_loop(self):
        """
        [V110.0] Smart SL Engine for REAL Mode.
        Monitors both Tactical Slots and Moonbag Vault.
        """
        if self.execution_mode != "REAL":
            return

        from services.execution_protocol import execution_protocol
        from services.firebase_service import firebase_service

        logger.info("🚀 [V110.0] REAL Execution Engine (Tactical + Vault) ACTIVATING...")

        while True:
            try:
                from services.sentinel_auditor import sentinel_auditor
                sentinel_auditor.record_heartbeat("real_execution_loop")

                # 1. Get active slots AND moonbags from Firebase
                slots = await firebase_service.get_active_slots()
                moonbags = await firebase_service.get_moonbags()
                
                active_tactical = [s for s in slots if s.get("symbol") and s.get("entry_price", 0) > 0]
                active_positions = active_tactical + moonbags
                
                if not active_positions:
                    await asyncio.sleep(5)
                    continue
                # 2. Batch fetch tickers & positions
                resp = await self.get_tickers()
                ticker_list = resp.get("result", {}).get("list", [])
                price_map = {t["symbol"]: float(t.get("lastPrice", 0)) for t in ticker_list}

                # [V110.125] Position Verification: Fetch real positions once per loop for cross-check
                real_positions = await self.get_active_positions()
                active_real_symbols = {p['symbol'].replace('.P', '').upper() for p in real_positions}

                # 3. Process each position
                for slot in active_positions:
                    try:
                        symbol = self._strip_p(slot["symbol"])
                        current_price = price_map.get(symbol, 0)
                        if current_price <= 0: continue

                        is_moonbag = slot.get("status") == "EMANCIPATED"
                        moon_uuid = slot.get("id") if is_moonbag else None

                        # [V110.125] GHOST MOONBAG GUARD: Se é moonbag e não existe na Bybit, ignore ou purgue
                        if is_moonbag and symbol not in active_real_symbols:
                            opened_at = slot.get("opened_at", 0)
                            if (time.time() - opened_at) > 300: # 5 min grace period
                                logger.warning(f"🌙 [GHOST-PURGE] Moonbag {symbol} não encontrada na Bybit. Removendo do Vault.")
                                await firebase_service.remove_moonbag(moon_uuid, reason="GHOST_SYNC_OKX")
                                continue

                        slot_data = {
                            "symbol": symbol,
                            "side": slot.get("side", "Buy"),
                            "entry_price": float(slot.get("entry_price", 0)),
                            "current_stop": float(slot.get("current_stop", 0)),
                            "target_price": float(slot.get("target_price", 0)),
                            "structural_target": float(slot.get("structural_target", 0)),
                            "slot_type": slot.get("slot_type", "TREND"),
                            "slot_id": slot.get("id"),
                            "status": slot.get("status"),
                            "sentinel_retests": slot.get("sentinel_retests", 0),
                            "partial_tp_hit": slot.get("partial_tp_hit", False),
                            "move_room_pct": slot.get("move_room_pct", 2.0),
                            "opened_at": slot.get("opened_at", 0),
                            "maestria_guard_active": slot.get("maestria_guard_active", False),
                            "sentinel_first_hit_at": slot.get("sentinel_first_hit_at", 0),
                        }

                        # [V110.125] ROI INTEGRITY GUARD
                        if slot_data["entry_price"] <= 0:
                            logger.error(f"❌ [DATA-CORRUPT] {symbol} com entry_price zero. Pulando processamento.")
                            continue

                        # 4. Execute Logic
                        should_close, reason, new_sl = await execution_protocol.process_order_logic(slot_data, current_price)

                        # [SENTINEL 3.0] Ativação da Paciência Diplomática
                        if reason == "SENTINEL_ACTIVATE":
                            upd = {"sentinel_first_hit_at": new_sl} 
                            if is_moonbag: await firebase_service.update_moonbag(moon_uuid, upd)
                            else: await firebase_service.update_slot(slot["id"], upd)
                            continue

                        # [V110.6] EMANCIPATION TRIGGER (Real Mode)
                        if reason == "EMANCIPATE_SLOT" and not is_moonbag:
                            if symbol in self.emancipating_symbols:
                                logger.info(f"🛡️ [V110.4] {symbol} já está em processo de emancipação. Aguardando...")
                                continue
                            
                            self.emancipating_symbols.add(symbol)
                            try:
                                # [V110.6] ACQUISITION LOCK: Update Exchange BEFORE liberating slot in Firebase
                                logger.info(f"🚀 [V110.6 EMANCIPATE-SYNC] Iniciando atualização na Bybit para {symbol}...")
                                
                                # 1. Limpa TakeProfit (Surf Mode)
                                tp_clear = await self.set_trading_stop(symbol, takeProfit="0")
                                
                                # 2. Define StopLoss Progressivo
                                success = True
                                rounded_sl = 0
                                if new_sl:
                                    rounded_sl = await self.round_price(symbol, new_sl)
                                    sl_result = await self.set_trading_stop(
                                        category="linear", symbol=symbol,
                                        stopLoss=str(rounded_sl), side=slot_data["side"]
                                    )
                                    if sl_result.get("retCode") != 0:
                                        ret_code = sl_result.get("retCode")
                                        ret_msg = str(sl_result.get("retMsg", "")).lower()
                                        if ret_code in (10001, 130024, 130073, 140024, 130074) or "not modified" in ret_msg or "same" in ret_msg:
                                            logger.info(f"✅ [REAL] SL de {symbol} já está posicionado em +110% (Code {ret_code}). Avançando com Emancipação.")
                                        else:
                                            logger.error(f"❌ [V110.6] Falha ao definir SL de emancipação para {symbol}: {sl_result}")
                                            success = False
                                
                                # 3. SOMENTE se a Bybit confirmar, promove no Firebase
                                if success:
                                    new_moon_uuid = await firebase_service.promote_to_moonbag(slot.get("id"))
                                    if new_moon_uuid:
                                        logger.info(f"✅ [V110.6] {symbol} promovido para Moonbag após confirmação da Bybit.")
                                        if rounded_sl > 0:
                                            await firebase_service.update_moonbag(new_moon_uuid, {"current_stop": rounded_sl, "timestamp_last_update": time.time()})
                                else:
                                    logger.warning(f"⚠️ [V110.6] Emancipação abortada para {symbol} devido a falha na corretora. O slot permanece tático.")
                            finally:
                                # Remove o guard após um pequeno delay para sincronização
                                asyncio.create_task(self._release_emancipation_guard(symbol))
                            continue

                        # 5a. Handle SL Update
                        if new_sl is not None and not should_close:
                            current_sl = float(slot.get("current_stop", 0))
                            side_norm = slot_data["side"].lower()
                            
                            is_improvement = (side_norm == "buy" and new_sl > current_sl) or \
                                             (side_norm == "sell" and (current_sl == 0 or new_sl < current_sl)) or \
                                             (reason == "RESCUE_MOVE_SL_BREAKEVEN")

                            if is_improvement:
                                rounded_sl = await self.round_price(symbol, new_sl)
                                result = await self.set_trading_stop(
                                    category="linear", symbol=symbol,
                                    stopLoss=str(rounded_sl), side=slot_data["side"]
                                )
                                if result.get("retCode") == 0:
                                    # [V123] Calcula status_risco baseado no ROI para atualizar o badge da UI
                                    _roi_now = execution_protocol.calculate_roi(slot_data['entry_price'], current_price, side_norm, float(slot_data.get('leverage', 50)))
                                    if _roi_now >= 110.0:   _status_risco = "PROFIT_LOCK"
                                    elif _roi_now >= 70.0:  _status_risco = "RISCO_ZERO"
                                    elif _roi_now >= 30.0:  _status_risco = "SL_0"
                                    else:                   _status_risco = "MONITORANDO"
                                    upd = {"current_stop": rounded_sl, "status_risco": _status_risco, "timestamp_last_update": time.time()}
                                    if is_moonbag: await firebase_service.update_moonbag(moon_uuid, upd)
                                    else: await firebase_service.update_slot(slot["id"], upd)
                                    logger.info(f"🛡️ [V123 ESCADINHA] {symbol} ROI: {_roi_now:.1f}% | SL: {rounded_sl} | Status: {_status_risco}")

                        # 5b. Status Updates Sem Fechamento (ex: MAESTRIA)
                        if reason == "MAESTRIA_GUARD_ACTIVATE" and not should_close:
                            if is_moonbag: await firebase_service.update_moonbag(moon_uuid, {"maestria_guard_active": True})
                            else: await firebase_service.update_slot(slot["id"], {"maestria_guard_active": True})

                        # 5b. Handle Partial Harvest or Full Closure
                        elif should_close or reason == "PARTIAL_HARVEST":
                            logger.info(f"🚜 [HARVESTER] Decision for {symbol}: {reason}")
                            try:
                                from services.bankroll import bankroll_manager
                                pos_list = await self.get_active_positions(symbol=symbol)
                                for p in pos_list:
                                    q = float(p.get("size", 0))
                                    if q <= 0: continue
                                    
                                    if reason == "PARTIAL_HARVEST":
                                        # Payload is in new_sl (which is harvest_res)
                                        harvest_res = new_sl
                                        proportion = harvest_res.get("proportion", 0.9)
                                        close_qty = await self.round_qty(symbol, q * proportion)
                                        
                                        if close_qty > 0:
                                            logger.warning(f"🌾 [REAL-HARVEST] Executing partial harvest for {symbol}: {close_qty} units ({proportion*100:.1f}%)")
                                            success = await self.close_position(symbol, p["side"], close_qty, reason=f"HARVEST_{harvest_res.get('target_level')}")
                                            if success:
                                                # Log trade manually for Real mode as it won't appear in orphan sync yet
                                                # Calculate estimated PnL for the harvest
                                                entry_p = float(p.get("avgPrice", 0))
                                                roi_val = harvest_res.get("current_roi", 0)
                                                margin_used = (close_qty * entry_p) / 50.0
                                                est_pnl = margin_used * (roi_val / 100.0)
                                                
                                                trade_data = {
                                                    "symbol": symbol,
                                                    "side": p["side"],
                                                    "entry_price": entry_p,
                                                    "exit_price": current_price,
                                                    "qty": close_qty,
                                                    "pnl": est_pnl,
                                                    "pnl_percent": roi_val,
                                                    "slot_id": slot.get("id", 0),
                                                    "slot_type": "MOONBAG",
                                                    "close_reason": f"HARVEST_{harvest_res.get('target_level')}",
                                                    "order_id": f"{symbol.replace('.P','')}_{slot.get('opened_at', int(time.time()))}_harvest"
                                                }
                                                await bankroll_manager.register_sniper_trade(trade_data)
                                                
                                                # Update moonbag record with new qty
                                                await firebase_service.update_moonbag(moon_uuid, {
                                                    "qty": q - close_qty,
                                                    "entry_margin": ((q - close_qty) * entry_p) / 50.0,
                                                    "pensamento": f"🌾 Colheita de 500% ROI realizada em {harvest_res.get('target_level')}"
                                                })
                                    else:
                                        # Full Closure
                                        logger.warning(f"🛑 [REAL EXIT] {symbol} | Reason: {reason}")
                                        success = await self.close_position(symbol, p["side"], q, reason=reason)
                                        if success and is_moonbag:
                                            # Register trade before removing
                                            entry_p = float(p.get("avgPrice", 0))
                                            roi_val = execution_protocol.calculate_roi(entry_p, current_price, p["side"])
                                            margin_used = (q * entry_p) / 50.0
                                            est_pnl = margin_used * (roi_val / 100.0)
                                            
                                            trade_data = {
                                                "symbol": symbol,
                                                "side": p["side"],
                                                "entry_price": entry_p,
                                                "exit_price": current_price,
                                                "qty": q,
                                                "pnl": est_pnl,
                                                "pnl_percent": roi_val,
                                                "slot_id": slot.get("id", 0),
                                                "slot_type": "MOONBAG",
                                                "close_reason": reason,
                                                "order_id": f"{symbol.replace('.P','')}_{slot.get('opened_at', int(time.time()))}"
                                            }
                                            await bankroll_manager.register_sniper_trade(trade_data)
                                            await firebase_service.remove_moonbag(moon_uuid, reason=reason)
                                        elif success and not is_moonbag:
                                            # [V125] FIX: Slots táticos (BLITZ, etc) agora registram histórico no Vault
                                            # Antes: 'pass' → histórico ficava vazio para todas as ordens paper normais
                                            try:
                                                entry_p = float(slot.get("entry_price", 0)) if slot else 0
                                                qty_closed = q
                                                roi_val = execution_protocol.calculate_roi(entry_p, current_price, p["side"], float(slot.get("leverage", 50))) if entry_p > 0 else 0
                                                # [V110.701 FIX] For PAPER mode, use fixed margin per slot (10% of $100 = $10)
                                                margin_used = float(slot.get("entry_margin", 0)) or (10.0 if self.execution_mode == "PAPER" else ((qty_closed * entry_p) / float(slot.get("leverage", 50) or 50)))
                                                est_pnl = (roi_val / 100.0) * margin_used
                                                from services.time_utils import get_br_iso_str
                                                slot_type_val = slot.get("slot_type", "BLITZ_30M") if slot else "BLITZ_30M"
                                                genesis_id = slot.get("genesis_id", f"{symbol}_{int(time.time())}") if slot else f"{symbol}_{int(time.time())}"
                                                trade_data_paper = {
                                                    "symbol": symbol,
                                                    "side": p["side"],
                                                    "entry_price": entry_p,
                                                    "exit_price": current_price,
                                                    "qty": qty_closed,
                                                    "pnl": round(est_pnl, 4),
                                                    "pnl_percent": round(roi_val, 2),
                                                    "entry_margin": round(margin_used, 4),
                                                    "leverage": float(slot.get("leverage", 50)) if slot else 50,
                                                    "slot_id": slot.get("id", 0) if slot else 0,
                                                    "slot_type": slot_type_val,
                                                    "close_reason": reason,
                                                    "order_id": genesis_id,
                                                    "score": slot.get("score", 0) if slot else 0,
                                                    "pensamento": slot.get("pensamento", "") if slot else "",
                                                    "fleet_intel": slot.get("fleet_intel", {}) if slot else {},
                                                    "closed_at": get_br_iso_str(),
                                                    "final_roi": round(roi_val, 2),
                                                    "current_stop_at_close": float(slot.get("current_stop", 0)) if slot else 0,
                                                }
                                                from services.bankroll import bankroll_manager
                                                await bankroll_manager.register_sniper_trade(trade_data_paper)
                                                logger.info(f"✅ [V125 PAPER-HISTORY] {symbol} | {reason} | ROI: {roi_val:.1f}% | PnL: ${est_pnl:.2f} registrado no Vault.")
                                            except Exception as hist_err:
                                                logger.error(f"❌ [V125 PAPER-HISTORY] Erro ao registrar histórico de {symbol}: {hist_err}")
                            except Exception as ce: logger.error(f"Error handling closure/harvest for {symbol}: {ce}")


                    except Exception as se:
                        logger.error(f"Error processing {slot.get('symbol')}: {se}")

                # UI PNL Pulse
                if active_tactical:
                    pnl_summary = []
                    for s in active_tactical:
                        p_sym = self._strip_p(s["symbol"])
                        cur_p = price_map.get(p_sym, 0)
                        if cur_p > 0:
                            entry = float(s.get("entry_price", 0))
                            if entry > 0:
                                side = s.get("side", "Buy")
                                qty = float(s.get("qty") or s.get("size") or 0)
                                # [V110.128] Standardized PnL Calculation: (ROI/100) * Margin
                                # [V110.701 FIX] For PAPER mode, use fixed margin per slot (10% of $100 = $10)
                                margin = float(s.get("entry_margin") or (10.0 if self.execution_mode == "PAPER" else (qty * entry / 50.0)))
                                roi = execution_protocol.calculate_roi(entry, cur_p, side)
                                p_usd = (roi / 100.0) * margin
                                
                                pnl_summary.append({
                                    "symbol": s["symbol"],
                                    "roi": roi,
                                    "pnl_usd": round(p_usd, 2)
                                })
                    if pnl_summary:
                        await self.redis.publish_update("ui_updates", {"type": "PNL_PULSE", "data": pnl_summary})

            except Exception as e:
                logger.error(f"[REAL ENGINE] Loop error: {e}")

            await asyncio.sleep(3)

    async def run_paper_execution_loop(self):
        """
        [V110.0] Engine de execução blindada para modo PAPER.
        Monitors both paper_positions and paper_moonbags.
        """
        if self.execution_mode != "PAPER":
            return

        from services.okx_ws_public import okx_ws_public_service
        from services.execution_protocol import execution_protocol
        from services.firebase_service import firebase_service

        logger.info("🚀 [V110.12.12] PAPER Execution Engine (Tactical + Vault) ACTIVATING...")
        
        while True:
            try:
                from services.sentinel_auditor import sentinel_auditor
                sentinel_auditor.record_heartbeat("paper_execution_loop")

                # [V110.23.5] Periodically refresh state from Firestore if any other instance modified it
                # (Every 5 minutes or based on a last-update flag if we wanted to be fancy)
                if time.time() - self._last_paper_load_time > 300:
                    await self._load_paper_state()
                    # [V110.64 FIX] Removido 'continue' que causava skip do ciclo inteiro após reload

                combined_paper = self.paper_positions + self.paper_moonbags
                if not combined_paper:
                    await asyncio.sleep(2)
                    continue

                # 1. Fetch prices
                price_map = {}
                for pos in combined_paper:
                    sym = pos["symbol"]
                    ws_price = okx_ws_public_service.get_current_price(sym)
                    if ws_price and ws_price > 0: price_map[sym] = ws_price
                    else:
                        ticker = await self.get_tickers(symbol=sym)
                        t_list = ticker.get("result", {}).get("list", [])
                        if t_list: price_map[sym] = float(t_list[0].get("lastPrice", 0))

                # 2. Get Firebase slots
                slots = await firebase_service.get_active_slots()
                slots_by_symbol = {self._strip_p(s.get("symbol")): s for s in slots if s.get("symbol")}

                # 3. Process each position
                for pos in combined_paper:
                    symbol = pos.get("symbol", "UNKNOWN")
                    try:
                        current_price = price_map.get(symbol, 0)
                        if current_price <= 0: continue

                        is_moonbag = pos.get("status") == "EMANCIPATED"
                        slot = slots_by_symbol.get(symbol)
                        
                        slot_data = {
                            "symbol": symbol,
                            "side": pos.get("side", "Buy"),
                            "entry_price": float(pos.get("avgPrice", 0)),
                            "current_stop": float(pos.get("stopLoss", 0)) if pos.get("stopLoss") else 0,
                            "target_price": float(pos.get("takeProfit", 0)) if pos.get("takeProfit") else 0,
                            "slot_type": slot.get("slot_type", "SNIPER") if slot else "SNIPER",
                            "slot_id": slot.get("id") if slot else None,
                            "status": pos.get("status"),
                            "opened_at": pos.get("opened_at", 0),
                            "maestria_guard_active": pos.get("maestria_guard_active", False),
                            "sentinel_first_hit_at": slot.get("sentinel_first_hit_at", 0) if slot else 0,
                            # [V110.28.2 FIX] Campos ausentes que afetam os triggers da Escadinha
                            "structural_target": float(slot.get("structural_target", 0)) if slot else 0,
                            "score": slot.get("score", 0) if slot else 0,
                            "is_market_ranging": slot.get("is_market_ranging", False) if slot else False,
                            "id": slot.get("id", 0) if slot else 0,
                        }

                        from services.execution_protocol import execution_protocol
                        roi = execution_protocol.calculate_roi(slot_data["entry_price"], current_price, slot_data["side"])
                        should_close, reason, new_sl = await execution_protocol.process_order_logic(slot_data, current_price)
                        # [V110.100.2] ABSOLUTE ORDER (Sem saida parcial)
                        # A ordem inteira será conduzida até a emancipação completa.

                        # [V110.118 FIX-A] SENTINEL EARLY EXIT: Deve ser interceptado ANTES
                        # do bloco genérico de new_sl para evitar que o timestamp (time.time())
                        # seja gravado como stopLoss no Firebase e na memória Paper.
                        if reason == "SENTINEL_ACTIVATE":
                            current_phase = execution_protocol.get_sl_phase(roi, scale=1.0, slot_data=slot_data)
                            upd = {
                                "sentinel_first_hit_at": new_sl,  # new_sl aqui É o timestamp — correto
                                "visual_status": current_phase,
                                "sl_phase": current_phase
                            }
                            if is_moonbag:
                                moonbags_fb = await firebase_service.get_moonbags()
                                t_moon = next((m for m in moonbags_fb if m.get("symbol") == symbol), None)
                                if t_moon: await firebase_service.update_moonbag(t_moon["id"], upd)
                            elif slot:
                                await firebase_service.update_slot(slot["id"], upd)
                            continue  # EARLY EXIT: nunca chega no bloco de SL abaixo

                        # Se houve mudança de SL pela Escadinha
                        if new_sl and new_sl != slot_data["current_stop"]:
                            # [V110.118 FIX-A] SANITY GUARD: Rejeita timestamps como SL.
                            # Qualquer valor > 1 bilhão não é um preço de ativo — é um bug.
                            if isinstance(new_sl, (int, float)) and new_sl > 1_000_000_000:
                                logger.error(f"🚨 [V110.118 SL-GHOST-BLOCK] {symbol}: new_sl={new_sl:.0f} é um timestamp! Bloqueando gravação no stopLoss.")
                                new_sl = None
                            else:
                                pos["stopLoss"] = str(new_sl)
                                if slot:
                                    current_phase = execution_protocol.get_sl_phase(roi, scale=1.0, slot_data=slot_data)
                                    await firebase_service.update_slot(slot["id"], {
                                        "current_stop": new_sl,
                                        "visual_status": current_phase,
                                        "sl_phase": current_phase
                                    })
                                await self._save_paper_state()

                                # Do not skip directly if this was an emancipation trigger!
                                if reason != "EMANCIPATE_SLOT":
                                    continue
                        # [V110.65] Sincronização periódica da fase visual (mesmo sem mudança de SL)
                        if slot and int(time.time()) % 5 == 0: # A cada ~5s
                            current_phase = execution_protocol.get_sl_phase(roi, scale=1.0, slot_data=slot_data)
                            if slot.get("visual_status") != current_phase:
                                await firebase_service.update_slot(slot["id"], {
                                    "visual_status": current_phase,
                                    "sl_phase": current_phase
                                })

                        # [V110.6] EMANCIPATION TRIGGER (Paper Mode)
                        if reason == "EMANCIPATE_SLOT" and not is_moonbag:
                            if symbol in self.emancipating_symbols:
                                logger.info(f"🛡️ [V110.4 PAPER] {symbol} já está em processo de emancipação. Aguardando...")
                                continue

                            # [V110.28.2] PERPETUAL SURF: Mover 100% da ordem (Cheia) para o Vault.
                            # Liberar slot tático sem reduzir o tamanho da posição.
                            logger.info(f"🚀 [V110.28.2 PAPER-SYNC] Iniciando emancipação de ORDEM CHEIA para {symbol}...")
                            self.emancipating_symbols.add(symbol)
                            try:
                                # 1. Atualiza o estado local (Simulando a corretora)
                                pos["status"] = "EMANCIPATED"
                                pos["takeProfit"] = "0"
                                if new_sl: pos["stopLoss"] = str(new_sl)
                                
                                # Move para moonbags na memória
                                if pos in self.paper_positions:
                                    self.paper_positions.remove(pos)
                                if pos not in self.paper_moonbags:
                                    self.paper_moonbags.append(pos)
                                
                                await self._save_paper_state()
                                
                                # 2. Promove no Firebase (Liberação da vaga tática)
                                # Somente após o estado local estar salvo
                                moon_uuid = await firebase_service.promote_to_moonbag(slot["id"]) if slot else None
                                if moon_uuid:
                                    pos["moon_uuid"] = moon_uuid # [V110.128.1] Persist ID for atomic closure
                                    if new_sl:
                                        await firebase_service.update_moonbag(moon_uuid, {"current_stop": new_sl, "timestamp_last_update": time.time()})
                                    logger.info(f"[V110.6 PAPER] {symbol} promovido com sucesso no Firebase (ID: {moon_uuid}).")
                                else:
                                    # [V110.136.2 F1] EMANCIPATION RETRY GUARD
                                    # promote_to_moonbag falhou (retornou None). O slot do Firebase nao foi liberado.
                                    # Revertemos o estado em memoria para que o proximo ciclo tente novamente.
                                    logger.error(
                                        f"[V110.136.2 EMANCIPATION-FAIL] promote_to_moonbag falhou para {symbol}. "
                                        f"Revertendo estado em memoria — proximo ciclo tentara novamente."
                                    )
                                    pos["status"] = None
                                    pos["takeProfit"] = str(slot.get("target_price", "0")) if slot else "0"
                                    if pos in self.paper_moonbags:
                                        self.paper_moonbags.remove(pos)
                                    if pos not in self.paper_positions:
                                        self.paper_positions.append(pos)
                                    await self._save_paper_state()
                            finally:
                                asyncio.create_task(self._release_emancipation_guard(symbol))
                            continue

                        # 4a. Update SL
                        if new_sl is not None and not should_close:
                            current_sl = float(pos.get("stopLoss", 0)) if pos.get("stopLoss") else 0
                            side_norm = slot_data["side"].lower()
                            is_improvement = (side_norm == "buy" and new_sl > current_sl) or \
                                             (side_norm == "sell" and (current_sl == 0 or new_sl < current_sl))
                            
                            if is_improvement:
                                pos["stopLoss"] = str(new_sl)
                                await self._save_paper_state()
                                if is_moonbag:
                                    moonbags = await firebase_service.get_moonbags()
                                    target_moon = next((m for m in moonbags if m.get("symbol") == symbol), None)
                                    if target_moon: await firebase_service.update_moonbag(target_moon["id"], {"current_stop": new_sl})
                                elif slot:
                                    await firebase_service.update_slot(slot["id"], {"current_stop": new_sl})

                        # 4b. Status Updates Sem Fechamento (ex: MAESTRIA)
                        if reason == "MAESTRIA_GUARD_ACTIVATE" and not should_close:
                            pos["maestria_guard_active"] = True
                            await self._save_paper_state()
                            if slot: await firebase_service.update_slot(slot["id"], {"maestria_guard_active": True})

                        # 4b. Close or Partial Harvest
                        elif should_close or reason == "PARTIAL_HARVEST":
                            try:
                                from services.bankroll import bankroll_manager
                                qty = float(pos.get("size", 0))
                                
                                if reason == "PARTIAL_HARVEST":
                                    harvest_res = new_sl
                                    proportion = harvest_res.get("proportion", 0.9)
                                    close_qty = qty * proportion
                                    
                                    if close_qty <= 0:
                                        logger.warning(f"⚠️ [PAPER-HARVEST] {symbol}: close_qty={close_qty} inválido. Abortando colheita.")
                                    else:
                                        logger.warning(
                                            f"🌾 [PAPER-HARVEST] {symbol} | "
                                            f"Colhendo {proportion*100:.1f}% ({close_qty:.6f}/{qty:.6f} unidades) "
                                            f"| Fase: {harvest_res.get('phase', 'COLHEITA')}"
                                        )
                                        # [V110.118] close_position com is_partial=True:
                                        # - NÃO chama hard_reset_slot (Moonbag sobrevive)
                                        # - NÃO remove da memória (apenas atualiza size)
                                        # - Registra o trade parcial no histórico
                                        # - Atualiza o Firebase do moonbag
                                        success = await self.close_position(
                                            symbol, pos.get("side"), close_qty,
                                            reason=f"HARVEST_{harvest_res.get('target_level', 'FIBO')}",
                                            is_partial=True
                                        )
                                        
                                        if success:
                                            # [V110.118] NÃO atualizar pos["size"] aqui!
                                            # close_position já fez isso internamente.
                                            # Apenas salvar o estado Paper.
                                            await self._save_paper_state()
                                            logger.info(f"✅ [PAPER-HARVEST] Colheita parcial de {symbol} executada com sucesso.")
                                        else:
                                            logger.error(f"❌ [PAPER-HARVEST] Falha ao executar colheita parcial de {symbol}.")

                                else:
                                    # Full Close
                                    logger.warning(f"🛑 [PAPER EXIT] {symbol} | Reason: {reason}")
                                    if qty > 0:
                                        await self.close_position(symbol, pos.get("side"), qty, reason=reason)
                                    
                                    await self._save_paper_state()
                                    if is_moonbag:
                                        # [V110.128.1] Use saved moon_uuid if available to avoid search failure
                                        target_id = pos.get("moon_uuid")
                                        if not target_id:
                                            moonbags = await firebase_service.get_moonbags()
                                            target_moon = next((m for m in moonbags if m.get("symbol") == symbol), None)
                                            target_id = target_moon["id"] if target_moon else None
                                        
                                        if target_id:
                                            await firebase_service.remove_moonbag(target_id, reason=reason)
                                        else:
                                            logger.warning(f"⚠️ [PAPER-GHOST-WARD] {symbol} (Moonbag) closed but no Firebase ID found to remove.")
                            except Exception as pe: logger.error(f"Error handling paper closure/harvest for {symbol}: {pe}")

                            # [V110.64 FIX] Removido free_slot() duplicado aqui.
                            # close_position() já faz hard_reset_slot() internamente.
                            # O duplo reset causava race conditions e slots "piscando".

                    except Exception as pos_error:
                        logger.error(f"❌ [PAPER POSITION ERROR] {symbol}: {pos_error}")
                        continue

                # UI PNL Pulse (Paper)
                combined_for_pnl = self.paper_positions + self.paper_moonbags
                if combined_for_pnl:
                    # [V110.12.12] Safe ROI Calculation for UI
                    pnl_summary = []
                    for p in combined_for_pnl:
                        p_sym = p.get("symbol")
                        p_price = price_map.get(p_sym, 0)
                        if p_price > 0:
                            entry = float(p.get("avgPrice", 0))
                            if entry > 0:
                                side = p.get("side", "Buy")
                                qty = float(p.get("size", 0))
                                # Em PAPER, calcula a margem dinamicamente baseado em 10% da banca operacional do usuário
                                target_pct = 0.10
                                if p.get("status") == "EMANCIPATED":
                                    # Moonbags mantêm a margem de entrada original
                                    margin = float(p.get("entry_margin") or (self.paper_balance * target_pct))
                                else:
                                    margin = float(p.get("entry_margin") or (self.paper_balance * target_pct))
                                
                                # ROI = (diferença de preço / preço de entrada) * alavancagem * 100
                                leverage = float(p.get("leverage", 50.0))
                                roi = execution_protocol.calculate_roi(entry, p_price, side, leverage=leverage)
                                # PnL USD = (ROI / 100) * Margem real da ordem
                                p_usd = (roi / 100.0) * margin
                                pnl_summary.append({
                                    "symbol": p_sym, 
                                    "roi": roi,
                                    "pnl_usd": round(p_usd, 2)
                                })
                    if pnl_summary:
                        await self.redis.publish_update("ui_updates", {"type": "PNL_PULSE", "data": pnl_summary})
                        # [V110.118 FIX-B] Publicar também no RTDB para que o PWA receba PnL dinâmico
                        if firebase_service.rtdb:

                            try:
                                total_float_roi = sum(p["roi"] for p in pnl_summary)
                                total_float_pnl = sum(p["pnl_usd"] for p in pnl_summary)
                                await asyncio.to_thread(
                                    firebase_service.rtdb.child("live_pnl").update,
                                    {
                                        "slots_roi": {p["symbol"]: round(p["roi"], 1) for p in pnl_summary},
                                        "slots_pnl": {p["symbol"]: round(p["pnl_usd"], 2) for p in pnl_summary},
                                        "total_float_roi": round(total_float_roi, 1),
                                        "total_float_pnl": round(total_float_pnl, 2),
                                        "active_count": len(pnl_summary),
                                        "updated_at": int(time.time() * 1000)
                                    }
                                )
                            except Exception:
                                pass  # Silencioso: não travar o loop por RTDB

            except Exception as e:
                logger.error(f"[PAPER ENGINE] Global Loop error: {e}")

            await asyncio.sleep(1)

    async def _release_emancipation_guard(self, symbol: str, delay: int = 15):
        """Libera a trava de emancipação após um delay de sincronização."""
        await asyncio.sleep(delay)
        self.emancipating_symbols.discard(symbol)

okx_rest_service = OKXRest()

