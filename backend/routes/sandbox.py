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
                "created_at": t.created_at.isoformat() if t.created_at else None
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
        total_pnl_usd = 0.0  # Lucro acumulado em dólares com base em $2 de margem por trade
        strategy_stats = {}

        for t in trades:
            # PnL USD de cada trade: (ROI / 100) * $2.00 de margem
            trade_pnl_usd = (t.pnl_pct / 100.0) * 2.0
            
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

        # ROI da banca de $100.00: (total_pnl_usd / 100.0) * 100 = total_pnl_usd
        bank_pnl_percent = total_pnl_usd

        win_rate = (wins / closed * 100.0) if closed > 0 else 0.0
        avg_pnl = (bank_pnl_percent / total) if total > 0 else 0.0

        # Para cada estratégia, converter pnl_usd para o ROI equivalente da banca
        for strat in strategy_stats:
            strategy_stats[strat]["pnl"] = strategy_stats[strat]["pnl_usd"]

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
            from services.agents.captain import captain
            if hasattr(captain, 'btc_market_regime'):
                current_regime = captain.btc_market_regime.get("direction", "NEUTRAL")
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
            phase = state.get("fase", "DESCONHECIDA")
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

@router.post("/clear")
async def clear_sandbox():
    try:
        success = await database_service.clear_sandbox_trades()
        return {"success": success, "message": "Sandbox resetado com sucesso."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao limpar sandbox: {str(e)}")

