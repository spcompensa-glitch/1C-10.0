# Anchored Summary — 1Crypten / 1C-10.0 (Trading System)

## Objective
- Fix two bugs in the deployed 1C-10.0 trading system (FastAPI + OKX):
  1. **[DONE]** Swing Lab (Sandbox) orders stuck: prices/ROI frozen in sandbox UI (`/sandbox`).
  2. **[DONE]** In OKX **PAPER** mode, the Sandbox consolidated balance (~$10,094.60) was NOT mirrored to the Cockpit "Net Worth"/Equity (desktop + mobile) — Cockpit showed ~$0.00 / fallback $100 instead. User rule: "o resultado da Banca do SandBoxx deve ser espelhada na Banca do Cockpit".

## Important Details
- System: 1Crypten 7.0 (deployed repo `1C-10.0`), FastAPI on OKX. Swing Lab + Scalping Lab forward-testing in sandbox. Architecture doc: `MASTER_ARCHITECTURE.md` (V124.7).
- `OKX_EXECUTION_MODE="PAPER"` (config.py:21, default). `OKX_SIMULATED_BALANCE=100.0` (config.py:22). `SWING_MARGIN_PER_TRADE=200.0` (config.py:170). `SWING_VIRTUAL_BALANCE=10000.0` (config.py:174).
- Sandbox consolidated balance source: `/api/sandbox/unified-state` returns `virtual_balance` = `BANCA_BASE(10000) + sum(pnl_pct/100 * margin)` over ACTIVE scalp ($200/trade) + ACTIVE swing ($200/trade). e.g. $10,094.60.
- Cockpit Net Worth = `liveEquity` (cockpit.html:6442-6449): `hasRealOkx = saldo_real_okx>0` → if true `saldo_real_okx + liveTotalPnL`, else `baseEquity(saldo_total) + liveTotalPnL`. `liveTotalPnL` = `lucro_total_acumulado + lucro_moonbag_acumulado` (~$0.03 in user screenshot).
- Cockpit `useBancaRT` (cockpit.html:1295) consumes `banca_status` Firebase/WS packet + `/api/banca/data` fallback.
- Sandbox UI has "Espelho (OKX)" toggle for mirroring swing orders to real account — separate concern from balance mirror.
- Remote: `https://github.com/spcompensa-glitch/1C-10.0.git` (origin, branch `main`). `ECC/` is a submodule (do NOT commit). `test_price.py` is dev's scratch test (do NOT commit).

## Work State
### Completed
- **Bug 1 — Swing frozen prices:** `backend/services/agents/flash_agent.py` had a local import `from services.database_service import database_service` at line 485 that shadowed the module-level import (line 20). Inside `_process_sandbox_swing_trade`, `database_service` was unbound at the price-update call (line 384) → `UnboundLocalError` every cycle, swallowed by `asyncio.gather` → `update_swing_trade` never ran → prices frozen. Removed the local import. Verified via simulation. Committed `560019f`, pushed (`99ed2e2..560019f`).
- **Bug 2 — Sandbox→Cockpit mirror in PAPER:** Root cause = in PAPER mode both `update_banca_status` (bankroll.py:1710) and `get_banca_data` (system.py:112) anchored `saldo_total`/`configured_balance` to `OKX_SIMULATED_BALANCE` (=100). Worse, in PAPER the code still queried the REAL OKX `/api/v5/account/balance` and set `saldo_real_okx` to the real balance (bankroll.py:1656), so the frontend took the `hasRealOkx` branch and ignored the simulated base entirely.
  - Added `DatabaseService.get_sandbox_unified_balance()` (database_service.py) replicating the unified-state calc (BANCA_BASE 10000 + ACTIVE scalp/swing pnl @ $200).
  - `update_banca_status` (bankroll.py): in PAPER sets `saldo_total`/`configured_balance`/`paper_equity` = sandbox unified balance; forces `saldo_real_okx = 0.0` so frontend flutua a banca base com o PnL do Sandbox; updated log line.
  - `get_banca_data` (system.py): in PAPER sets `saldo_total`/`configured_balance` = sandbox unified balance (with $100 fallback on error); still pops `saldo_real_okx`.
  - Verified `py_compile` on all 3 files. Committed `df3ebba`, pushed (`560019f..df3ebba`).

### Active
- (none)

### Blocked
- (none)

## Next Move
- Validate in production: Cockpit desktop + mobile "Net Worth" should now show ~$10,094.60 (sandbox balance) in PAPER mode. User should refresh `/sandbox` + Cockpit after deploy.
- If user wants the real OKX balance visible in PAPER too, that's a separate toggle (not requested).

## Relevant Files
- backend/services/database_service.py: added `get_sandbox_unified_balance()` (~line 1193); `get_sandbox_trades` (1080), `get_swing_trades` (1145).
- backend/services/bankroll.py: `update_banca_status` PAPER branch — sandbox_balance calc (~1700), `update_data` dict saldo_real_okx/saldo_total/configured_balance (~1709), log (~1730).
- backend/routes/system.py: `get_banca_data` PAPER branch (~109) now uses sandbox balance.
- backend/services/agents/flash_agent.py: line 485 local import removed (commit 560019f) — Bug 1 fix.
- backend/routes/sandbox.py: `/api/sandbox/unified-state` returns `virtual_balance` (46, 183, 623); swing mirror toggle (714).
- frontend/cockpit.html: Net Worth block 5951; `liveEquity`/`liveTotalPnL` calc 6442-6449; `useBancaRT` hook 1295.
- config.py: OKX_EXECUTION_MODE:21, OKX_SIMULATED_BALANCE:22, SWING_MARGIN_PER_TRADE:170, SWING_VIRTUAL_BALANCE:174.
- https://1crypten.space/sandbox and Cockpit pages (user-reported UI symptoms).
- https://github.com/spcompensa-glitch/1C-10.0.git (origin, main). Commits: 560019f (Bug1), df3ebba (Bug2).
