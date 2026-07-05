from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from services.database_service import database_service
from services.sandbox_service import sandbox_service

router = APIRouter(prefix="/api/sandbox", tags=["Sandbox"])

@router.get("/trades")
async def get_sandbox_trades(active_only: bool = Query(False, description="Filtrar apenas por trades ativos")):
    try:
        trades = await database_service.get_sandbox_trades(active_only=active_only)
        # Converter para formato serializável
        result = []
        for t in trades:
            result.append({
                "id": t.id,
                "symbol": t.symbol,
                "strategy": t.strategy,
                "direction": t.direction,
                "entry_price": t.entry_price,
                "current_price": t.current_price,
                "stop_loss": t.stop_loss,
                "target": t.target,
                "max_roi": t.max_roi,
                "current_roi": t.current_roi,
                "pnl_pct": t.pnl_pct,
                "status": t.status,
                "opened_at": t.opened_at,
                "closed_at": t.closed_at,
                "flash_state": t.flash_state,
                "contract_meta": t.contract_meta,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "explosion_score": getattr(t, "explosion_score", 0) or 0,
                "explosion_signals": getattr(t, "explosion_signals", []) or []
            })
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar trades do sandbox: {str(e)}")

@router.get("/stats")
async def get_sandbox_stats():
    try:
        trades = await database_service.get_sandbox_trades(active_only=False)
        total = len(trades)
        active = sum(1 for t in trades if t.status == "ACTIVE")
        closed = total - active
        
        wins = 0
        losses = 0
        total_pnl_usd = 0.0  # [V119] Lucro acumulado em USD com margem de $2.00 do Founder Vision
        BANCA = 100.0
        MARGEM_MEDIA = 2.00
        # [V119] Inicializa preventivamente as 3 estratégias para garantir telemetria consistente na UI
        strategy_stats = {
            "ALPHA SHIELD": {"total": 0, "wins": 0, "losses": 0, "pnl": 0.0, "pnl_usd": 0.0},
            "VELOCITY FLOW": {"total": 0, "wins": 0, "losses": 0, "pnl": 0.0, "pnl_usd": 0.0},
            "DECOR SHADOW": {"total": 0, "wins": 0, "losses": 0, "pnl": 0.0, "pnl_usd": 0.0}
        }

        for t in trades:
            # PnL USD: (ROI / 100) * $2.00 de margem do Founder Vision
            trade_pnl_usd = (t.pnl_pct / 100.0) * MARGEM_MEDIA
            
            # Somar no PnL total da banca
            total_pnl_usd += trade_pnl_usd
            
            if t.status != "ACTIVE":
                if t.pnl_pct > 0:
                    wins += 1
                else:
                    losses += 1

            # Agrupar estatísticas por estratégia
            strat = t.strategy or "UNKNOWN"
            if strat not in strategy_stats:
                strategy_stats[strat] = {"total": 0, "wins": 0, "losses": 0, "pnl": 0.0, "pnl_usd": 0.0}
            
            strategy_stats[strat]["total"] += 1
            if t.status != "ACTIVE":
                if t.pnl_pct > 0:
                    strategy_stats[strat]["wins"] += 1
                else:
                    strategy_stats[strat]["losses"] += 1
                strategy_stats[strat]["pnl_usd"] += trade_pnl_usd
            else:
                strategy_stats[strat]["pnl_usd"] += trade_pnl_usd

        # [V113.2] ROI real da banca de $22.00: (total_pnl_usd / BANCA) * 100
        bank_pnl_percent = (total_pnl_usd / BANCA) * 100.0

        win_rate = (wins / closed * 100.0) if closed > 0 else 0.0
        avg_pnl = (bank_pnl_percent / total) if total > 0 else 0.0

        # [V113.2] Converter pnl_usd de cada estratégia para % da banca $22.00
        for strat in strategy_stats:
            strategy_stats[strat]["pnl"] = (strategy_stats[strat]["pnl_usd"] / BANCA) * 100.0

        # Encontrar melhor estratégia baseada em PnL total
        best_strategy = "N/A"
        best_pnl = -9999.0
        for strat, s_data in strategy_stats.items():
            if s_data["pnl"] > best_pnl:
                best_pnl = s_data["pnl"]
                best_strategy = strat

        # Tentar buscar o regime atual
        current_regime = "NEUTRAL"
        try:
            from services.agents.captain import captain_agent
            if hasattr(captain_agent, 'btc_market_regime'):
                current_regime = captain_agent.btc_market_regime.get("direction", "NEUTRAL")
        except Exception:
            pass

        return {
            "total_trades": total,
            "active_trades": active,
            "closed_trades": closed,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 2),
            "average_pnl": round(avg_pnl, 2),
            "total_pnl": round(bank_pnl_percent, 2),
            "best_strategy": best_strategy,
            "strategy_breakdown": strategy_stats,
            "current_regime": current_regime
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar estatísticas do sandbox: {str(e)}")

