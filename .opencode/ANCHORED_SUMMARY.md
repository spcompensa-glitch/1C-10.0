# Anchored Summary — 1Crypten / 1C-10.0 (Trading System)

## Objective
- Fix bugs in deployed 1C-10.0 (FastAPI + OKX) so the **Cockpit mirrors the Sandbox** in PAPER mode:
  1. **[DONE]** Swing Lab (Sandbox) prices/ROI frozen in `/sandbox` UI.
  2. **[DONE]** Cockpit "Net Worth" in PAPER showed ~$0/$100 — now mirrors Sandbox consolidated balance (~$10,094).
  3. **[DONE]** Cockpit "Painel de Custódia" showed 0 positions in PAPER — now mirrors Sandbox active Scalping + Swing orders as slots (via REST `/api/slots` + WS `live_slots`).
- User rule: "Em PAPER o Cockpit deve representar TODAS as ordens + a banca simulada do Sandbox. Em REAL, a OKX recebe scalping/swing do Sandbox e o Cockpit representa as ordens da banca real da OKX."

## Important Details
- System: 1Crypten 7.0 (repo `1C-10.0`), FastAPI on OKX. Swing Lab + Scalping Lab forward-testing. Doc: `MASTER_ARCHITECTURE.md`.
- `OKX_EXECUTION_MODE="PAPER"` (config.py:21, default). `OKX_SIMULATED_BALANCE=100.0` (config.py:22). `SWING_MARGIN_PER_TRADE=200.0` (config.py:170). `SWING_VIRTUAL_BALANCE=10000.0` (config.py:174).
- **Sandbox consolidated balance** = `BANCA_BASE(10000) + sum(pnl_pct/100 * margin)` over ALL (closed+active) scalp ($200/trade) + swing ($200/trade). Computed in `routes/sandbox.py:/unified-state` (lines 20-38) and now duplicated in `database_service.get_sandbox_unified_balance()`.
- **Cockpit positions**: `useSlotsRT` (cockpit.html:1519) → `GET /api/slots` (poll 30s) + WS `live_slots` packet (broadcast a cada 5s em main.py `slots_broadcast_loop`). Rendered in "Painel de Custódia" (cockpit.html:5912/6620) using `slots.filter(s=>s.symbol && entry_price>0)`.
- Remote: `https://github.com/spcompensa-glitch/1C-10.0.git` (origin, branch `main`). `ECC/` = submodule (NÃO commitar). `test_price.py` = scratch dev test (NÃO commitar).

## Work State
### Completed (commits pushed to origin/main)
- **Bug1 — Swing frozen prices** (`560019f`): `flash_agent.py:485` local import shadowed module-level `database_service` → `UnboundLocalError` every cycle → prices frozen. Removed local import.
- **Bug2 — PAPER balance mirror** (`df3ebba`): `update_banca_status` (bankroll.py) + `get_banca_data` (system.py) anchored `saldo_total`/`configured_balance` to `OKX_SIMULATED_BALANCE` (100) and even queried REAL OKX balance into `saldo_real_okx`, making frontend take `hasRealOkx` branch. Fix: added `database_service.get_sandbox_unified_balance()`; in PAPER set `saldo_total`/`configured_balance`/`paper_equity` = sandbox balance and force `saldo_real_okx=0`.
- **Bug2b — all-trades count** (`0ed0588`): helper initialmente só contava trades ACTIVE; sandbox balance vem de TODOS os trades (fechados+ativos). Corrigido para iterar sobre todos. Cockpit agora mostra ~$10.094,63.
- **Bug3 — PAPER orders mirror** (`5debf3f`):
  - `routes/trading.py`: added `_map_sandbox_trade_to_slot(trade, lab_type)`; `GET /api/slots` now appends active Sandbox scalp ("SCALPING") + swing ("SWING") trades as slot-like dicts in PAPER; fixed `int(slot.get("id"))` crash (sandbox ids são strings) com try/except.
  - `main.py` `slots_broadcast_loop`: in PAPER appends Sandbox trades to the `live_slots` WS broadcast (atualiza posições ao vivo a cada 5s). Uses `settings.OKX_EXECUTION_MODE`.
  - Projection/live PnL: `/api/slots` já roda `build_projection` + `get_sl_phase_info` por slot (live price da OKX), então pnl das ordens do Sandbox atualiza a cada 30s (poll) e o WS mantém symbol/entry.

### Active
- (none)

### Blocked / Known caveats
- Cockpit header "Slots X/20" e `available_slots_count` continuam refletindo slots reais (0 em PAPER), não o count do Sandbox. O Painel de Custódia (posições) já espelha. Se o usuário quiser o header também, ajustar `update_banca_status` para somar active sandbox.
- "Espelho (OKX)" na UI do Sandbox = mirror de ordens swing para conta real (SWING_MIRROR_MODE). Separado do balance/orders mirror do Cockpit em PAPER.

## Next Move
- Validar em produção: Cockpit desktop+mobile deve mostrar ~$10.094,63 e as ordens ativas do Sandbox no Painel de Custódia.
- Opcional: espelhar count de slots no header "Slots X/20".

## Relevant Files
- backend/services/database_service.py: `get_sandbox_unified_balance()` (~1193); `get_sandbox_trades` (1080), `get_swing_trades` (1145); modelos `SandboxTrade` (114), `SandboxSwingTrade` (137).
- backend/services/bankroll.py: `update_banca_status` PAPER branch — sandbox_balance (~1700), `update_data` dict (~1716), `saldo_real_okx` forçado 0 em PAPER.
- backend/routes/system.py: `get_banca_data` PAPER (~109) usa sandbox balance.
- backend/routes/trading.py: `_map_sandbox_trade_to_slot` (antes de get_slots), `get_slots` merge PAPER (~80), fix int(id) (~106).
- backend/main.py: `slots_broadcast_loop` merge PAPER (~565).
- backend/routes/sandbox.py: `/unified-state` (8) — fonte do virtual_balance.
- frontend/cockpit.html: `useSlotsRT` (1519), `Painel de Custódia` (5912/6620), `liveEquity` (6442-6449).
- config.py: OKX_EXECUTION_MODE:21, OKX_SIMULATED_BALANCE:22, SWING_MARGIN_PER_TRADE:170.
- Remote commits: 560019f (Bug1), df3ebba (Bug2), 0ed0588 (Bug2b), 5debf3f (Bug3). main = 5debf3f.
