# -*- coding: utf-8 -*-
import asyncio
from config import settings
import logging
import datetime
from services.resilience import with_circuit_breaker

logger = logging.getLogger("FirebaseService")
logger.setLevel(logging.CRITICAL)  # Silenciando os logs de Firebase conforme solicitado

class DummyFirestore:
    def collection(self, *args, **kwargs):
        class DummyCollection:
            def document(self, *args, **kwargs):
                class DummyDoc:
                    def get(self, *args, **kwargs): return self
                    def set(self, *args, **kwargs): pass
                    def update(self, *args, **kwargs): pass
                    @property
                    def exists(self): return False
                    def to_dict(self): return {}
                return DummyDoc()
            def stream(self): return []
            def where(self, *args, **kwargs): return self
            def order_by(self, *args, **kwargs): return self
            def limit(self, *args, **kwargs): return self
            def add(self, *args, **kwargs): pass
        return DummyCollection()

class DummyRTDB:
    def child(self, *args, **kwargs):
        class DummyChild:
            def get(self, *args, **kwargs): return {}
            def set(self, *args, **kwargs): pass
            def update(self, *args, **kwargs): pass
            def delete(self, *args, **kwargs): pass
            def child(self, *args, **kwargs): return self
        return DummyChild()
# Define Private Key safely as a Python multiline string to avoid string escaping hell
# This is the user provided key
# Initialize Firebase with explicit error handling to strictly enforcing SAFE MODE if key is invalid
# This guarantees the server starts even with broken keys.

from collections import deque
import time

# [V120] Multitenancy Cache
USERS_CACHE = {}
LAST_USERS_SYNC = 0

