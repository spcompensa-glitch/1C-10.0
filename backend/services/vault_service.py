"""
Vault Management Service V9.0
Gerencia o ciclo de 10 trades Sniper com diversificação obrigatória e compound automático.
"""
import logging
import asyncio
import time
from datetime import datetime, timezone, timedelta
from config import settings
from services.firebase_service import firebase_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VaultService")


class VaultService:
    def __init__(self):
        self.cycle_doc_path = "vault_management/current_cycle"
        
    async def _sync_rtdb(self):
        """V15.0: Syncs current cycle status to RTDB for real-time dashboard."""
        try:
            status = await self.get_cycle_status()
            await firebase_service.update_vault_pulse(status)
        except Exception as e:
            logger.error(f"Error syncing vault to RTDB: {e}")
        
    async def get_cycle_status(self) -> dict:
        """
        Retorna o status atual do ciclo de 10 trades Sniper.
        Returns: {sniper_wins, cycle_number, cycle_profit, in_admiral_rest, rest_until}
        """
        try:
            if not firebase_service.is_active or not firebase_service.db:
                return self._default_cycle()
            
            def _get():
                doc = firebase_service.db.collection("vault_management").document("current_cycle").get()
                return doc.to_dict() if doc.exists else None
            
            data = await asyncio.to_thread(_get)
            if not data:
                # Initialize if not exists
                await self.initialize_cycle()
                return self._default_cycle()
            
            # Check if rest period has ended
            if data.get("in_admiral_rest") and data.get("rest_until"):
                rest_until = data["rest_until"]
                
                # V15.8.5: Robust datetime parsing (handles Firestore Timestamp, ISO string, or naive)
                if isinstance(rest_until, str):
                    try:
                        rest_until_dt = datetime.fromisoformat(rest_until.replace("Z", "+00:00"))
                    except ValueError:
                        rest_until_dt = datetime.now(timezone.utc)
                elif hasattr(rest_until, 'timestamp'): # Firestore Timestamp
                    rest_until_dt = datetime.fromtimestamp(rest_until.timestamp(), tz=timezone.utc)
                else:
                    rest_until_dt = rest_until # Assume already datetime

                now = datetime.now(timezone.utc)
                if now > rest_until_dt:
                    # Auto-exit rest mode
                    await self.deactivate_admiral_rest()
                    data["in_admiral_rest"] = False
                    
            return data
            
        except Exception as e:
            logger.error(f"Error getting cycle status: {e}")
            return self._default_cycle()
    
    def _default_cycle(self) -> dict:
        return {
            "sniper_wins": 0,
            "cycle_number": 1,
            "cycle_profit": 0.0,      # Lucro líquido Sniper (Wins - Losses)
            "cycle_losses": 0.0,      # Apenas perdas acumuladas Sniper
            "started_at": datetime.now(timezone.utc).isoformat(),
            "in_admiral_rest": False,
            "rest_until": None,
            "vault_total": 0.0,
            "cautious_mode": False,
            "min_score_threshold": 75,  # [V12.2] Dynamic Sniper Score (Reduced for $20 balance)
            "total_trades_cycle": 0,    # Target: 10
            "cycle_gains_count": 0,     # [V8.0] Count of trades with PnL > 0
            "cycle_losses_count": 0,    # [V8.0] Count of trades with PnL < 0
            "accumulated_vault": 0.0,
            "sniper_mode_active": True,  # [V10.6.2] Always Active by default
            # V9.0 Cycle Diversification & Compound
            "used_symbols_in_cycle": [],  # V9.0: Lista de pares já operados no ciclo
            "cycle_start_bankroll": 0.0,  # V9.0: Banca travada no início do ciclo
            "next_entry_value": 0.0,      # V9.0: Valor de entrada (10% da banca ciclo)
            # V11.0 Mega Cycle (1/100)
            "mega_cycle_wins": 0,         # V11.0: Trades com ROI >= 100%
            "mega_cycle_total": 0,        # V11.0: Total de trades no mega ciclo
            "mega_cycle_number": 1,       # V11.0: Número do mega ciclo atual
            "mega_cycle_profit": 0.0,      # V11.0: Lucro acumulado no mega ciclo
            "order_ids_processed": []     # V6.5.1: Ledger for idempotency
        }
    
    async def initialize_cycle(self):
        """Creates initial cycle document if it doesn't exist."""
        try:
            if not firebase_service.is_active or not firebase_service.db:
                return
                
            def _init():
                doc_ref = firebase_service.db.collection("vault_management").document("current_cycle")
                if not doc_ref.get().exists:
                    doc_ref.set(self._default_cycle())
                    logger.info("Vault cycle initialized.")
            
            await asyncio.to_thread(_init)
        except Exception as e:
            logger.error(f"Error initializing cycle: {e}")
    
    # ========== V9.0 CYCLE DIVERSIFICATION ==========
    
    async def is_symbol_used_in_cycle(self, symbol: str) -> bool:
        """
        V9.0: Verifica se um par já foi operado no ciclo atual de 10 trades.
        # V10.2: Dynamic Asset Locking (Drag Mode).
        - Drag Mode Active: Lock for 10 trades (Cycle).
        - Drag Mode Standby: Lock for 3 trades (Flexible).
        """
        try:
            current = await self.get_cycle_status()
            used_symbols = current.get("used_symbols_in_cycle", [])
            norm_symbol = symbol.replace(".P", "").upper()
            if not (norm_symbol.endswith("USDT") or norm_symbol.endswith("USDC")):
                norm_symbol = f"{norm_symbol}USDT"
            
            # V15.6 Optimization: Regra de Diversificação por Resultado (PnL)
            # Se o par está na lista, significa que houve um LOSS (PnL <= 0)
            if norm_symbol in used_symbols:
                logger.info(f"🔒 {norm_symbol} LOCKED: Bloqueio por LOSS ativo até o próximo ciclo de 10 vitórias.")
                return True
                
            return False
        except Exception as e:
            logger.error(f"Error checking symbol in cycle: {e}")
            return False
    
    async def add_symbol_to_cycle(self, symbol: str, pnl: float = 0):
        """
        V15.6 Optimization: Adiciona par à lista de exclusão APENAS se houver LOSS.
        Gains (PnL > 0) deixam o par disponível para novas oportunidades.
        """
        try:
            if not firebase_service.is_active or not firebase_service.db:
                return
            
            # Se for GAIN, não bloqueamos o par (Regra V15.6)
            if pnl > 0:
                logger.info(f"✅ V15.6: {symbol} (PnL: ${pnl:.2f}) - Par mantido disponível no ciclo.")
                return

            current = await self.get_cycle_status()
            used_symbols = current.get("used_symbols_in_cycle", [])
            norm_symbol = symbol.replace(".P", "").upper()
            if not (norm_symbol.endswith("USDT") or norm_symbol.endswith("USDC")):
                norm_symbol = f"{norm_symbol}USDT"
            
            # Adiciona à lista de bloqueio (One Strike Out por Loss)
            if norm_symbol not in used_symbols:
                used_symbols.append(norm_symbol)
            
            def _update():
                firebase_service.db.collection("vault_management").document("current_cycle").update({
                    "used_symbols_in_cycle": used_symbols
                })
            
            await asyncio.to_thread(_update)
            logger.info(f"🔄 V15.6: {norm_symbol} (LOSS) bloqueado para este ciclo.")
            
            # [V15.0] Sync to RTDB
            await self._sync_rtdb()
            
        except Exception as e:
            logger.error(f"Error adding symbol to cycle: {e}")
    
    async def reset_cycle_symbols(self):
        """
        V9.0: Reseta a lista de pares após completar 10 trades.
        """
        try:
            if not firebase_service.is_active or not firebase_service.db:
                return
            
            current = await self.get_cycle_status()
            new_cycle_number = current.get("cycle_number", 1) + 1
            
            def _reset():
                firebase_service.db.collection("vault_management").document("current_cycle").update({
                    "used_symbols_in_cycle": [],
                    "cycle_number": new_cycle_number,
                    "total_trades_cycle": 0,
                    "cycle_gains_count": 0,
                    "cycle_losses_count": 0,
                    "cycle_profit": 0.0,
                    "started_at": datetime.now(timezone.utc).isoformat()
                })
            
            await asyncio.to_thread(_reset)
            await firebase_service.log_event("VAULT", f"🔄 V9.0: CICLO #{new_cycle_number} INICIADO! Lista de exclusão resetada. 83 pares disponíveis.", "SUCCESS")
            logger.info(f"V9.0: Cycle symbols reset. New cycle #{new_cycle_number}")
            
            # [V15.0] Sync to RTDB
            await self._sync_rtdb()
            
        except Exception as e:
            logger.error(f"Error resetting cycle symbols: {e}")
    
    async def initialize_cycle_bankroll(self, balance: float):
        """
        V9.0: Trava a banca no início de um novo ciclo para compound.
        V15.8.1: Ensures configured_balance is prioritized if set.
        """
        try:
            if not firebase_service.is_active or not firebase_service.db:
                return
            
            # [V15.8.1] Check configured balance again to ensure we don't overwrite user preference with small real balance
            banca_status = await firebase_service.get_banca_status()
            config_balance = banca_status.get("configured_balance", 0)
            
            final_balance = config_balance if config_balance >= 5 else balance
            entry_value = final_balance * 0.10  # [V10.6.2] Correct 10% margin rule
            
            def _init():
                firebase_service.db.collection("vault_management").document("current_cycle").update({
                    "cycle_start_bankroll": final_balance,
                    "cycle_bankroll": final_balance,
                    "next_entry_value": entry_value
                })
            
            await asyncio.to_thread(_init)
            logger.info(f"📊 V15.8.1 Compound: Banca travada em ${final_balance:.2f} . Entrada: ${entry_value:.2f}")
            await firebase_service.log_event("VAULT", f"📊 V15.8 COMPOUND: Ciclo iniciado com ${final_balance:.2f} . Cada trade usará ${entry_value:.2f}.", "SUCCESS")
            
            # [V15.0] Sync to RTDB
            await self._sync_rtdb()
            
        except Exception as e:
            logger.error(f"Error initializing cycle bankroll: {e}")
    
    async def recalculate_cycle_bankroll(self):
        """
        V9.0: Recalcula a banca após completar 10 trades (Compound).
        V15.8 FIX: Prioriza configured_balance do Almirante em vez do Bybit real.
        """
        try:
            # [V15.8 FIX] Fetch the configured balance first
            banca_status = await firebase_service.get_banca_status()
            config_balance = banca_status.get("configured_balance", 0)
            from services.okx_rest import okx_rest_service
            real_balance = await okx_rest_service.get_wallet_balance()
            
            # [V19.0] Base for compound is ALWAYS the total equity (Capital + Total PnL)
            new_balance = banca_status.get("saldo_total", config_balance if config_balance >= 5 else real_balance)
            
            current = await self.get_cycle_status()
            old_bankroll = current.get("cycle_start_bankroll", 0)
            
            profit_pct = ((new_balance - old_bankroll) / old_bankroll * 100) if old_bankroll > 0 else 0
            new_entry = new_balance * 0.10 # [V10.6.2] Correct 10% margin rule
            
            if not firebase_service.is_active or not firebase_service.db:
                return
            
            def _update():
                firebase_service.db.collection("vault_management").document("current_cycle").update({
                    "cycle_start_bankroll": new_balance,
                    "next_entry_value": new_entry,
                    "cycle_bankroll": new_balance  # Ensure legacy field is also updated
                })
            
            await asyncio.to_thread(_update)
            
            emoji = "🚀" if profit_pct > 0 else "⚠️"
            logger.info(f"V9.0 Compound: Recálculo completo. Nova banca: ${new_balance:.2f} (Real Bybit: ${real_balance:.2f})")
            await firebase_service.log_event("VAULT", f"{emoji} V9.0 COMPOUND RECALCULADO: ${old_bankroll:.2f} → ${new_balance:.2f}. Nova entrada: ${new_entry:.2f}", "SUCCESS")
            
            # [V15.0] Sync to RTDB
            await self._sync_rtdb()
            
        except Exception as e:
            logger.error(f"Error recalculating cycle bankroll: {e}")
    
    async def get_used_symbols_in_cycle(self) -> list:
        """
        V9.0: Retorna lista de pares já usados no ciclo atual.
        """
        try:
            current = await self.get_cycle_status()
            return current.get("used_symbols_in_cycle", [])
        except Exception as e:
            logger.error(f"Error getting used symbols: {e}")
            return []
    
    # ========== END V9.0 ==========

    async def register_sniper_trade(self, trade_data: dict) -> dict:
        """
        [V11.0] SNIPER TRADE: Registra um trade no ciclo.
        - Contador 1/10: Só conta como WIN se ROI >= 100%
        - Contador 1/100: Mega ciclo também incrementa com ROI >= 100%
        """
        try:
            from config import settings
            
            if not firebase_service.is_active or not firebase_service.db:
                return self._default_cycle()
            
            current = await self.get_cycle_status()
            pnl = trade_data.get("pnl", 0)
            
            # [V6.5.1] Idempotency Check (Ledger)
            order_id = trade_data.get("order_id")
            processed_ids = current.get("order_ids_processed", [])
            if order_id and order_id in processed_ids:
                logger.warning(f"🛡️ [VAULT IDEMPOTENCY] Order {order_id} already processed. Skipping counters.")
                return current

            # 🆕 V6.5.1: Add ID to ledger (keep list small, only last 20)
            if order_id:
                processed_ids.append(order_id)
                if len(processed_ids) > 20: 
                    processed_ids = processed_ids[-20:]

            # V11.0: Calcular ROI para verificação de WIN
            roi = trade_data.get("pnl_percent", 0)
            if roi == 0 and trade_data.get("entry_price") and trade_data.get("exit_price"):
                from services.execution_protocol import execution_protocol
                roi = execution_protocol.calculate_roi(
                    trade_data["entry_price"], 
                    trade_data["exit_price"], 
                    trade_data.get("side", "Buy")
                )

            # [V20.2] Unificação do Contador (Almirante's Guideline):
            # Slots 3 & 4 (TREND) agora incrementam o ciclo 1/10 em QUALQUER resultado (Win/Loss).
            # Slots 1 & 2 (SCALP) são ignorados pelo contador 1/10 (Missões), mas aparecem no histórico.
            slot_id = trade_data.get("slot_id")
            is_trend_slot = slot_id in [3, 4]
            
            # V11.0: WIN_ROI_THRESHOLD define o mínimo para contar como vitória de ELITE
            win_threshold = getattr(settings, 'WIN_ROI_THRESHOLD', 80.0)
            is_high_roi_win = (roi or 0) >= win_threshold
            is_pnl_positive = (pnl or 0) > 0
            
            new_wins_count = current.get("cycle_gains_count", 0)
            new_losses_count = current.get("cycle_losses_count", 0)
            new_total_trades = current.get("total_trades_cycle", 0)
            
            # V11.0: Mega Cycle counters
            mega_wins = current.get("mega_cycle_wins", 0)
            mega_total = current.get("mega_cycle_total", 0)
            mega_profit = current.get("mega_cycle_profit", 0.0)
            mega_number = current.get("mega_cycle_number", 1)
            
            # Lógica de contagem V20.2:
            if is_trend_slot:
                # Slot 3/4: Sempre incrementa o ciclo 1/10
                new_total_trades += 1
                if is_pnl_positive:
                    new_wins_count += 1
                    result_label = "TREND GAIN 🚀"
                    result_emoji = "💎"
                else:
                    new_losses_count += 1
                    result_label = "TREND LOSS 🔴"
                    result_emoji = "❌"
            else:
                # Slot 1/2: Apenas registra, não mexe no contador 1/10
                result_label = "SCALP"
                result_emoji = "⚡"
                if is_pnl_positive:
                    result_label += " GAIN"
                else:
                    result_label += " LOSS"
            
            # Mega Cycle: Mantém a regra de ROI >= 80% para ser "Elite Hunter"
            if is_high_roi_win:
                mega_wins += 1
                mega_total += 1
                new_wins_count += 1 # Increment cycle wins on Elite Win
                if not is_trend_slot:
                    result_label += " (MISSION ELITE)"
            
            mega_profit += pnl
            new_profit = current.get("cycle_profit", 0) + pnl
            
            update_data = {
                "cycle_gains_count": new_wins_count,
                "cycle_losses_count": new_losses_count,
                "cycle_profit": new_profit,
                "total_trades_cycle": new_total_trades,
                # V11.0: Mega Cycle
                "mega_cycle_wins": mega_wins,
                "mega_cycle_total": mega_total,
                "mega_cycle_profit": mega_profit,
                "updated_at": int(time.time() * 1000),
                "order_ids_processed": processed_ids
            }
            
            # V11.0: Mega Cycle Completion (100 trades de 80% ROI)
            if mega_wins >= 100:
                mega_number += 1
                update_data["mega_cycle_number"] = mega_number
                update_data["mega_cycle_wins"] = 0
                update_data["mega_cycle_total"] = 0
                update_data["mega_cycle_profit"] = 0.0
                await firebase_service.log_event("VAULT", f"🏆🏆🏆 MEGA CICLO #{mega_number-1} CONCLUÍDO! 100 missões com ROI >= 80%! Lucro: ${mega_profit:.2f}", "SUCCESS")
            
            def _update():
                firebase_service.db.collection("vault_management").document("current_cycle").update(update_data)
            
            await asyncio.to_thread(_update)
            
            # [V20.4] Compound recalibration: Only at the end of the 10-trade cycle
            # Removed real-time compound (recalculate_cycle_bankroll) to keep entry fixed as requested.
            
            # [V10.6.2] Automated 10-Trade Cycle Recalibration
            # [V20.5] Compound recalibration: Activated precisely on the 10th Elite Win (ROI >= 80%)
            if new_wins_count >= 10:
                await firebase_service.log_event("VAULT", f"🏁 CICLO DE 10 MISSÕES FINALIZADO! 10 wins com ROI>=80% alcançadas.", "SUCCESS")
                await self.recalculate_cycle_bankroll() # Trigger Compound (10% of total bankroll)
                await self.reset_cycle_symbols()
                
            # Log detalhado V11.0
            event_type = "SUCCESS" if is_high_roi_win else ("INFO" if is_pnl_positive else "WARNING")
            result_msg = f"{result_emoji} V11.0 {result_label} | ROI: {roi:.1f}% | 1/10: {new_wins_count}/10 | 1/100: {mega_wins}/100 | PnL: ${pnl:.2f}"
            await firebase_service.log_event("VAULT", result_msg, event_type)
            
            if new_wins_count >= 10:
                await firebase_service.log_event("VAULT", f"🏆 CICLO PERFEITO #{current.get('cycle_number', 1)}! 10 trades com ROI>=80%! Sniper Profit: ${new_profit:.2f}", "SUCCESS")
            
            # [V15.6] Diversification by Result: Gain keeps symbol, Loss locks it.
            if trade_data.get("symbol"):
                await self.add_symbol_to_cycle(trade_data.get("symbol"), pnl=pnl)

            # [V15.0] Sync to RTDB
            await self._sync_rtdb()

            return current
            
        except Exception as e:
            logger.error(f"Error registering sniper trade: {e}")
            return self._default_cycle()

    async def sync_vault_with_history(self):
        """
        V5.2.2: Reconstrói o status do ciclo atual baseando-se no histórico de trades.
        Percorre os trades do ciclo atual e recalcula wins (ROI >= 80%) e lucro.
        """
        try:
            logger.info("🔄 Iniciando Sincronização Vault <-> Histórico...")
            if not firebase_service.is_active or not firebase_service.db:
                return
                
            current = await self.get_cycle_status()
            cycle_num = current.get("cycle_number", 1)
            
            # 1. Fetch trades for this cycle (Sniper & Surf)
            def _get_history():
                docs = (firebase_service.db.collection("trade_history").stream())
                return [d.to_dict() for d in docs]
            
            all_trades = await asyncio.to_thread(_get_history)
            
            # Filtro opcional: apenas trades após a data de início do ciclo
            started_at = current.get("started_at")
            trades = all_trades  # Default for loop
            if started_at:
                try:
                    start_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                    trades = [t for t in all_trades if datetime.fromisoformat(t["timestamp"].replace("Z", "+00:00")) >= start_dt]
                except: pass

            logger.info(f"Encontrados {len(trades)} trades para o Ciclo #{cycle_num}")
            
            # 2. Recalculate
            new_wins = 0
            new_profit = 0.0
            new_losses = 0.0
            new_surf_profit = 0.0
            used_symbols = set()
            total_mega_wins = 0 # V15.1
            
            from services.execution_protocol import execution_protocol
            
            # Recalculate Mega Wins from all history
            logger.info(f"📊 Recalculando Missão Elite sobre {len(all_trades)} trades totais...")
            for t in all_trades:
                try:
                    # Robust slot_type check
                    st = t.get("slot_type", "UNKNOWN")
                    if st in ["SNIPER", "SWING", "SURF", "TREND", "SCALP", "UNKNOWN"]:
                        # Robust ROI parsing
                        t_roi = t.get("pnl_percent")
                        if t_roi is None or t_roi == 0:
                            if t.get("entry_price") and t.get("exit_price"):
                                t_roi = execution_protocol.calculate_roi(t["entry_price"], t["exit_price"], t.get("side", "Buy"))
                        
                        # Handle string ROI from Firestore if necessary
                        if isinstance(t_roi, str):
                            try:
                                t_roi = float(t_roi.replace('%', '').strip())
                            except: t_roi = 0.0
                        
                        # Convert to float to be safe
                        t_roi = float(t_roi or 0)
                        
                        threshold = getattr(settings, 'WIN_ROI_THRESHOLD', 80.0)
                        if t_roi >= threshold:
                            total_mega_wins += 1
                            # logger.info(f"  ✨ Elite Win Detectada: {t.get('symbol')} ({t_roi:.1f}%)")
                except Exception as e:
                    logger.warning(f"Erro ao processar trade no loop mega: {e}")
            
            logger.info(f"🏆 Missão Elite final: {total_mega_wins}/100")
            
            for t in trades:
                pnl = t.get("pnl", 0)
                roi = t.get("pnl_percent", 0)
                slot_type = t.get("slot_type", "SNIPER")
                symbol = t.get("symbol")
                
                # Filter by timestamp if cycle start is known
                if started_at:
                    try:
                        t_dt = datetime.fromisoformat(t["timestamp"].replace("Z", "+00:00"))
                        if t_dt < start_dt: continue
                    except: pass

                # Sum PnL for ALL trades in the period
                new_profit += pnl
                if pnl < 0:
                    new_losses += abs(pnl)

                if slot_type in ["SNIPER", "SWING", "SURF", "TREND", "SCALP"]:
                    if roi is None or roi == 0:
                        if t.get("entry_price") and t.get("exit_price"):
                            roi = execution_protocol.calculate_roi(t["entry_price"], t["exit_price"], t.get("side", "Buy"))
                            # Store the calculated ROI back to improve future lookups/UI
                            try:
                                doc_id = t.get("id")
                                if doc_id:
                                    firebase_service.db.collection("trade_history").document(doc_id).update({"pnl_percent": roi})
                            except: pass
                    
                    if roi and roi >= getattr(settings, 'WIN_ROI_THRESHOLD', 80.0):
                        new_wins += 1
                    
                    # Track unique symbols for the cycle
                    if symbol:
                        norm_symbol = symbol.replace(".P", "").upper()
                        used_symbols.add(norm_symbol)
                        
                elif slot_type == "SURF":
                    new_surf_profit += pnl
            
            # 3. Update Database
            # [V25.1] total_trades_cycle should count only trades in the current 10-trade window
            # NOT all historical trades. Use modulo to prevent META 100 false positive.
            slot34_trades = len([t for t in trades if t.get('slot_id') in [3, 4]])
            total_trades_capped = slot34_trades % 10  # Reset every 10 trades as designed
            
            update_data = {
                "sniper_wins": new_wins,
                "cycle_profit": new_profit,
                "cycle_losses": new_losses,
                "cycle_gains_count": total_mega_wins % 10, # Align with 10-win cycle
                "cycle_losses_count": len([t for t in trades if (t.get('pnl') or 0) <= 0]),
                "total_trades_cycle": total_trades_capped,
                "used_symbols_in_cycle": list(used_symbols),
                "mega_cycle_wins": total_mega_wins, # V15.1
                "updated_at": int(time.time() * 1000)
            }
            
            def _push():
                firebase_service.db.collection("vault_management").document("current_cycle").update(update_data)
            
            await asyncio.to_thread(_push)
            # logger.info(f"✅ Sincronização concluída: #{new_wins}/20 Wins | Total Trades (Sniper): {len([t for t in all_trades if t.get('slot_type') == 'SNIPER'])} | Profit: ${new_profit:.2f} | Symbols: {len(used_symbols)}")
            # await firebase_service.log_event("VAULT", f"🔄 SINCRONIA COMPLETA: #{new_wins}/20 | Trades (Sniper): {len([t for t in all_trades if t.get('slot_type') == 'SNIPER'])}/10 | Profit: ${new_profit:.2f}", "SUCCESS")
            
            # [V15.0] Sync to RTDB
            await self._sync_rtdb()
            
        except Exception as e:
            logger.error(f"Error syncing vault with history: {e}")

    async def calculate_withdrawal_amount(self) -> dict:
        """
        Calcula o valor recomendado para saque (20% do lucro do ciclo).
        Retorna: {recommended_20pct, cycle_profit, vault_total}
        """
        try:
            current = await self.get_cycle_status()
            cycle_profit = current.get("cycle_profit", 0)
            vault_total = current.get("vault_total", 0)
            
            return {
                "recommended_20pct": cycle_profit * 0.20,
                "cycle_profit": cycle_profit,
                "vault_total": vault_total,
                "sniper_wins": current.get("sniper_wins", 0)
            }
        except Exception as e:
            logger.error(f"Error calculating withdrawal: {e}")
            return {"recommended_20pct": 0, "cycle_profit": 0, "vault_total": 0, "sniper_wins": 0}
    
    async def execute_withdrawal(self, amount: float, destination: str = "personal_vault") -> bool:
        """
        Registra uma retirada manual para o Vault.
        """
        try:
            if not firebase_service.is_active or not firebase_service.db:
                return False
            
            current = await self.get_cycle_status()
            new_vault_total = current.get("vault_total", 0) + amount
            
            withdrawal_record = {
                "amount": amount,
                "cycle_number": current.get("cycle_number", 1),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "destination": destination
            }
            
            def _execute():
                # Add to withdrawals subcollection
                firebase_service.db.collection("vault_management").document("withdrawals").collection("history").add(withdrawal_record)
                # Update vault total
                firebase_service.db.collection("vault_management").document("current_cycle").update({
                    "vault_total": new_vault_total
                })
            
            await asyncio.to_thread(_execute)
            await firebase_service.log_event("VAULT", f"💰 Retirada de ${amount:.2f} registrada. Cofre Total: ${new_vault_total:.2f}", "SUCCESS")
            
            # [V15.0] Sync to RTDB
            await self._sync_rtdb()
            
            return True
        except Exception as e:
            logger.error(f"Error executing withdrawal: {e}")
            return False
    
    async def get_withdrawal_history(self, limit: int = 20) -> list:
        """Retorna histórico de retiradas."""
        try:
            if not firebase_service.is_active or not firebase_service.db:
                return []
            
            def _get():
                docs = (firebase_service.db.collection("vault_management")
                        .document("withdrawals")
                        .collection("history")
                        .order_by("timestamp", direction="DESCENDING")
                        .limit(limit)
                        .stream())
                return [d.to_dict() for d in docs]
            
            return await asyncio.to_thread(_get)
        except Exception as e:
            logger.error(f"Error getting withdrawal history: {e}")
            return []
    
    async def start_new_cycle(self) -> dict:
        """
        Inicia um novo ciclo após completar 20 trades ou retirada manual.
        """
        try:
            if not firebase_service.is_active or not firebase_service.db:
                return self._default_cycle()
            
            current = await self.get_cycle_status()
            new_cycle = current.get("cycle_number", 1) + 1
            
            new_data = {
                "sniper_wins": 0,
                "cycle_number": new_cycle,
                "cycle_profit": 0.0,
                "cycle_losses": 0.0,
                "surf_profit": 0.0,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "in_admiral_rest": current.get("in_admiral_rest", False),
                "rest_until": current.get("rest_until"),
                "vault_total": current.get("vault_total", 0),
                "cautious_mode": False,
                "min_score_threshold": 75,
                "total_trades_cycle": 0,
                "accumulated_vault": current.get("accumulated_vault", 0.0)
            }
            
            def _update():
                firebase_service.db.collection("vault_management").document("current_cycle").set(new_data)
            
            await asyncio.to_thread(_update)
            await firebase_service.log_event("VAULT", f"🚀 Novo Ciclo #{new_cycle} iniciado!", "SUCCESS")
            
            # [V15.0] Sync to RTDB
            await self._sync_rtdb()
            
            return new_data
        except Exception as e:
            logger.error(f"Error starting new cycle: {e}")
            return self._default_cycle()
    
    async def activate_admiral_rest(self, hours: int = 24) -> bool:
        """
        Ativa o modo de descanso do Almirante (bloqueia novas ordens).
        """
        try:
            if not firebase_service.is_active or not firebase_service.db:
                return False
            
            rest_until = datetime.now(timezone.utc) + timedelta(hours=hours)
            
            def _activate():
                firebase_service.db.collection("vault_management").document("current_cycle").update({
                    "in_admiral_rest": True,
                    "rest_until": rest_until.isoformat()
                })
            
            await asyncio.to_thread(_activate)
            await firebase_service.log_event("VAULT", f"😴 Admiral's Rest ativado por {hours}h. Sistema em standby.", "WARNING")
            
            return True
        except Exception as e:
            logger.error(f"Error activating admiral rest: {e}")
            return False
    
    async def deactivate_admiral_rest(self) -> bool:
        """Desativa manualmente o modo de descanso."""
        try:
            if not firebase_service.is_active or not firebase_service.db:
                return False
            
            def _deactivate():
                firebase_service.db.collection("vault_management").document("current_cycle").update({
                    "in_admiral_rest": False,
                    "rest_until": None
                })
            
            await asyncio.to_thread(_deactivate)
            await firebase_service.log_event("VAULT", "⚡ Admiral's Rest desativado. Sistema operacional.", "SUCCESS")
            
            return True
        except Exception as e:
            logger.error(f"Error deactivating admiral rest: {e}")
            return False
    
    async def set_cautious_mode(self, enabled: bool, min_score: int = 85) -> bool:
        """
        Ativa/desativa modo cautela (aumenta threshold de score).
        """
        try:
            if not firebase_service.is_active or not firebase_service.db:
                return False
            
            def _set():
                firebase_service.db.collection("vault_management").document("current_cycle").update({
                    "cautious_mode": enabled,
                    "min_score_threshold": min_score if enabled else 75
                })
            
            await asyncio.to_thread(_set)
            
            status = f"ATIVADO (Score mínimo: {min_score})" if enabled else "DESATIVADO"
            await firebase_service.log_event("VAULT", f"⚠️ Modo Cautela {status}", "WARNING" if enabled else "INFO")
            
            return True
        except Exception as e:
            logger.error(f"Error setting cautious mode: {e}")
            return False

    async def set_sniper_mode(self, enabled: bool) -> bool:
        """
        [V8.0] Ativa ou Pausa o Capitão Sniper (Master Toggle).
        """
        try:
            if not firebase_service.is_active or not firebase_service.db:
                return False
            
            def _set():
                firebase_service.db.collection("vault_management").document("current_cycle").update({
                    "sniper_mode_active": enabled
                })
            
            await asyncio.to_thread(_set)
            
            status = "AUTORIZADO 🟢" if enabled else "BLOQUEADO 🔴"
            await firebase_service.log_event("VAULT", f"⚓ Capitão Sniper {status} pelo Almirante.", "SUCCESS" if enabled else "WARNING")
            
            return True
        except Exception as e:
            logger.error(f"Error setting sniper mode: {e}")
            return False
    
    async def is_trading_allowed(self) -> tuple[bool, str]:
        """
        Verifica se o sistema pode abrir novos trades.
        Returns: (allowed: bool, reason: str)
        """
        try:
            # [V110.178] PAPER MODE BYPASS: Paper mode has no cycle restrictions
            from services.okx_rest import okx_rest_service
            if okx_rest_service and okx_rest_service.execution_mode == "PAPER":
                return True, "Paper mode bypasses Almirante restrictions"

            status = await self.get_cycle_status()
            
            # [V10.6.2] Master Toggle IGNORED for Autonomous Mode
            # if not status.get("sniper_mode_active", True):
            #    return False, "Capitão Sniper está PAUSADO (Manual Stop)."

            if status.get("in_admiral_rest"):
                rest_until = status.get("rest_until", "")
                return False, f"Admiral's Rest ativo até {rest_until}"
            
            # [V5.2.5] Meta 100 Block
            if status.get("total_trades_cycle", 0) >= 100:
                return False, "META 100 ATINGIDA: Extraia 50% do lucro para continuar."
            
            return True, "Trading autorizado"
        except Exception as e:
            logger.error(f"Error checking trading permission: {e}")
            return True, "Fallback: Trading autorizado"

    async def get_dynamic_margin(self) -> float:
        """
        [V5.2.5] Calcula a margem dinâmica: 5% do saldo total (Banca + Lucro Ciclo).
        Garante o crescimento exponencial conforme planejado.
        """
        try:
            from services.okx_rest import okx_rest_service
            balance = await okx_rest_service.get_wallet_balance()
            
            # Margem = 5% do saldo total atual
            margin = balance * 0.05
            
            # Garantir mínimo de $5 para evitar ordens rejeitadas
            return max(5.0, margin)
        except Exception as e:
            logger.error(f"Error calculating dynamic margin: {e}")
            return 5.0
    
    async def get_min_score_threshold(self) -> int:
        """[V20.4] Retorna o threshold de score atual (60 normal, 70+ em modo cautela). Adjusted from 75 after removing +15 score inflation."""
        try:
            status = await self.get_cycle_status()
            return status.get("min_score_threshold", 60)
        except:
            return 60


vault_service = VaultService()
