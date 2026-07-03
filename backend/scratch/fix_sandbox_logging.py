#!/usr/bin/env python3
"""
FIX 2 & 3: 
2. Add detailed logging on VELOCITY FLOW losses in sandbox_service.py
3. Create sandbox analytics endpoint in routes/sandbox.py
"""
import os

# ═══════════════════════════════════════════════════════
# FIX 2: Add detailed loss logging in sandbox_service.py
# ═══════════════════════════════════════════════════════
sandbox_path = os.path.join(os.path.dirname(__file__), '..', 'services', 'sandbox_service.py')

with open(sandbox_path, 'r', encoding='utf-8') as f:
    content = f.read()

changes2 = 0

# Add loss logging after status is set to CLOSED_SL or CLOSED_TRAILING
old_log = '''                        if status == "CLOSED_TRAILING":
                            history.append(f"[TRAILING] Stop atingido em {current_price} — fechado lucrativo com +{final_pnl:.1f}% ROI")
                        else:
                            history.append(f"Stop atingido em {current_price} (SL configurado em {stop_price})")

                    await database_service.update_sandbox_trade(trade.id, update_payload)'''

new_log = '''                        if status == "CLOSED_TRAILING":
                            history.append(f"[TRAILING] Stop atingido em {current_price} — fechado lucrativo com +{final_pnl:.1f}% ROI")
                        else:
                            history.append(f"Stop atingido em {current_price} (SL configurado em {stop_price})")
                            # [FIX-LOSS-LOG] Log detalhado de trades com loss para análise de padrões
                            loss_regime = "TRENDING" if not is_ranging else "LATERAL"
                            from datetime import datetime, timezone
                            loss_hour_utc = datetime.now(timezone.utc).hour
                            logger.warning(
                                f"📊 [SANDBOX-LOSS] {trade.symbol} | Strategy={trade.strategy} | "
                                f"Dir={trade.direction} | Entry={trade.entry_price:.4f} | "
                                f"Exit={exit_price:.4f} | ROI={final_pnl:.1f}% | "
                                f"StopROI={updated_stop_roi:.0f}% | Regime={loss_regime} | "
                                f"HourUTC={loss_hour_utc} | MaxROI={max_roi:.1f}%"
                            )

                    await database_service.update_sandbox_trade(trade.id, update_payload)'''

if old_log in content:
    content = content.replace(old_log, new_log, 1)
    changes2 += 1
    print(f'[OK] Fix 2 applied: Detailed loss logging added to sandbox_service.py')
else:
    print(f'[SKIP] Fix 2: pattern not found (checking alternative)')
    # Try alternative pattern
    alt_old = 'history.append(f"Stop atingido em {current_price} (SL configurado em {stop_price})")\n\n                    await database_service.update_sandbox_trade'
    if alt_old in content:
        alt_new = '''history.append(f"Stop atingido em {current_price} (SL configurado em {stop_price})")
                            # [FIX-LOSS-LOG] Log detalhado de trades com loss para analise de padroes
                            loss_regime = "TRENDING" if not is_ranging else "LATERAL"
                            from datetime import datetime, timezone
                            loss_hour_utc = datetime.now(timezone.utc).hour
                            logger.warning(
                                f"📊 [SANDBOX-LOSS] {trade.symbol} | Strategy={trade.strategy} | "
                                f"Dir={trade.direction} | Entry={trade.entry_price:.4f} | "
                                f"Exit={exit_price:.4f} | ROI={final_pnl:.1f}% | "
                                f"StopROI={updated_stop_roi:.0f}% | Regime={loss_regime} | "
                                f"HourUTC={loss_hour_utc} | MaxROI={max_roi:.1f}%"
                            )

                    await database_service.update_sandbox_trade'''
        content = content.replace(alt_old, alt_new, 1)
        changes2 += 1
        print(f'[OK] Fix 2 applied (alt pattern): Detailed loss logging added')

with open(sandbox_path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f'Fix 2 total: {changes2} changes')

# ═══════════════════════════════════════════════════════
# FIX 3: Create sandbox analytics endpoint
# ═══════════════════════════════════════════════════════
routes_path = os.path.join(os.path.dirname(__file__), '..', 'routes', 'sandbox.py')

with open(routes_path, 'r', encoding='utf-8') as f:
    routes_content = f.read()

changes3 = 0

# Add analytics endpoint before the clear endpoint
analytics_endpoint = '''
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
            # Trades com stop em -20% eram LATERAL, -40% eram TRENDING
            stop_roi = state.get("stop_roi", -40.0)
            if stop_roi >= -25.0:
                return "LATERAL"
            return "TRENDING"
        
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
            if hour not in loss_by_hour:
                loss_by_hour[hour] = {"count": 0, "total_roi": 0, "avg_roi": 0}
            loss_by_hour[hour]["count"] += 1
            loss_by_hour[hour]["total_roi"] += t.pnl_pct
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
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar analytics: {str(e)}")

'''

# Insert before the clear endpoint
clear_marker = '@router.post("/clear")'
if clear_marker in routes_content and '/analytics' not in routes_content:
    routes_content = routes_content.replace(clear_marker, analytics_endpoint + '\n' + clear_marker, 1)
    changes3 += 1
    print(f'[OK] Fix 3 applied: Analytics endpoint added to routes/sandbox.py')
else:
    print(f'[SKIP] Fix 3: marker not found or already applied')

with open(routes_path, 'w', encoding='utf-8') as f:
    f.write(routes_content)

print(f'Fix 3 total: {changes3} changes')
print(f'\nAll fixes complete: Fix2={changes2}, Fix3={changes3}')