class FirebaseService:
    def __init__(self):
        self.is_active = False
        self.db = DummyFirestore()
        self.rtdb = DummyRTDB()
        self.log_buffer = deque(maxlen=100)
        self.signal_buffer = deque(maxlen=100)
        self.slots_cache = [{"id": i, "symbol": None, "entry_price": 0, "current_stop": 0, "status_risco": "LIVRE", "pnl_percent": 0} for i in range(1, 5)]
        self.radar_pulse_cache = {"signals": [], "decisions": [], "updated_at": 0}
        self._reconnect_task = None
        self._consecutive_failures = 0
        self._last_successful_op = time.time()
        self._reconnect_attempts = 0
        self._last_state_data = {}

    def _make_json_safe(self, data):
        if isinstance(data, dict):
            clean_dict = {}
            for k, v in data.items():
                if isinstance(k, str):
                    clean_k = k.strip()
                    if not clean_k: clean_k = "empty_key"
                    clean_k = clean_k.replace(".", "_").replace("$", "_").replace("#", "_").replace("[", "_").replace("]", "_").replace("/", "_")
                    clean_dict[clean_k] = self._make_json_safe(v)
                else:
                    safe_k = str(k) if k is not None else "null_key"
                    if not safe_k: safe_k = "empty_key"
                    clean_dict[safe_k] = self._make_json_safe(v)
            return clean_dict
        elif isinstance(data, list):
            return [self._make_json_safe(item) for item in data]
        elif hasattr(data, 'isoformat'):
            return data.isoformat()
        elif hasattr(data, 'to_dict'):
            return self._make_json_safe(data.to_dict())
        elif "DatetimeWithNanoseconds" in str(type(data)):
             return str(data)
        return data

    async def initialize(self):
        logger.warning("❌ Firebase SDK disabled due to hybrid architecture. Routing to Postgres/Redis.")
        self.is_active = False
        return

    async def _reconnection_loop(self):
        pass
        """
        V10.6.5: Enhanced reconnection loop with exponential backoff.
        Starts at 15s, doubles each attempt, max 60s.
        """
        base_delay = 15  # Start with 15s instead of 60s
        max_delay = 60
        
        while not self.is_active:
            self._reconnect_attempts += 1
            delay = min(base_delay * (2 ** (self._reconnect_attempts - 1)), max_delay)
            
            logger.warning(f"🔄 Firebase Reconnection Attempt #{self._reconnect_attempts} (next in {delay}s)...")
            await self.initialize()
            
            if self.is_active:
                logger.info(f"✅ Firebase RECONNECTED after {self._reconnect_attempts} attempts.")
                self._reconnect_attempts = 0
                self._consecutive_failures = 0
                break
            
            await asyncio.sleep(delay)

    async def _flush_buffers(self):
        """Pushes buffered logs and signals to Firebase after a reconnection."""
        if not self.is_active: return
        
        logger.info(f"Flushing buffers to Firebase: {len(self.log_buffer)} logs, {len(self.signal_buffer)} signals.")
        
        # We don't clear the buffer because it's a deque used for UI as well, 
        # but we can try to push items that are 'local' only.
        # For simplicity, we just log that we are online now.
        logger.info("🔥 Firebase Connection Restored. Buffers active.")

    async def _health_check(self):
        """
        V10.6.5: Proactive health check triggered by consecutive failures.
        Tests basic Firebase connectivity and triggers reconnection if needed.
        """
        logger.info("🏥 Running Firebase health check...")
        try:
            # Simple read test with short timeout
            test_result = await asyncio.wait_for(
                asyncio.to_thread(self.db.collection("banca_status").document("status").get),
                timeout=5.0
            )
            if test_result.exists:
                logger.info("✅ Firebase health check passed. Resetting failure counter.")
                self._consecutive_failures = 0
                self._last_successful_op = time.time()
            else:
                raise Exception("Health check returned empty result")
        except Exception as e:
            logger.error(f"❌ Firebase health check FAILED: {e}")
            # Mark as inactive and trigger reconnection
            self.is_active = False
            if not self._reconnect_task or self._reconnect_task.done():
                self._reconnect_task = asyncio.create_task(self._reconnection_loop())

    @with_circuit_breaker(breaker_name="firebase_rest", fallback_return={"saldo_total": 100.0, "risco_real_percent": 10.0, "slots_disponiveis": 4, "status": "ERROR"})
    async def get_banca_status(self, username: str = None):
        """[V120] Busca o status da banca isolado por usuário ou global."""
        if not self.is_active:
            await self.initialize()
            if not self.is_active:
                return {"saldo_total": 100.0, "risco_real_percent": 10.0, "slots_disponiveis": 4, "status": "OFFLINE"}
            
        try:
            if username:
                # [V120] Busca no documento do usuário
                user_doc = await asyncio.wait_for(
                    asyncio.to_thread(self.db.collection("users").document(username).get),
                    timeout=10.0
                )
                if user_doc.exists:
                    data = user_doc.to_dict()
                    return {
                        "saldo_total": float(data.get("bankroll_balance", 100.0)),
                        "risco_real_percent": 0.0,
                        "slots_disponiveis": 4,
                        "status": "USER_MODE"
                    }

            # Fallback Legacy
            doc = await asyncio.wait_for(
                asyncio.to_thread(self.db.collection("banca_status").document("status").get),
                timeout=10.0
            )
            if doc.exists:
                return doc.to_dict()
        except asyncio.TimeoutError:
            self._consecutive_failures += 1
            logger.warning(f"Firebase timeout ao buscar banca status (failures: {self._consecutive_failures}). Using fallback.")
            # V10.6.5: Auto-trigger reconnection check after 5 consecutive failures
            if self._consecutive_failures >= 5:
                logger.error("🚨 5+ consecutive Firebase failures. Triggering health check...")
                asyncio.create_task(self._health_check())
            return {"saldo_total": 100.0, "risco_real_percent": 10.0, "slots_disponiveis": 4, "status": "TIMEOUT"}
        except Exception as e:
            self._consecutive_failures += 1
            logger.error(f"Error fetching banca (failures: {self._consecutive_failures}): {e}")
        return {"saldo_total": 100.0, "risco_real_percent": 10.0, "slots_disponiveis": 4, "status": "ERROR"}

    async def update_bankroll(self, balance: float):
        """[V110.29.0] Updates the bankroll baseline in Firestore and RTDB."""
        if not self.is_active: return
        try:
            data = {
                "configured_balance": balance,
                "saldo_total": balance,
                "timestamp_last_update": time.time()
            }
            await self.update_banca_status(data)
            logger.info(f"✅ [V110.29.0] Bankroll updated to ${balance:.2f}")
        except Exception as e:
            logger.error(f"Error updating bankroll: {e}")

    async def update_banca_status(self, data: dict):
        if not self.is_active: return data
        try:
            # Sync to Firestore
            await asyncio.wait_for(asyncio.to_thread(self.db.collection("banca_status").document("status").set, data, merge=True), timeout=8.0)
            
            # V11.0: Sync to Realtime DB with timeout
            if self.rtdb:
                try:
                    await asyncio.wait_for(asyncio.to_thread(self.rtdb.child("banca_status").set, data), timeout=5.0)
                except asyncio.TimeoutError:
                    logger.warning("RTDB banca update timeout - using cache")
        except Exception as e:
            logger.error(f"Error updating banca status: {e}")
        return data

    async def log_banca_snapshot(self, data: dict):
        """Logs a historical snapshot of the bankroll."""
        if not self.is_active: return
        try:
            snapshot = {
                **data,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
            await asyncio.to_thread(self.db.collection("banca_history").add, snapshot)
        except Exception as e:
            logger.error(f"Error logging banca snapshot: {e}")

    async def get_active_subscribers_with_vault(self):
        """
        [V120] Busca todos os usuários ativos que possuem cofre configurado.
        Usa cache de 30s para não sobrecarregar o Firestore em loops rápidos.
        """
        global USERS_CACHE, LAST_USERS_SYNC
        now = time.time()
        if now - LAST_USERS_SYNC < 30:
            return USERS_CACHE

        if not self.is_active: return {}
        try:
            def _get():
                # Filtra usuários com role 'user' ou 'admin' e que tenham o campo 'bybit_vault'
                # Em produção, você pode adicionar um check de assinatura (subscription_active == True)
                docs = self.db.collection("users").where("role", "in", ["user", "admin"]).stream()
                users = {}
                for doc in docs:
                    d = doc.to_dict()
                    if "bybit_vault" in d:
                        users[doc.id] = d
                return users
            
            USERS_CACHE = await asyncio.to_thread(_get)
            LAST_USERS_SYNC = now
            return USERS_CACHE
        except Exception as e:
            logger.error(f"Erro ao buscar assinantes ativos: {e}")
            return USERS_CACHE

    @with_circuit_breaker(breaker_name="firebase_rest", fallback_return=None)
    async def log_trade(self, trade_data: dict):
        """
        Logs a completed trade to history.
        [V110.112] BULLETPROOFING: Uses SERVER_TIMESTAMP and local backup.
        """
        symbol = trade_data.get('symbol', 'UNKNOWN')
        order_id = trade_data.get('order_id')
        pnl = float(trade_data.get('pnl', 0))

        # 0. [V110.999] SEMPRE PERSISTIR NO POSTGRESQL (Railway SSOT) INDEPENDENTE DO FIREBASE
        try:
            from services.database_service import database_service
            pg_data = trade_data.copy()
            if "timestamp" in pg_data and isinstance(pg_data["timestamp"], str):
                try:
                    pg_data["timestamp"] = datetime.datetime.fromisoformat(pg_data["timestamp"].replace("Z", "+00:00"))
                except:
                    pg_data["timestamp"] = datetime.datetime.utcnow()
            elif "timestamp" not in pg_data:
                pg_data["timestamp"] = datetime.datetime.utcnow()
            
            await database_service.log_trade(pg_data)
            logger.info(f"✅ [POSTGRES-HISTORY] {symbol} logged in relational database.")
        except Exception as pg_err:
            logger.error(f"❌ [POSTGRES-HISTORY-ERROR] Failed to save in Postgres: {pg_err}")

        # 1. [V110.114] Block ghost cleanups but allow real breakeven trades
        close_reason = trade_data.get("close_reason", "")
        _GHOST_TAGS = ["GHOST", "PURGE", "CLEANUP", "SYNC"]
        is_ghost = any(tag in close_reason.upper() for tag in _GHOST_TAGS)
        if abs(pnl) < 0.0001 and (is_ghost or not close_reason):
            logger.info(f"🛡️ [VAULT-FILTER] Blocked ghost/zero PnL for {symbol}. Reason: {close_reason or 'N/A'}")
            return

        # 2. Local Backup (Emergency Safety Net)
        try:
            backup_file = "trade_history_backup.json"
            backup_entry = {**trade_data, "logged_at": datetime.datetime.now().isoformat()}
            
            import json, os
            mode = 'a' if os.path.exists(backup_file) else 'w'
            with open(backup_file, mode) as f:
                f.write(json.dumps(backup_entry) + "\n")
        except Exception as be:
            logger.warning(f"⚠️ [BACKUP-FAIL] Could not write local trade backup: {be}")

        if not self.is_active: return

        try:
            # 3. Firestore Logging
            def _log():
                final_data = trade_data.copy()
                
                # [V110.112] CRITICAL: Use server timestamp for UI compatibility
                final_data["timestamp"] = firestore.SERVER_TIMESTAMP
                
                if order_id:
                    # Genesis Merge logic
                    try:
                        genesis_doc = self.db.collection("orders_genesis").document(str(order_id)).get()
                        if genesis_doc.exists:
                            genesis_data = genesis_doc.to_dict()
                            tactical_fields = [
                                "fleet_intel", "unified_confidence", "pensamento", 
                                "score", "pattern", "initial_stop", "strategy", 
                                "librarian_dna", "oracle_state", "sentinel_retests"
                            ]
                            for field in tactical_fields:
                                if field in genesis_data and field not in final_data:
                                    final_data[field] = genesis_data[field]
                    except Exception as ge:
                        logger.warning(f"⚠️ [GENESIS-FAIL] {order_id}: {ge}")

                    # History Protection Guard (Block zero PnL over real PnL)
                    doc_ref = self.db.collection("trade_history").document(str(order_id))
                    existing = doc_ref.get()
                    if existing.exists:
                        old_pnl = float(existing.to_dict().get("pnl", 0))
                        if abs(old_pnl) > 0.0001 and abs(pnl) < 0.0001:
                            logger.info(f"🛡️ [HISTORY-GUARD] {symbol} Blocked zero PnL override.")
                            update_data = {k: v for k, v in final_data.items() if k != "pnl"}
                            doc_ref.set(update_data, merge=True)
                            return

                    doc_ref.set(final_data, merge=True)
                else:
                    self.db.collection("trade_history").add(final_data)
            
            await asyncio.to_thread(_log)
            logger.info(f"✅ [HISTORY-SUCCESS] {symbol} logged. OrderID: {order_id}")
        except Exception as e:
            logger.error(f"❌ [LOG-CRITICAL] Failure logging {symbol}: {e}")

    async def register_order_genesis(self, order_data: dict):
        """
        [V110.61] Cria uma Certidão de Nascimento imutável para a ordem.
        Garante que score de agentes e metadados táticos sobrevivam a qualquer purga.
        """
        if not self.is_active: return
        try:
            # Deterministic ID based on symbol and opening timestamp
            symbol = order_data.get("symbol", "UNKNOWN")
            opened_at = int(order_data.get("opened_at") or time.time())
            order_id = order_data.get("order_id") or f"{symbol.replace('.P','')}_{opened_at}"
            
            order_data["order_id"] = order_id
            order_data["genesis_at"] = time.time()
            safe_data = self._make_json_safe(order_data)
            
            await asyncio.to_thread(self.db.collection("orders_genesis").document(str(order_id)).set, safe_data)
            logger.info(f"🧬 [GENESIS] Order registered: {order_id} ({symbol})")
            return order_id
        except Exception as e:
            logger.error(f"Error registering order genesis: {e}")

    async def get_order_genesis(self, order_id: str):
        """[V110.61] Recupera metadados táticos da ordem da coleção imutável."""
        if not self.is_active: return None
        try:
            doc = await asyncio.to_thread(self.db.collection("orders_genesis").document(str(order_id)).get)
            if doc.exists:
                return doc.to_dict()
        except Exception as e:
            logger.error(f"Error fetching order genesis {order_id}: {e}")
        return None

    def _parse_ts_for_query(self, ts_str, end_of_day: bool = False):
        """
        [V110.114] Convert timestamp strings to datetime for Firestore queries.
        Firestore timestamp fields (SERVER_TIMESTAMP) are stored as datetime objects,
        so query filters and pagination cursors must also use datetime.
        """
        if not ts_str:
            return None
        # ISO format (from isoformat() serialization)
        try:
            dt_val = datetime.datetime.fromisoformat(str(ts_str).replace('Z', '+00:00'))
            if end_of_day and dt_val.hour == 0 and dt_val.minute == 0 and dt_val.second == 0:
                dt_val = dt_val + datetime.timedelta(days=1)
            return dt_val
        except (ValueError, AttributeError):
            pass
        # Date-only format (YYYY-MM-DD from UI date picker)
        try:
            dt_val = datetime.datetime.strptime(str(ts_str), "%Y-%m-%d")
            if end_of_day:
                dt_val = dt_val + datetime.timedelta(days=1)
            return dt_val
        except (ValueError, AttributeError):
            pass
        # Unix timestamp (float/int)
        try:
            ts_float = float(ts_str)
            return datetime.datetime.fromtimestamp(ts_float)
        except (ValueError, TypeError):
            pass
        return ts_str  # fallback to original value

    async def get_trade_history(self, limit: int = 50, last_timestamp: str = None, symbol: str = None, start_date: str = None, end_date: str = None):
        """
        Fetches completed trade history with pagination and filtering support.
        [V15.1] Added memory fallback for missing composite indexes.
        """
        if not self.is_active:
            try:
                from services.database_service import database_service
                trades = await database_service.get_trade_history(limit=limit)
                for t in trades:
                    if t.get("timestamp") and hasattr(t["timestamp"], "isoformat"):
                        t["timestamp"] = t["timestamp"].isoformat()
                    if t.get("data") and isinstance(t["data"], dict):
                        for k, v in t["data"].items():
                            if k not in t:
                                t[k] = v
                return trades
            except Exception as e:
                logger.error(f"Error getting trade history from Postgres fallback: {e}")
                return []
        try:
            def _get_trades():
                query = self.db.collection("trade_history")
                
                # Try Direct Firebase Query First
                try:
                    if symbol:
                        query = query.where("symbol", "==", symbol.upper())
                    if start_date:
                        query = query.where("timestamp", ">=", self._parse_ts_for_query(start_date))
                    if end_date:
                        query = query.where("timestamp", "<=", self._parse_ts_for_query(end_date, end_of_day=True))
                    
                    # Ordering (This often requires index if combined with where)
                    query = query.order_by("timestamp", direction=firestore.Query.DESCENDING).limit(limit)
                    
                    if last_timestamp:
                        cursor_ts = self._parse_ts_for_query(last_timestamp)
                        query = query.start_after({"timestamp": cursor_ts})
                    
                    docs = query.stream()
                    results = []
                    for doc in docs:
                        d = doc.to_dict()
                        # Normaliza timestamps para serialização JSON
                        for k, v in d.items():
                            if hasattr(v, 'isoformat'):
                                d[k] = v.isoformat()
                        results.append({**d, "id": doc.id})
                    return results
                except Exception as query_error:
                    # Fallback: Filter in memory if index is missing
                    if "index" in str(query_error).lower():
                        logger.warning(f"Index missing for history query. Falling back to memory filter. Link: {query_error}")
                        # Fetch last 300 trades and filter (limit fallback to avoid huge memory/cost)
                        fallback_query = self.db.collection("trade_history").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(300)
                        all_docs = fallback_query.stream()
                        results = []
                        for doc in all_docs:
                            d = doc.to_dict()
                            # Normaliza timestamps para serialização JSON
                            for k, v in d.items():
                                if hasattr(v, 'isoformat'):
                                    d[k] = v.isoformat()
                            item = {**d, "id": doc.id}
                            # Manual Filter
                            if symbol and d.get("symbol") != symbol.upper(): continue
                            if start_date and str(d.get("timestamp")) < start_date: continue
                            if end_date and str(d.get("timestamp")) > end_date: continue
                            results.append(item)
                        
                        return results[:limit]
                    raise query_error
            
            return await asyncio.wait_for(asyncio.to_thread(_get_trades), timeout=15.0)
        except Exception as e:
            logger.error(f"Error fetching trade history: {e}")
            return []

    async def get_vault_history(self, limit: int = 50):
        """Alias para get_trade_history usado pelo Librarian Profile Engine."""
        return await self.get_trade_history(limit=limit)

    async def get_trade_history_stats(self, symbol: str = None, start_date: str = None, end_date: str = None):
        """
        [V15.1] Memory-efficient stats.
        """
        if not self.is_active:
            try:
                from services.database_service import database_service
                trades = await database_service.get_trade_history(limit=1000)
                total_pnl = 0.0
                count = 0
                for t in trades:
                    if symbol and t.get("symbol") != symbol.upper(): continue
                    total_pnl += float(t.get("pnl", 0))
                    count += 1
                return {"total_count": count, "total_pnl": round(total_pnl, 2)}
            except Exception as e:
                logger.error(f"Error calculating stats from Postgres fallback: {e}")
                return {"total_count": 0, "total_pnl": 0.0}
        try:
            def _get_stats():
                query = self.db.collection("trade_history")
                # For stats, we don't necessarily need ordering, so we might avoid index errors
                if symbol:
                    query = query.where("symbol", "==", symbol.upper())
                if start_date:
                    query = query.where("timestamp", ">=", start_date)
                if end_date:
                    query = query.where("timestamp", "<=", end_date)
                
                # If no filters, we can just use the provided stats if available or count small collection
                docs = query.stream()
                total_pnl = 0.0
                count = 0
                for doc in docs:
                    d = doc.to_dict()
                    total_pnl += float(d.get("pnl", 0))
                    count += 1
                return {"total_count": count, "total_pnl": round(total_pnl, 2)}
            
            return await asyncio.wait_for(asyncio.to_thread(_get_stats), timeout=15.0)
        except Exception as e:
            logger.error(f"Error fetching trade history stats: {e}")
            return {"total_count": 0, "total_pnl": 0.0}
        except asyncio.TimeoutError:
            logger.warning("Timeout fetching trade history from Firebase. It might be empty or unreachable.")
            return []
        except Exception as e:
            logger.error(f"Error fetching trade history: {e}")
            return []

    async def get_active_slots(self, username: str = None, force_refresh: bool = False):
        """[V120 OVERRIDE] Busca os slots ativos EXCLUSIVAMENTE do Postgres (Não usa mais Firebase para dados)."""
        try:
            from services.database_service import database_service
            slots = await database_service.get_active_slots()
            full_slots = []
            for i in range(1, 5):
                existing = next((s for s in slots if s.get("id") == i), None)
                if existing: full_slots.append(existing)
                else: full_slots.append({"id": i, "symbol": None, "entry_price": 0, "current_stop": 0, "status_risco": "LIVRE", "pnl_percent": 0})
            self.slots_cache = full_slots
            return self.slots_cache
        except Exception as e:
            logger.error(f"Error reading Postgres slots from Firebase proxy: {e}")
            return self.slots_cache

    def _clean_mojibake(self, data: any) -> any:
        """
        V15.7.8: Recursively cleans mojibake patterns from data before sending to RTDB.
        """
        if isinstance(data, str):
            # Known corrupted patterns to fix
            replacements = {
                "ðŸ›¡ï¸": "\U0001f6e1\ufe0f", # 🛡️
                "ðŸ”\ufe0f": "\U0001f534",     # 🔴
                "âœ…": "\u2705",              # ✅
                "âœ—": "\u274c",              # ❌
                "ðŸ”’": "\U0001f512",         # 🔒
                "ðŸ”®": "\U0001f52e"          # 🔮
            }
            for old, new in replacements.items():
                data = data.replace(old, new)
            return data
        elif isinstance(data, dict):
            return {k: self._clean_mojibake(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._clean_mojibake(item) for item in data]
        return data

    async def update_slot(self, slot_id: int, data: dict, username: str = None):
        """[V120] Atualiza o estado de um slot no Firestore e RTDB com isolamento multitenant."""
        try:
            from services.database_service import database_service
            await database_service.update_slot(slot_id, data)
        except Exception as e:
            logger.error(f"Error updating Postgres slot from Firebase proxy: {e}")
        
        if not self.is_active: 
            return data
        
        try:
            # 1. Firestore Path
            if username:
                ref = self.db.collection("users").document(username).collection("slots").document(str(slot_id))
            else:
                ref = self.db.collection("slots_ativos").document(str(slot_id))
                
            await asyncio.to_thread(ref.set, data, merge=True)
            
            # 2. RTDB Sync
            if self.rtdb:
                rtdb_data = self._clean_mojibake(data)
                # Camino multitenant no RTDB: users/{username}/live_slots/{slot_id}
                path = f"users/{username}/live_slots" if username else "live_slots"
                try:
                    await asyncio.wait_for(asyncio.to_thread(self.rtdb.child(path).child(str(slot_id)).update, rtdb_data), timeout=8.0)
                except asyncio.TimeoutError:
                    logger.warning(f"RTDB slot {slot_id} update timeout for {username}")
        except Exception as e:
            logger.error(f"Error updating slot {slot_id} for {username}: {e}")
        return data

    async def free_slot(self, slot_id: int, reason: str = "Promoted to Moonbag", username: str = None):
        """[V120] Reseta um slot tático para o estado LIVRE no contexto multitenant."""
        reset_data = {
            "symbol": None,
            "side": None,
            "qty": 0,
            "entry_margin": 0,
            "opened_at": None,
            "fleet_intel": {},
            "unified_confidence": 50,
            "entry_price": 0,
            "initial_stop": 0,
            "current_stop": 0,
            "target_price": 0,
            "status_risco": "LIVRE",
            "pnl_percent": 0,
            "slot_type": None,
            "pattern": None,
            "pensamento": f"🔄 {reason}",
            "maestria_guard_active": False,
            "rescue_activated": False,
            "rescue_resolved": False,
            "sentinel_retests": 0,
            "partial_tp_hit": False,
            "sentinel_first_hit_at": 0,
            "timestamp_last_update": time.time()
        }
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await self.update_slot(slot_id, reset_data, username=username)
                return True
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"Failed to free slot {slot_id} after {max_retries} attempts: {e}")
                    return False
                await asyncio.sleep(1)

    async def hard_reset_slot(self, slot_id: int, reason: str = "Tolerancia Zero", pnl: float = 0, trade_data: dict = None, username: str = None):
        """[V120] Força um reset absoluto do slot com registro de histórico completo e concorrência robusta."""
        try:
            # [V121 INTEGRATION] Delega para a função completa com auto-cálculo e auditoria rica
            success = await self._hard_reset_slot_full(slot_id, reason=reason, pnl=pnl, trade_data=trade_data)
            return success if success is not None else True
        except Exception as e:
            logger.error(f"❌ [HARD-RESET] Falha no hard_reset_slot integrado: {e}")
            # Fallback seguro para esvaziar o slot mesmo com erro de persistência
            return await self.free_slot(slot_id, reason, username=username)
        
    async def promote_to_moonbag(self, slot_id: int):
        """[V110.0] Promove um trade tático para o status de Moonbag (Emancipado)."""
        if not self.is_active: 
            try:
                from services.database_service import database_service
                return await database_service.promote_to_moonbag(slot_id)
            except Exception as e:
                logger.error(f"Error promoting Moonbag in Postgres: {e}")
                return False
        try:
            # 1. Busca os dados atuais do slot
            slots = await self.get_active_slots(force_refresh=True)
            slot_data = next((s for s in slots if s.get("id") == slot_id), None)
            
            if not slot_data or not slot_data.get("symbol"):
                logger.warning(f"⚠️ [EMANCIPATE] Tentativa de emancipar slot {slot_id} vazio ou inválido.")
                return

            # [V110.125] DATA INTEGRITY GUARD: Bloqueia promoção se o preço de entrada for inválido
            entry_p = float(slot_data.get("entry_price", 0))
            if entry_p <= 0:
                logger.error(f"❌ [EMANCIPATE-FAIL] {slot_data.get('symbol')} possui entry_price {entry_p}. Promoção bloqueada para evitar PnL irreal.")
                # Opcional: Tenta recuperar o preço atual via API como fallback se for um erro de cache
                return

            # 2. Prepara os dados para a nova coleção
            moonbag_data = {
                **slot_data,
                "status": "EMANCIPATED",
                "promoted_at": time.time(),
                "original_slot": slot_id,
                "timestamp_last_update": time.time()
            }
            
            # [V110.4] ID Determinístico: Evita duplicação por race condition
            # Se a trade já tem um timestamp de abertura, usamos como chave única
            open_ts = int(slot_data.get("opened_at") or slot_data.get("created_at") or time.time())
            moon_uuid = f"{slot_data['symbol'].replace('.P','')}_{open_ts}"
            
            # 3. Verificação de Duplicata (Trava Atômica)
            # Se já existe no Vault com o mesmo UUID, apenas retorna o ID existente
            # para evitar que vários loops criem clones.
            existing_vault = await self.get_moonbags()
            if any(m.get("id") == moon_uuid for m in existing_vault):
                logger.warning(f"🛡️ [V110.4] {slot_data['symbol']} já existe no Vault. Ignorando promoção duplicada.")
                # Mesmo assim garantimos que o slot seja limpo
                await self.free_slot(slot_id, reason=f"Vincular_Moonbag_Existente: {slot_data['symbol']}")
                return moon_uuid

            # 4. Salva na coleção moonbags (Firestore)
            await asyncio.to_thread(self.db.collection("moonbags").document(moon_uuid).set, moonbag_data)
            
            # 5. Sincroniza com RTDB para a UI (seção dedicada)
            if self.rtdb:
                logger.info(f"📤 [RTDB] Sincronizando Moonbag Vault: {moon_uuid}")
                await asyncio.to_thread(self.rtdb.child("moonbag_vault").child(moon_uuid).set, self._clean_mojibake(moonbag_data))
            
            # 6. Libera o slot original tático
            await self.free_slot(slot_id, reason=f"Emancipado: {slot_data['symbol']}")
            
            logger.info(f"🚀 [V110.4] {slot_data['symbol']} EMANCIPADO! Movido para o Vault. Slot {slot_id} LIVRE.")
            return moon_uuid

        except Exception as e:
            logger.error(f"Error promoting slot {slot_id} to moonbag: {e}")
            return None

    async def update_moonbag(self, moon_uuid: str, data: dict):
        """[V110.0] Atualiza os dados de uma ordem no Vault (Ex: Trailling Stop)."""
        if not self.is_active: return
        try:
            data["timestamp_last_update"] = time.time()
            # Firestore
            await asyncio.to_thread(self.db.collection("moonbags").document(moon_uuid).update, data)
            # RTDB
            if self.rtdb:
                await asyncio.to_thread(self.rtdb.child("moonbag_vault").child(moon_uuid).update, self._clean_mojibake(data))
        except Exception as e:
            logger.error(f"Error updating moonbag {moon_uuid}: {e}")

    async def remove_moonbag(self, moon_uuid: str, reason: str = "Closed"):
        """[V110.0] Remove uma ordem do Vault após fechamento."""
        if not self.is_active: return
        try:
            # Firestore
            await asyncio.to_thread(self.db.collection("moonbags").document(moon_uuid).delete)
            # RTDB
            if self.rtdb:
                await asyncio.to_thread(self.rtdb.child("moonbag_vault").child(moon_uuid).delete)
            logger.info(f"🌔 [V110.0] Moonbag {moon_uuid} removida do Vault: {reason}")
        except Exception as e:
            logger.error(f"Error removing moonbag {moon_uuid}: {e}")

    async def get_moonbags(self, limit: int = 50):
        """[V110.0] Busca moonbags ativas."""
        if not self.is_active: 
            try:
                from services.database_service import database_service
                return await database_service.get_moonbags()
            except Exception as e:
                logger.error(f"Error getting Moonbags from Postgres: {e}")
                return []
        try:
            # V110.0: Busca todas para o loop de execução monitorar
            docs = await asyncio.to_thread(self.db.collection("moonbags").get)
            moonbags = []
            for doc in docs:
                m = doc.to_dict()
                m['id'] = doc.id  # O UUID gerado no promote
                moonbags.append(m)
            return moonbags
        except Exception as e:
            logger.error(f"Error fetching moonbags: {e}")
            return []

    async def get_all_moonbags(self):
        """[V110.28.5] Alias for get_moonbags to support auto-adoption in BybitREST."""
        return await self.get_moonbags()

    async def log_signal(self, signal_data: dict):
        # 1. Add to local buffer immediately
        signal_data["id"] = f"loc_{int(time.time() * 1000)}"
        signal_data["timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.signal_buffer.appendleft(signal_data)
        
        if not self.is_active: return signal_data["id"]
        
        # Retry logic for critical signal logging
        for attempt in range(3):
            try:
                # Wrap blocking call
                await asyncio.wait_for(asyncio.to_thread(self.db.collection("journey_signals").add, signal_data), timeout=5.0)
                return signal_data["id"] # Success
            except (asyncio.TimeoutError, Exception) as e: 
                if attempt < 2:
                    wait_time = (attempt + 1) * 2
                    logger.warning(f"Retry {attempt+1}/3: Firebase log_signal failed ({type(e).__name__}). Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"FATAL: log_signal failed after 3 attempts: {e}")
        
        return signal_data["id"] # Return ID anyway as it's in the local buffer

    async def get_recent_signals(self, limit: int = 100):
        # Always return local buffer first for speed and quota saving
        local_data = list(self.signal_buffer)[:limit]
        if not self.is_active or len(local_data) >= 5:
             return local_data
             
        try:
            def _get_signals():
                docs = self.db.collection("journey_signals").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(limit).stream()
                return [{**doc.to_dict(), "id": doc.id} for doc in docs]
            
            remote = await asyncio.wait_for(asyncio.to_thread(_get_signals), timeout=5.0)
            return remote or local_data
        except Exception: return local_data

    async def log_event(self, agent: str, message: str, level: str = "INFO"):

        data = {
            "agent": agent,
            "message": message,
            "level": level,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        self.log_buffer.appendleft(data)
        
        if not self.is_active: return data
        try:
            await asyncio.to_thread(self.db.collection("system_logs").add, data)
        except Exception: pass
        return data

    async def get_recent_logs(self, limit: int = 50):
        local_data = list(self.log_buffer)[:limit]
        if not self.is_active or len(local_data) >= 5:
            return local_data or [{"agent": "System", "message": "Neural Interface Online. Waiting for logs...", "level": "INFO", "timestamp": "Now"}]
            
        try:
            def _get_logs():
                docs = self.db.collection("system_logs").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(limit).stream()
                return [doc.to_dict() for doc in docs]
            remote = await asyncio.to_thread(_get_logs)
            return remote or local_data
        except Exception: return local_data


    async def update_signal_outcome(self, signal_id: str, outcome: any, extra_fields: dict = None):
        update_data = {"outcome": outcome}
        if extra_fields:
            update_data.update(extra_fields)
            
        for sig in self.signal_buffer:
            if sig.get("id") == signal_id:
                sig.update(update_data)
                break

        if not self.is_active: return
        try:
            await asyncio.to_thread(self.db.collection("journey_signals").document(signal_id).update, update_data)
        except Exception: pass

    async def update_pulse(self):
        """Sends a heartbeat to Realtime DB for the Pulse Monitor."""
        if not self.is_active or not self.rtdb: return
        try:
            # RTDB is great for this as it has extremely low latency
            data = self._clean_mojibake(self._make_json_safe({
                "timestamp": time.time() * 1000,
                "status": "ONLINE",
                "last_heartbeat": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }))
            # V15.7.5: Reduced timeout to 5s for faster recovery from RTDB hangs
            await asyncio.wait_for(asyncio.to_thread(self.rtdb.update, {"system_pulse": data}), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("⚠️ Heartbeat RTDB Timeout (5s)")
        except Exception as e:
            logger.warning(f"Heartbeat failed: {type(e).__name__} ({str(e)}). This is usually transient but may trigger LAG in UI.")

    async def update_pulse_drag(self, btc_drag_mode: bool, btc_cvd: float, exhaustion: float, 
                                 btc_price: float = 0, btc_var_1h: float = 0,
                                 btc_adx: float = 0, decorrelation_avg: float = 0, btc_var_24h: float = 0,
                                 btc_dominance: float = 0, btc_var_15m: float = 0,
                                 btc_direction: str = 'LATERAL',
                                 oracle_context: dict = None):

        """V12.1: Updates BTC Command Center in RTDB with price, variation and intelligence metrics."""
        if not self.is_active or not self.rtdb: return
        try:
            payload = {
                "btc_drag_mode": btc_drag_mode,
                "btc_cvd": btc_cvd,
                "exhaustion": exhaustion,
                "btc_price": btc_price,           # V12.1: Real-time BTC price
                "btc_variation_1h": btc_var_1h,   # V12.1: 1h variation %
                "btc_variation_24h": btc_var_24h, # V110.30.2: 24h variation %
                "btc_adx": btc_adx,               # [V20.1] Market ADX Telemetry
                "decorrelation_avg": decorrelation_avg, # [V20.1] Market Correlation Telemetry
                "btc_dominance": btc_dominance,   # [V110.33] BTC Dominance from CoinGecko
                "btc_var_15m": btc_var_15m,       # [V110.34] 15m variation for regime alignment
                "btc_direction": btc_direction,   # [V110.34] Captain-aligned direction (UP/DOWN/LATERAL)
                "timestamp": time.time() * 1000
            }

            # 🆕 [V110.32.1] Inject Oracle Context into Market Context for UI
            if oracle_context:
                payload["oracle_status"] = oracle_context.get("status", "SECURE")
                payload["oracle_message"] = oracle_context.get("status", "SECURE") # Compatibility
                # Progress calculation: 150s base
                uptime = time.time() - oracle_context.get("boot_time", time.time())
                progress = min(1.0, uptime / 150.0) if payload["oracle_status"] == "STABILIZING" else 1.0
                payload["stabilization_progress"] = progress

            data = self._clean_mojibake(self._make_json_safe(payload))

            # V5.2.4.3: Added 3s timeout for RTDB updates
            await asyncio.wait_for(asyncio.to_thread(self.rtdb.update, {"btc_command_center": data}), timeout=3.0)
            logger.info(f"✅ [RTDB-BTC] Update SUCCESS: ${btc_price:,.0f} | Oracle: {payload.get('oracle_status')} | ADX: {btc_adx:.1f}")
        except asyncio.TimeoutError:
            logger.warning("\u26a0\ufe0f RTDB BTC Update Timeout (3s)")
        except Exception as e:
            logger.error(f"\u274c RTDB BTC Update Failed: {str(e)}")

    async def update_vault_pulse(self, data: dict):
        """V15.0: Syncs vault status to RTDB for real-time dashboard updates."""
        if not self.is_active or not self.rtdb: return
        try:
            data["updated_at"] = int(time.time() * 1000)
            safe_data = self._clean_mojibake(self._make_json_safe(data))
            await asyncio.to_thread(self.rtdb.child("vault_status").set, safe_data)
        except Exception as e:
            logger.error(f"Error updating vault pulse: {e}")

    async def get_radar_pulse(self):
        """[V15.1.4] Fetches radar pulse from cache or RTDB."""
        if not self.is_active or not self.rtdb:
            if not self.radar_pulse_cache.get("signals"):
                try:
                    from services.database_service import database_service
                    db_pulse = await database_service.get_radar_pulse()
                    if db_pulse:
                        self.radar_pulse_cache = db_pulse
                except Exception as e:
                    logger.error(f"Error loading radar pulse fallback from Postgres: {e}")
            return self.radar_pulse_cache
            
        # Debounce to save quota
        if self.radar_pulse_cache.get("updated_at", 0) > (time.time() * 1000 - 5000):
            return self.radar_pulse_cache
            
        try:
            snapshot = await asyncio.to_thread(self.rtdb.child("radar_pulse").get)
            if snapshot:
                self.radar_pulse_cache = snapshot
        except Exception as e:
            logger.error(f"Error fetching radar pulse from RTDB: {e}")
            
        return self.radar_pulse_cache

    async def update_radar_pulse(self, signals: list, decisions: list = None, market_context: dict = None):
        """V15.0: Syncs radar signals and AI decisions to RTDB."""
        # V15.1.4: Update cache regardless of active status
        data = self._clean_mojibake(self._make_json_safe({
            "signals": signals[:20] if signals else [], # Limit to last 20
            "decisions": decisions or [],
            "market_context": market_context or {},
            "updated_at": int(time.time() * 1000)
        }))
        self.radar_pulse_cache = data
        
        try:
            from services.websocket_service import websocket_service
            asyncio.create_task(websocket_service.update_radar_pulse(
                data.get("signals", []), data.get("decisions", []), data.get("market_context", {})
            ))
        except Exception as e:
            logger.error(f"Error emitting radar to WS proxy: {e}")
            
        if not self.is_active or not self.rtdb:
            try:
                from services.database_service import database_service
                asyncio.create_task(database_service.update_radar_pulse(data))
            except Exception as e:
                logger.error(f"Error persisting radar pulse to Postgres: {e}")
            return
        try:
            # V15.7.5: Added timeout to prevent radar loop from freezing if RTDB hangs
            await asyncio.wait_for(asyncio.to_thread(self.rtdb.child("radar_pulse").set, data), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning("⚠️ RTDB Radar Pulse Update Timeout (10s)")
        except Exception as e:
            logger.error(f"Error updating radar pulse: {e}")

    async def update_system_state(self, state: str, slots_occupied: int = 0, message: str = "", protocol: str = "Sniper V15.1", last_reconciliation: float = 0):
        """
        V10.6: Updates system state in RTDB for frontend synchronization.
        state: SCANNING | MONITORING | PAUSED
        """
        if not self.is_active or not self.rtdb: return
        try:
            def _update_sync():
                data = self._clean_mojibake(self._make_json_safe({
                    "current": state,
                    "slots_occupied": slots_occupied,
                    "message": message,
                    "protocol": protocol,
                    "last_reconciliation": last_reconciliation * 1000 if last_reconciliation > 0 else 0,
                    "updated_at": int(time.time() * 1000)
                }))
                self.rtdb.child("system_state").set(data)
            # V15.7.5: Added timeout to prevent state updates from freezing the system
            await asyncio.wait_for(asyncio.to_thread(_update_sync), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning("⚠️ RTDB System State Update Timeout (10s)")
        except Exception as e:
            logger.error(f"Error updating system state: {e}")

    async def get_system_state(self):
        """V10.6: Fetches the current system state from RTDB as a fallback."""
        if not self.is_active or not self.rtdb:
            return {"current": "PAUSED", "message": "Firebase Offline", "slots_occupied": 0}
        try:
            state = await asyncio.to_thread(self.rtdb.child("system_state").get)
            return state or {"current": "PAUSED", "message": "Sem Dados", "slots_occupied": 0}
        except Exception as e:
            logger.error(f"Error fetching system state: {e}")
            return {"current": "PAUSED", "message": "Erro Firebase", "slots_occupied": 0}

    async def update_ws_health(self, latency: float, status: str = "ONLINE"):
        """🆕 V6.0: Updates WebSocket Health (Command Tower) in RTDB."""
        if not self.is_active or not self.rtdb: return
        try:
            data = {
                "latency_ms": latency,
                "status": status,
                "timestamp": time.time() * 1000  # V12.2: Consistent with JS milliseconds
            }
            await asyncio.wait_for(asyncio.to_thread(self.rtdb.update, {"ws_command_tower": data}), timeout=2.0)
        except Exception: pass

    async def update_rtdb_slots(self, slots: list):
        """Duplicate slot data to RTDB for high-speed UI refreshes."""
        if not self.is_active or not self.rtdb: return
        try:
            # Convert list to dict for RTDB
            slots_data = {str(s["id"]): s for s in slots}
            # V11.0: Increased timeout for Cloud Run compatibility
            await asyncio.wait_for(asyncio.to_thread(self.rtdb.child("live_slots").update, slots_data), timeout=5.0)
        except Exception: pass

    async def update_radar_batch(self, batch_data: dict):
        """Updates multiple symbols in RTDB in a single operation."""
        if not self.is_active or not self.rtdb: return
        try:
            # Note: In RTDB, update/set at the root or a subpath is efficient.
            # V15.0: Increased timeout to 10s for production batches
            await asyncio.wait_for(asyncio.to_thread(self.rtdb.child("market_radar").update, batch_data), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning("⚠️ RTDB Radar Batch Update Timeout (10s)")
        except Exception as e:
            logger.error(f"Error updating radar batch: {type(e).__name__} - {str(e)}")

    # --- Operação Oráculo: Chat Memory ---
    async def get_chat_history(self, limit: int = 15):
        """Fetches the recent interactive chat messages from RTDB."""
        if not self.is_active or not self.rtdb: return []
        try:
            def _get_chat_history_sync():
                # Correct way: use .child() on the root reference
                ref = self.rtdb.child("chat_history")
                snapshot = ref.order_by_key().limit_to_last(limit).get()
                if not snapshot: return []
                # RTDB returns a dict, sort by key (timestamp) and return list
                history = [v for k, v in sorted(snapshot.items())]
                return history
            return await asyncio.to_thread(_get_chat_history_sync)
        except Exception as e:
            logger.error(f"Error fetching chat history: {e}")
            return []

    async def add_chat_message(self, role: str, message: str):
        """Adds a message to the chat history in RTDB."""
        if not self.is_active or not self.rtdb: return
        try:
            def _add_chat_message_sync():
                ref = self.rtdb.child("chat_history")
                timestamp = int(time.time() * 1000)
                ref.child(str(timestamp)).set({
                    "role": role,
                    "text": message, # Using 'text' to match standard naming if needed, or 'message'
                    "timestamp": timestamp
                })
                # Cleanup: Keep only last 20 messages to avoid bloat
                snapshot = ref.get()
                if snapshot and len(snapshot) > 20:
                    keys = sorted(snapshot.keys())
                    # Delete everything except the last 20
                    for k in keys[:-20]:
                        ref.child(k).delete()
            await asyncio.to_thread(_add_chat_message_sync)
        except Exception as e:
            logger.error(f"Error adding chat message: {e}")

    async def set_thinking_state(self, is_thinking: bool):
        """V18.0: Updates the Captain's thinking state in RTDB for real-time UI display."""
        if not self.is_active or not self.rtdb: return
        try:
            def _set_thinking_sync():
                self.rtdb.child("chat_status").update({
                    "is_thinking": is_thinking,
                    "updated_at": int(time.time() * 1000)
                })
            await asyncio.to_thread(_set_thinking_sync)
        except Exception as e:
            logger.error(f"Error setting thinking state: {e}")

    async def clear_chat_history(self):
        """Removes all chat messages from RTDB."""
        if not self.is_active or not self.rtdb: return
        try:
            await asyncio.to_thread(self.rtdb.child("chat_history").delete)
            # Log the reset event
            await self.log_event("System", "Chat History Reset by Commander", "INFO")
        except Exception as e:
            logger.error(f"Error clearing chat history: {e}")

    async def get_slot(self, slot_id: int) -> dict:
        """Fetch a specific slot state from Firestore or Postgres fallback."""
        if not self.is_active:
            try:
                from services.database_service import database_service
                return await database_service.get_slot(slot_id)
            except Exception as e:
                logger.error(f"Error fetching Postgres slot from Firebase proxy: {e}")
                return None
        try:
            doc_ref = self.db.collection("slots_ativos").document(str(slot_id))
            doc = await asyncio.to_thread(doc_ref.get)
            return doc.to_dict() if doc.exists else None
        except Exception:
            return None

    async def _hard_reset_slot_full(self, slot_id: int, reason: str = "Tolerancia Zero", pnl: float = 0, trade_data: dict = None):
        """
        [V110.114] FULL Hard Reset: Idempotent slot reset with trade history logging + Genesis merge.
        This is the SINGLE source of truth for slot closure. All closures must flow through here.
        """
        # [V5.3.4] Cross-Loop Idempotency check:
        # If this slot was already reset by another loop (e.g. Guardian vs BybitREST), 
        # we skip the logging to avoid duplicates.
        current_state = await self.get_slot(slot_id)
        if not current_state or not current_state.get("symbol"):
            if trade_data:
                logger.warning(f"⚠️ [IDEMPOTENCY] Slot {slot_id} already reset. Skipping duplicate log for {trade_data.get('symbol')}")
            return False

        # [V53.5] Safety Lock - Don't reset if the slot was updated in the last 30s
        # UNLESS it's a valid closure with trade_data (meaning it's not a ghost cleanup)
        last_update = current_state.get("timestamp_last_update") or 0
        if (time.time() - last_update) < 30 and not trade_data:
            logger.warning(f"🛡️ [SAFETY LOCK] Blocking reset for Slot {slot_id} ({current_state.get('symbol')}). Updated too recently.")
            return

        # [V110.182] REAL-ASSET SHIELD: Impedir purga de slots simulados ou reais legítimos
        # se o slot tiver quantidade > 0 e preço > 0 e a purga for por "Ghost" ou "Pre-Open Purge",
        # a menos que venha acompanhada de trade_data legítimo com pnl (ou seja, fechamento real).
        exist_qty = float(current_state.get("qty") or 0)
        exist_entry = float(current_state.get("entry_price") or 0)
        is_phantom_purge = any(p_word in reason.upper() for p_word in ["GHOST", "PRE-OPEN PURGE", "CLEANUP", "ZOMBIE"])
        if exist_qty > 0 and exist_entry > 0 and is_phantom_purge:
            req_symbol = (trade_data or {}).get("symbol")
            slot_symbol = current_state.get("symbol")
            # Se for do mesmo símbolo e tiver PnL legítimo, ou se não houver conflito de símbolos, permite.
            # Caso contrário (símbolos diferentes), bloqueia o reset indevido.
            if slot_symbol and req_symbol and req_symbol.upper().replace(".P","") != slot_symbol.upper().replace(".P",""):
                logger.error(f"🛡️ [REAL-ASSET SHIELD] Bloqueando hard reset do Slot {slot_id} ({slot_symbol}) por motivo de '{reason}'. Posição física/simulada ativa (@ ${exist_entry}, Qty: {exist_qty}) protegida contra purgas destrutivas.")
                return False

        logger.info(f"🚨 [HARD RESET] Slot {slot_id} | Motivo: {reason} | PNL: ${pnl:.2f}")

        # [V110.61] GENESIS RECOVERY: Se o slot está incompleto, tenta buscar na gênese
        if trade_data is None:
            trade_data = {}
        
        # Merge current slot state into trade_data if not present
        for k, v in current_state.items():
            if k not in trade_data:
                trade_data[k] = v

        # [V121 AUTO-CALC] Se o slot continha posição real ativa, calcula o PnL residual dinamicamente
        symbol = trade_data.get("symbol")
        entry_price = float(trade_data.get("entry_price") or 0)
        qty = float(trade_data.get("qty") or 0)
        side = trade_data.get("side", "BUY")
        entry_margin = float(trade_data.get("entry_margin") or 0)
        leverage = float(trade_data.get("leverage") or 50)
        
        if symbol and entry_price > 0 and qty > 0:
            # 1. Tenta obter o preço atual do ativo
            market_price = 0.0
            clean_sym = symbol.replace(".P", "").upper()
            
            # Método A: Buscar no Redis (ticker rápido)
            try:
                from services.redis_service import redis_service
                market_price = await redis_service.get_ticker(clean_sym) or 0.0
            except Exception as e:
                logger.debug(f"Redis get_ticker fallback failed: {e}")
                
            # Método B: WebSocket da Bybit
            if market_price <= 0:
                try:
                    from services.bybit_ws import bybit_ws_service
                    market_price = getattr(bybit_ws_service, 'get_current_price', lambda s: 0.0)(clean_sym)
                except Exception as e:
                    logger.debug(f"Bybit WS price fallback failed: {e}")
                    
            # Método C: REST API da OKX
            if market_price <= 0:
                try:
                    from services.okx_rest import okx_rest_service
                    ticker = await okx_rest_service.get_tickers(symbol)
                    if ticker and ticker.get("result", {}).get("list"):
                        market_price = float(ticker["result"]["list"][0].get("lastPrice", 0))
                except Exception as e:
                    logger.debug(f"OKX REST price fallback failed: {e}")
            
            # Fallback para o current_stop ou entry_price do slot se tudo falhar
            if market_price <= 0:
                market_price = float(trade_data.get("current_stop") or entry_price)
                
            # Define o exit_price no trade_data
            trade_data["exit_price"] = market_price
            
            # Se o pnl passado for 0, calcula
            if pnl == 0:
                pnl_percent = 0.0
                if side.upper() in ["BUY", "LONG"]:
                    price_diff_pct = (market_price - entry_price) / entry_price
                else:
                    price_diff_pct = (entry_price - market_price) / entry_price
                pnl_percent = round(price_diff_pct * leverage * 100, 2)
                pnl = round(entry_margin * (pnl_percent / 100), 4)
                
                trade_data["pnl_percent"] = pnl_percent
                trade_data["pnl"] = pnl
                trade_data["final_roi"] = pnl_percent

        # Resolve Order ID para busca na gênese
        symbol = trade_data.get("symbol")
        open_ts = int(trade_data.get("opened_at") or 0)
        order_id = trade_data.get("order_id")
        if not order_id and symbol and open_ts:
            order_id = f"{symbol.replace('.P','')}_{open_ts}"
        
        if order_id:
            genesis = await self.get_order_genesis(order_id)
            if genesis:
                logger.info(f"🧬 [GENESIS-LINK] Recuperados metadados táticos para {symbol} ({order_id})")
                # Merge genesis data into trade_data (genesis wins for tactical intel)
                for k, v in genesis.items():
                    if k not in trade_data or trade_data[k] in [None, 0, "N/A", {}]:
                        trade_data[k] = v
        
        # [V110.114] VAULT PROTECTION: Block ghost cleanups but allow breakeven trades
        _GHOST_TAGS = ["GHOST", "PURGE", "CLEANUP", "SYNC"]
        is_ghost_cleanup = any(tag in reason.upper() for tag in _GHOST_TAGS)
        # Log if PnL is meaningful OR if it's a real trade (non-ghost) at breakeven
        if trade_data and (abs(pnl) >= 0.0001 or not is_ghost_cleanup):
            trade_data["close_reason"] = reason
            trade_data["pnl"] = pnl
            
            # 🆕 V110.8 Generate Enriched Audit Report
            initial_reasoning = current_state.get("pensamento", "N/A")
            final_roi = trade_data.get("final_roi", 0)
            sl_phase = trade_data.get("sl_phase_at_close", "UNKNOWN")
            score = trade_data.get("score", 0)
            pattern_val = trade_data.get("pattern", "N/A")
            pnl_percent = trade_data.get("pnl_percent", 0)
            entry_price = trade_data.get("entry_price", 0)
            exit_price = trade_data.get("exit_price", 0)
            current_stop = trade_data.get("current_stop_at_close", 0)
            target_price = trade_data.get("target_price_at_close", 0)
            entry_margin = trade_data.get("entry_margin", 0)
            leverage = trade_data.get("leverage", 50)
            fleet_intel = trade_data.get("fleet_intel", {})
            unified_conf = trade_data.get("unified_confidence", 50)
            
            outcome_label = "🚀 WIN" if pnl >= 0 else "🛡️ LOSS"
            
            report = f"--- AUDIT REPORT V110.132 ---\n"
            report += f"GENESIS ID: {order_id}\n"
            report += f"SYMBOL: {trade_data.get('symbol')}\n"
            report += f"STRATEGY: {trade_data.get('slot_type')}\n"
            report += f"REASONING: {initial_reasoning}\n"
            report += f"\n⚓ FLEET INTELLIGENCE (V56.0):\n"
            report += f"  - Unified Confidence: {unified_conf}%\n"
            report += f"  - Macro: {fleet_intel.get('macro', 50)}%\n"
            report += f"  - Whale: {fleet_intel.get('micro', 50)}%\n"
            report += f"  - SMC: {fleet_intel.get('smc', 50)}%\n"
            report += f"  - OnChain: {fleet_intel.get('onchain', 50)}%\n"
            if fleet_intel.get('onchain_summary'):
                report += f"  💡 {fleet_intel.get('onchain_summary')}\n"
            
            report += f"\n📊 EXECUÇÃO:\n"
            report += f"  OUTCOME: {outcome_label}\n"
            report += f"  CLOSE REASON: {reason}\n"
            report += f"  PNL USD: ${pnl:.2f} ({pnl_percent:.1f}%)\n"
            report += f"  ROI: {final_roi:.1f}%\n"
            report += f"  SL PHASE: {sl_phase}\n"
            report += f"  ENTRY: ${entry_price:.6f} | EXIT: ${exit_price:.6f}\n"
            report += f"  SL: ${current_stop:.6f} | TP: ${target_price:.6f}\n"
            report += f"  MARGIN: ${entry_margin:.2f} | LEV: {leverage:.0f}x\n"
            report += f"  SCORE: {score} | PATTERN: {pattern_val}\n"
            report += f"-------------------------"
            
            from services.time_utils import get_br_iso_str
            trade_data["reasoning_report"] = report
            if "closed_at" not in trade_data:
                trade_data["closed_at"] = get_br_iso_str()
            if "timestamp" not in trade_data:
                trade_data["timestamp"] = trade_data["closed_at"]
            
            await self.log_trade(trade_data)
            
            # [V6.1] Persistent Symbol Cooldown
            await self.register_sl_cooldown(trade_data.get("symbol", ""), duration_seconds=120)

        # 2. Reset slot in Firebase and local cache (aligned with free_slot fields)
        reset_data = {
            "symbol": None,
            "side": None,
            "qty": 0,
            "entry_margin": 0,
            "opened_at": None,
            "fleet_intel": {},
            "unified_confidence": 50,
            "entry_price": 0,
            "initial_stop": 0,
            "current_stop": 0,
            "target_price": 0,
            "status_risco": "LIVRE",
            "pnl_percent": 0,
            "slot_type": None,
            "pattern": None,
            "pensamento": f"🔄 Reset: {reason}",
            "maestria_guard_active": False,
            "rescue_activated": False,
            "rescue_resolved": False,
            "sentinel_retests": 0,
            "partial_tp_hit": False,
            "sentinel_first_hit_at": 0,
            "timestamp_last_update": time.time()
        }
        await self.update_slot(slot_id, reset_data)
        
        # 2b. Force RTDB sync for immediate UI cleanup
        if self.rtdb:
            try:
                rtdb_data = self._clean_mojibake(reset_data)
                await asyncio.wait_for(asyncio.to_thread(self.rtdb.child("live_slots").child(str(slot_id)).update, rtdb_data), timeout=5.0)
            except Exception as rtdb_err:
                logger.warning(f"⚠️ [RTDB-SYNC] Failed to sync slot {slot_id} reset to RTDB: {rtdb_err}")
        
        # 3. Log event for monitoring
        emoji = "✅" if pnl >= 0 else "❌"
        await self.log_event("ExecutionProtocol", f"{emoji} Slot {slot_id} RESET: {reason} | PNL: ${pnl:.2f}", "SUCCESS" if pnl >= 0 else "WARNING")
        
        return True

    async def initialize_db(self):
        """Creates initial documents if they don't exist."""
        if not self.is_active: return
        
        try:
            # Banca
            doc_ref = self.db.collection("banca_status").document("status")
            banca_doc = await asyncio.to_thread(doc_ref.get)
            if not banca_doc.exists:
                await asyncio.to_thread(doc_ref.set, {
                    "id": "status",
                    "saldo_total": 0,
                    "risco_real_percent": 0,
                    "slots_disponiveis": 4
                })
            
            # Slots
            for i in range(1, 5):
                slot_ref = self.db.collection("slots_ativos").document(str(i))
                slot_doc = await asyncio.to_thread(slot_ref.get)
                if not slot_doc.exists:
                    await asyncio.to_thread(slot_ref.set, {
                        "id": i,
                        "symbol": None,
                        "side": None,
                        "entry_price": 0,
                        "current_stop": 0,
                        "status_risco": "LIVRE",
                        "pnl_percent": 0
                    })
        except Exception as e:
            logger.error(f"Error initializing DB: {e}")

    # --- Capitão Elite V5.0: Long-Term Memory ---
    async def get_captain_profile(self) -> dict:
        """Fetches the Captain's memory profile for the user."""
        if not self.is_active or not self.rtdb: 
            return self._get_default_profile()
        try:
            def _get_profile_sync():
                ref = self.rtdb.child("captain_profile")
                profile = ref.get()
                return profile if profile else None
            profile = await asyncio.to_thread(_get_profile_sync)
            return profile if profile else self._get_default_profile()
        except Exception as e:
            logger.error(f"Error fetching captain profile: {e}")
            return self._get_default_profile()

    def _get_default_profile(self) -> dict:
        """Returns the default Captain profile structure."""
        return {
            "name": "Almirante",
            "interests": ["NBA", "Trading", "Tecnologia"],
            "communication_style": "formal_com_humor",
            "risk_tolerance": "moderado",
            "long_term_goals": [],
            "facts_learned": []
        }

    async def update_captain_profile(self, updates: dict):
        """Updates specific fields in the Captain's profile."""
        if not self.is_active or not self.rtdb: return
        try:
            def _update_profile_sync():
                ref = self.rtdb.child("captain_profile")
                ref.update(updates)
            await asyncio.to_thread(_update_profile_sync)
            logger.info(f"Captain Profile updated: {list(updates.keys())}")
        except Exception as e:
            logger.error(f"Error updating captain profile: {e}")

    async def add_learned_fact(self, fact: str):
        """Adds a new fact to the Captain's knowledge base about the user."""
        if not self.is_active or not self.rtdb: return
        try:
            profile = await self.get_captain_profile()
            facts = profile.get("facts_learned", [])
            if fact not in facts:
                facts.append(fact)
                # Keep only last 20 facts to avoid bloat
                if len(facts) > 20:
                    facts = facts[-20:]
                await self.update_captain_profile({"facts_learned": facts})
                logger.info(f"Captain learned new fact: {fact}")
        except Exception as e:
            logger.error(f"Error adding learned fact: {e}")

    # --- V15.0 Consciousness Edition: Admiral Memory ---
    async def get_admiral_consciousness(self) -> dict:
        """[V15.0] Fetches the Admiral's persistent life facts and consciousness data."""
        if not self.is_active: return {}
        try:
            def _get():
                doc = self.db.collection("admiral_consciousness").document("life_facts").get()
                return doc.to_dict() if doc.exists else {}
            return await asyncio.to_thread(_get)
        except Exception as e:
            logger.error(f"Error fetching admiral consciousness: {e}")
            return {}

    async def update_admiral_consciousness(self, facts: dict):
        """[V15.0] Updates or merges new life facts into the Admiral's consciousness."""
        if not self.is_active: return
        try:
            def _update():
                self.db.collection("admiral_consciousness").document("life_facts").set(facts, merge=True)
            await asyncio.to_thread(_update)
            logger.info("🧠 Admiral Consciousness updated with new life facts.")
        except Exception as e:
            logger.error(f"Error updating admiral consciousness: {e}")

    # --- Persistent SL Cooldowns V5.3.2 ---
    async def register_sl_cooldown(self, symbol: str, duration_seconds: int = 300):
        """
        Registers a symbol in SL cooldown in Firebase RTDB.
        Symbol is normalized to ensure consistency.
        """
        if not self.is_active or not self.rtdb: return
        try:
            norm_symbol = symbol.replace(".P", "").upper()
            expiry_time = time.time() + duration_seconds
            
            def _register_sync():
                ref = self.rtdb.child("system_cooldowns").child(norm_symbol)
                ref.set({
                    "symbol": norm_symbol,
                    "expiry_time": expiry_time,
                    "duration": duration_seconds,
                    "timestamp": time.time()
                })
            await asyncio.to_thread(_register_sync)
            logger.warning(f"🛡️ [FIREBASE] Cooldown persistence: {norm_symbol} blocked until {datetime.datetime.fromtimestamp(expiry_time).strftime('%H:%M:%S')}")
        except Exception as e:
            logger.error(f"Error registering SL cooldown in Firebase: {e}")

    async def is_symbol_blocked(self, symbol: str) -> tuple:
        """
        Checks if a symbol is in persistent SL cooldown.
        Returns (is_blocked, remaining_seconds).
        """
        if not self.is_active or not self.rtdb: return False, 0
        try:
            norm_symbol = symbol.replace(".P", "").upper()
            
            def _check_sync():
                ref = self.rtdb.child("system_cooldowns").child(norm_symbol)
                snapshot = ref.get()
                return snapshot if snapshot else None
                
            data = await asyncio.to_thread(_check_sync)
            if not data:
                return False, 0
                
            expiry = data.get("expiry_time", 0)
            current_time = time.time()
            
            if current_time < expiry:
                remaining = int(expiry - current_time)
                return True, remaining
            else:
                # Cleanup expired cooldown
                def _cleanup_sync():
                    self.rtdb.child("system_cooldowns").child(norm_symbol).delete()
                await asyncio.to_thread(_cleanup_sync)
                return False, 0
        except Exception as e:
            logger.error(f"Error checking SL cooldown in Firebase: {e}")
            return False, 0

    async def get_paper_state(self):
        """[V110.23.5] Recupera o estado persistente do Paper Mode do Firestore."""
        if not self.is_active: return None
        try:
            doc = await asyncio.to_thread(self.db.collection("system_state").document("paper_engine").get)
            if doc.exists:
                return doc.to_dict()
        except Exception as e:
            logger.error(f"Error fetching paper state: {e}")
        return None

    async def update_paper_state(self, data: dict):
        """[V110.23.5] Salva o estado do Paper Mode no Firestore (Atômico)."""
        if not self.is_active: return
        try:
            # Converte para JSON safe (remover NaNs, convert Datetimes, etc)
            safe_data = self._make_json_safe(data)
            await asyncio.to_thread(self.db.collection("system_state").document("paper_engine").set, safe_data, merge=True)
        except Exception as e:
            logger.error(f"Error updating paper state: {e}")

    async def save_oracle_context(self, context: dict):
        """[V110.32.1] Persiste o contexto macro do Oracle no Firestore (Amnesia Guard)."""
        if not self.is_active: return
        try:
            safe_data = self._make_json_safe(context)
            safe_data["last_updated"] = time.time()
            await asyncio.to_thread(self.db.collection("system_state").document("oracle_context").set, safe_data, merge=True)
            # Sync to RTDB too for immediate UI and redundancy
            if self.rtdb:
                await asyncio.wait_for(asyncio.to_thread(self.rtdb.child("oracle_context").set, safe_data), timeout=5.0)
        except Exception as e:
            logger.error(f"Error saving oracle context: {e}")

    async def get_oracle_context(self) -> dict:
        """[V110.32.1] Recupera o último contexto macro validado do Oracle."""
        if not self.is_active: return None
        try:
            doc = await asyncio.to_thread(self.db.collection("system_state").document("oracle_context").get)
            if doc.exists:
                return doc.to_dict()
        except Exception as e:
            logger.error(f"Error fetching oracle context: {e}")
        return None

    # --- [V110.62] Adaptive Weighting & Bias ---
    async def get_system_bias(self) -> dict:
        """[V110.62] Busca os multiplicadores de peso salvos pelo LibrarianAuditor."""
        if not self.is_active or not self.rtdb: return {}
        try:
            def _get():
                return self.rtdb.child("system_bias").get()
            return await asyncio.to_thread(_get) or {}
        except Exception as e:
            logger.error(f"Error fetching system bias: {e}")
            return {}

    async def save_system_bias(self, biases: dict):
        """[V110.62] Salva os novos pesos de confiança no RTDB."""
        if not self.is_active or not self.rtdb: return
        try:
            def _set():
                self.rtdb.child("system_bias").set(biases)
            await asyncio.to_thread(_set)
        except Exception as e:
            logger.error(f"Error saving system bias: {e}")



firebase_service = FirebaseService()
