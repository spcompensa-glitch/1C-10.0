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
        total_pnl = 0.0
        strategy_stats = {}

        for t in trades:
            if t.status != "ACTIVE":
                # Se fechou com PnL positivo é win, senão é loss
                pnl = t.pnl_pct
                total_pnl += pnl
                if pnl > 0:
                    wins += 1
                else:
                    losses += 1
            else:
                total_pnl += t.pnl_pct

            # Agrupar estatísticas por estratégia
            strat = t.strategy or "UNKNOWN"
            if strat not in strategy_stats:
                strategy_stats[strat] = {"total": 0, "wins": 0, "losses": 0, "pnl": 0.0}
            
            strategy_stats[strat]["total"] += 1
            if t.status != "ACTIVE":
                if t.pnl_pct > 0:
                    strategy_stats[strat]["wins"] += 1
                else:
                    strategy_stats[strat]["losses"] += 1
                strategy_stats[strat]["pnl"] += t.pnl_pct

        win_rate = (wins / closed * 100.0) if closed > 0 else 0.0
        avg_pnl = (total_pnl / total) if total > 0 else 0.0

        # Encontrar melhor estratégia baseada em PnL total
        best_strategy = "N/A"
        best_pnl = -9999.0
        for strat, s_data in strategy_stats.items():
            if s_data["pnl"] > best_pnl:
                best_pnl = s_data["pnl"]
                best_strategy = strat

        return {
            "total_trades": total,
            "active_trades": active,
            "closed_trades": closed,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 2),
            "average_pnl": round(avg_pnl, 2),
            "total_pnl": round(total_pnl, 2),
            "best_strategy": best_strategy,
            "strategy_breakdown": strategy_stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar estatísticas do sandbox: {str(e)}")

@router.post("/clear")
async def clear_sandbox():
    try:
        success = await database_service.clear_sandbox_trades()
        return {"success": success, "message": "Sandbox resetado com sucesso."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao limpar sandbox: {str(e)}")