@router.get("/patterns")
async def get_sandbox_patterns():
    try:
        trades = await database_service.get_sandbox_trades(active_only=False)
        
        pair_stats = {}
        direction_stats = {"LONG": {"total": 0, "wins": 0, "pnl": 0.0}, "SHORT": {"total": 0, "wins": 0, "pnl": 0.0}}
        exit_phases = {}
        
        closed_trades = [t for t in trades if t.status != "ACTIVE"]
        
        for t in closed_trades:
            # Stats por Par
            sym = t.symbol
            if sym not in pair_stats:
                pair_stats[sym] = {"total": 0, "wins": 0, "losses": 0, "pnl": 0.0}
            
            pair_stats[sym]["total"] += 1
            is_win = t.pnl_pct > 0
            if is_win:
                pair_stats[sym]["wins"] += 1
            else:
                pair_stats[sym]["losses"] += 1
            pair_stats[sym]["pnl"] += t.pnl_pct
            
            # Stats por Direção
            dir_type = t.direction
            if dir_type in direction_stats:
                direction_stats[dir_type]["total"] += 1
                if is_win:
                    direction_stats[dir_type]["wins"] += 1
                direction_stats[dir_type]["pnl"] += t.pnl_pct
                
            # Fase do FlashAgent na saída
            # Normalmente salvo no flash_state ou deduzido pelo stop_loss / pnl
            state = t.flash_state or {}
            phase = state.get("phase", "DESCONHECIDA")
            exit_phases[phase] = exit_phases.get(phase, 0) + 1

        # Processar Melhores e Piores Pares
        recommended_pairs = []
        blacklist_candidates = []
        
        for sym, stat in pair_stats.items():
            wr = (stat["wins"] / stat["total"] * 100.0) if stat["total"] > 0 else 0.0
            stat["win_rate"] = round(wr, 2)
            stat["pnl"] = round(stat["pnl"], 2)
            
            # Critérios de recomendação
            if stat["total"] >= 2:
                if stat["pnl"] > 0 and wr >= 50.0:
                    recommended_pairs.append({"symbol": sym, "pnl": stat["pnl"], "win_rate": wr, "total": stat["total"]})
                elif stat["pnl"] < -10.0 or (wr < 30.0 and stat["total"] >= 3):
                    blacklist_candidates.append({"symbol": sym, "pnl": stat["pnl"], "win_rate": wr, "total": stat["total"]})

        recommended_pairs.sort(key=lambda x: x["pnl"], reverse=True)
        blacklist_candidates.sort(key=lambda x: x["pnl"])

        # Cálculo de Win Rate por Direção
        for d, s in direction_stats.items():
            s["win_rate"] = round((s["wins"] / s["total"] * 100.0), 2) if s["total"] > 0 else 0.0
            s["pnl"] = round(s["pnl"], 2)

        return {
            "total_analyzed": len(closed_trades),
            "pair_performance": pair_stats,
            "direction_performance": direction_stats,
            "exit_phases": exit_phases,
            "recommended_pairs": recommended_pairs,
            "blacklist_candidates": blacklist_candidates,
            "insights": {
                "best_direction": "LONG" if direction_stats["LONG"]["pnl"] > direction_stats["SHORT"]["pnl"] else "SHORT",
                "suggested_action": "Continuar acumulando amostras. É recomendado no mínimo 50 trades fechados para aplicar a blacklist com segurança no ambiente real." if len(closed_trades) < 50 else "Amostragem estatística madura. Considere aplicar a blacklist sugerida e focar nos pares recomendados."
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao extrair padrões: {str(e)}")


@router.get("/analytics")
async def get_sandbox_analytics():
    """[FIX-ANALYTICS] Endpoint de analytics detalhado do Sandbox: distribuição de losses por regime, símbolo e hora."""
    try:
        from datetime import datetime, timezone
        trades = await database_service.get_sandbox_trades(active_only=False)
        closed = [t for t in trades if t.status != "ACTIVE"]
        
        if not closed:
            return {
                "total_analyzed": 0,
                "message": "Nenhum trade fechado para analisar.",
                "loss_by_regime": {},
                "loss_by_symbol": {},
                "loss_by_hour": {},
                "win_loss_by_strategy": {},
                "avg_loss_roi": 0,
                "avg_win_roi": 0,
            }
        
        # Classificar regime pelo flash_state (se disponível) ou fallback
        def get_trade_regime(t):
            state = t.flash_state or {}
            # Prioridade: regime salvo no flash_state (V112.13+)
            saved = state.get('regime')
            if saved in ('LATERAL', 'TRENDING'):
                return saved
            # Fallback: trades com stop em -20% eram LATERAL, -40% eram TRENDING
            stop_roi = state.get('stop_roi', -40.0)
            if stop_roi >= -25.0:
                return 'LATERAL'
            return 'TRENDING'
        
        losses = [t for t in closed if t.pnl_pct <= 0]
        wins = [t for t in closed if t.pnl_pct > 0]
        
        # 1. Loss por Regime
        loss_by_regime = {}
        for t in losses:
            regime = get_trade_regime(t)
            if regime not in loss_by_regime:
                loss_by_regime[regime] = {"count": 0, "total_roi": 0, "avg_roi": 0}
            loss_by_regime[regime]["count"] += 1
            loss_by_regime[regime]["total_roi"] += t.pnl_pct
        for r in loss_by_regime:
            loss_by_regime[r]["avg_roi"] = round(loss_by_regime[r]["total_roi"] / loss_by_regime[r]["count"], 2)
        
        # 2. Loss por Símbolo (top 10 piores)
        loss_by_symbol = {}
        for t in losses:
            sym = t.symbol
            if sym not in loss_by_symbol:
                loss_by_symbol[sym] = {"count": 0, "total_roi": 0, "avg_roi": 0, "wins": 0}
            loss_by_symbol[sym]["count"] += 1
            loss_by_symbol[sym]["total_roi"] += t.pnl_pct
        for t in wins:
            sym = t.symbol
            if sym in loss_by_symbol:
                loss_by_symbol[sym]["wins"] += 1
        for s in loss_by_symbol:
            total = loss_by_symbol[s]["count"]
            loss_by_symbol[s]["avg_roi"] = round(loss_by_symbol[s]["total_roi"] / total, 2) if total else 0
            loss_by_symbol[s]["win_rate"] = round(loss_by_symbol[s]["wins"] / (loss_by_symbol[s]["wins"] + loss_by_symbol[s]["count"]) * 100, 1) if (loss_by_symbol[s]["wins"] + loss_by_symbol[s]["count"]) > 0 else 0
        # Ordenar por pior ROI
        sorted_symbols = sorted(loss_by_symbol.items(), key=lambda x: x[1]["total_roi"])
        loss_by_symbol = dict(sorted_symbols[:10])
        
        # 3. Loss por Hora UTC
        loss_by_hour = {}
        for t in losses:
            opened = t.opened_at or 0
            if opened > 0:
                try:
                    dt = datetime.fromtimestamp(opened, tz=timezone.utc)
                    hour = dt.hour
                except:
                    hour = -1
            else:
                hour = -1
            hour_key = str(hour) if hour >= 0 else "unknown"
            if hour_key not in loss_by_hour:
                loss_by_hour[hour_key] = {"count": 0, "total_roi": 0, "avg_roi": 0}
            loss_by_hour[hour_key]["count"] += 1
            loss_by_hour[hour_key]["total_roi"] += t.pnl_pct
        for h in loss_by_hour:
            loss_by_hour[h]["avg_roi"] = round(loss_by_hour[h]["total_roi"] / loss_by_hour[h]["count"], 2)
        
        # 4. Win/Loss por Estratégia
        win_loss_by_strategy = {}
        for t in closed:
            strat = t.strategy or "UNKNOWN"
            if strat not in win_loss_by_strategy:
                win_loss_by_strategy[strat] = {"wins": 0, "losses": 0, "total_pnl": 0, "win_rate": 0}
            if t.pnl_pct > 0:
                win_loss_by_strategy[strat]["wins"] += 1
            else:
                win_loss_by_strategy[strat]["losses"] += 1
            win_loss_by_strategy[strat]["total_pnl"] += t.pnl_pct
        for s in win_loss_by_strategy:
            total = win_loss_by_strategy[s]["wins"] + win_loss_by_strategy[s]["losses"]
            win_loss_by_strategy[s]["win_rate"] = round(win_loss_by_strategy[s]["wins"] / total * 100, 1) if total else 0
            win_loss_by_strategy[s]["total_pnl"] = round(win_loss_by_strategy[s]["total_pnl"], 2)
        
        avg_loss_roi = round(sum(t.pnl_pct for t in losses) / len(losses), 2) if losses else 0
        avg_win_roi = round(sum(t.pnl_pct for t in wins) / len(wins), 2) if wins else 0

        # [V113] Zero-PnL statistics — trades que fecharam exatamente no entry
        zero_pnl_trades = [t for t in closed if t.pnl_pct == 0.0]
        zero_pnl_count = len(zero_pnl_trades)
        zero_pnl_percent = round(zero_pnl_count / len(closed) * 100, 1) if closed else 0
        # Média de MaxROI dos trades com zero PnL (para dimensionar o impacto da escadinha)
        zero_pnl_avg_maxroi = round(sum(t.max_roi for t in zero_pnl_trades) / zero_pnl_count, 1) if zero_pnl_count else 0
        
        # Top winners and losers
        winners_sorted = sorted(wins, key=lambda t: t.pnl_pct, reverse=True)[:5]
        losers_sorted = sorted(losses, key=lambda t: t.pnl_pct)[:5]
        
        top_winners = [{
            "symbol": t.symbol,
            "pnl_pct": t.pnl_pct,
            "max_roi": t.max_roi,
            "strategy": t.strategy,
            "direction": t.direction
        } for t in winners_sorted]
        
        top_losers = [{
            "symbol": t.symbol,
            "pnl_pct": t.pnl_pct,
            "max_roi": t.max_roi,
            "strategy": t.strategy,
            "direction": t.direction
        } for t in losers_sorted]
        
        return {
            "total_analyzed": len(closed),
            "total_wins": len(wins),
            "total_losses": len(losses),
            "overall_win_rate": round(len(wins) / len(closed) * 100, 1) if closed else 0,
            "loss_by_regime": loss_by_regime,
            "loss_by_symbol": loss_by_symbol,
            "loss_by_hour": loss_by_hour,
            "win_loss_by_strategy": win_loss_by_strategy,
            "avg_loss_roi": avg_loss_roi,
            "avg_win_roi": avg_win_roi,
            "risk_reward_ratio": round(abs(avg_win_roi / avg_loss_roi), 2) if avg_loss_roi != 0 else 0,
            "zero_pnl_count": zero_pnl_count,
            "zero_pnl_percent": zero_pnl_percent,
            "zero_pnl_avg_maxroi": zero_pnl_avg_maxroi,
            "top_winners": top_winners,
            "top_losers": top_losers,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar analytics: {str(e)}")


@router.post("/clear")
async def clear_sandbox():
    try:
        success = await database_service.clear_sandbox_trades()
        return {"success": success, "message": "Sandbox resetado com sucesso."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao limpar sandbox: {str(e)}")


# =============================================================================
# SWING LAB — Endpoints BlitzSniperAgent (BLITZ_30M)
# =============================================================================

@router.get("/swing/trades")
async def get_swing_trades(active_only: bool = Query(False)):
    """Lista os trades do Swing Lab (BLITZ_30M)."""
    try:
        trades = await database_service.get_swing_trades(active_only=active_only)
        result = []
        for t in trades:
            result.append({
                "id":           t.id,
                "symbol":       t.symbol,
                "strategy":     t.strategy,
                "direction":    t.direction,
                "entry_price":  t.entry_price,
                "current_price":t.current_price,
                "stop_loss":    t.stop_loss,
                "target":       t.target,
                "max_roi":      t.max_roi,
                "current_roi":  t.current_roi,
                "pnl_pct":      t.pnl_pct,
                "status":       t.status,
                "opened_at":    t.opened_at,
                "closed_at":    t.closed_at,
                "flash_state":  t.flash_state,
                "contract_meta":t.contract_meta,
                "created_at":   t.created_at.isoformat() if t.created_at else None,
                # Campos Blitz extras
                "blitz_score":  getattr(t, "blitz_score", 0) or 0,
                "fib_zone":     getattr(t, "fib_zone", None),
                "sma_cross":    getattr(t, "sma_cross", None),
                "cvd_value":    getattr(t, "cvd_value", 0) or 0,
                "volume_ratio": getattr(t, "volume_ratio", 0) or 0,
                "pa_pattern":   getattr(t, "pa_pattern", None),
                "reasons":      getattr(t, "reasons", []) or [],
                "blitz_unit":   getattr(t, "blitz_unit", 0) or 0,
            })
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar trades do Swing Lab: {str(e)}")


@router.get("/swing/stats")
async def get_swing_stats():
    """Estatísticas do Swing Lab (Win Rate, R:R, ROI, banca virtual)."""
    try:
        trades = await database_service.get_swing_trades(active_only=False)
        BANCA  = 100.0
        MARGEM = 1.0   # $1/trade para o Blitz

        total  = len(trades)
        active = sum(1 for t in trades if t.status == "ACTIVE")
        closed = total - active

        wins   = 0
        losses = 0
        total_pnl_usd = 0.0
        win_pnls  = []
        loss_pnls = []
        symbol_stats: dict = {}

        for t in trades:
            if t.status == "ACTIVE":
                continue
            pnl = float(t.pnl_pct or 0)
            pnl_usd = (pnl / 100.0) * MARGEM
            total_pnl_usd += pnl_usd

            sym = t.symbol.replace(".P", "").upper()
            if sym not in symbol_stats:
                symbol_stats[sym] = {"total": 0, "wins": 0, "losses": 0, "pnl": 0.0}
            symbol_stats[sym]["total"] += 1
            symbol_stats[sym]["pnl"] += pnl

            if pnl > 0:
                wins += 1
                win_pnls.append(pnl)
                symbol_stats[sym]["wins"] += 1
            elif pnl < 0:
                losses += 1
                loss_pnls.append(pnl)
                symbol_stats[sym]["losses"] += 1

        win_rate  = round((wins / closed * 100), 2) if closed > 0 else 0.0
        avg_win   = round(sum(win_pnls) / len(win_pnls), 2) if win_pnls else 0.0
        avg_loss  = round(sum(loss_pnls) / len(loss_pnls), 2) if loss_pnls else 0.0
        rr        = round(abs(avg_win / avg_loss), 2) if avg_loss != 0 else 0.0
        bank_roi  = round((total_pnl_usd / BANCA) * 100, 2)
        balance   = round(BANCA + total_pnl_usd, 2)

        best_sym  = max(symbol_stats, key=lambda s: symbol_stats[s]["pnl"], default=None) if symbol_stats else None

        return {
            "total_trades":    total,
            "active_trades":   active,
            "closed_trades":   closed,
            "wins":            wins,
            "losses":          losses,
            "win_rate":        win_rate,
            "avg_win":         avg_win,
            "avg_loss":        avg_loss,
            "risk_reward":     rr,
            "total_pnl_usd":   round(total_pnl_usd, 2),
            "bank_roi_pct":    bank_roi,
            "virtual_balance": balance,
            "banca_base":      BANCA,
            "best_symbol":     best_sym,
            "symbol_breakdown":symbol_stats,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao calcular stats do Swing Lab: {str(e)}")


@router.get("/swing/analytics")
async def get_swing_analytics():
    """Analytics detalhado do Swing Lab: distribuição de losses, top wins/losses."""
    try:
        trades = await database_service.get_swing_trades(active_only=False)
        MARGEM = 1.0

        closed_trades = [t for t in trades if t.status != "ACTIVE"]
        losses = [t for t in closed_trades if float(t.pnl_pct or 0) < 0]
        wins   = [t for t in closed_trades if float(t.pnl_pct or 0) > 0]

        # Distribuição de losses por hora UTC
        loss_by_hour = {str(h): 0 for h in range(24)}
        for t in losses:
            try:
                import datetime as _dt
                hr = str(_dt.datetime.utcfromtimestamp(t.opened_at).hour)
                loss_by_hour[hr] = loss_by_hour.get(hr, 0) + 1
            except Exception:
                pass

        # Top 5 wins/losses por ROI
        top_wins = sorted(wins, key=lambda t: float(t.pnl_pct or 0), reverse=True)[:5]
        top_losses = sorted(losses, key=lambda t: float(t.pnl_pct or 0))[:5]

        def fmt_trade(t):
            return {
                "symbol":   t.symbol,
                "direction":t.direction,
                "pnl_pct":  round(float(t.pnl_pct or 0), 2),
                "max_roi":  round(float(t.max_roi or 0), 2),
                "blitz_unit": getattr(t, "blitz_unit", 0),
                "blitz_score": getattr(t, "blitz_score", 0),
                "status":   t.status,
            }

        win_pnls  = [float(t.pnl_pct or 0) for t in wins]
        loss_pnls = [float(t.pnl_pct or 0) for t in losses]
        avg_win   = round(sum(win_pnls) / len(win_pnls), 2) if win_pnls else 0
        avg_loss  = round(sum(loss_pnls) / len(loss_pnls), 2) if loss_pnls else 0
        rr        = round(abs(avg_win / avg_loss), 2) if avg_loss != 0 else 0

        return {
            "total_analyzed": len(closed_trades),
            "risk_reward":    rr,
            "avg_win":        avg_win,
            "avg_loss":       avg_loss,
            "loss_by_hour":   loss_by_hour,
            "top_wins":       [fmt_trade(t) for t in top_wins],
            "top_losses":     [fmt_trade(t) for t in top_losses],
            "total_losses":   len(losses),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar analytics do Swing Lab: {str(e)}")


@router.post("/swing/clear")
async def clear_swing_trades():
    """Limpa todos os trades do Swing Lab."""
    try:
        success = await database_service.clear_swing_trades()
        return {"success": success, "message": "Swing Lab resetado com sucesso."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao limpar Swing Lab: {str(e)}")
