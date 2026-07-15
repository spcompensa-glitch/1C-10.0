# Anchored Summary — 1Crypten / 1C-10.0 (Trading System)

## Objective
- Em PAPER, o Cockpit deve espelhar TODAS as ordens + a banca simulada do Sandbox. Em REAL, a OKX recebe scalping/swing do Sandbox e o Cockpit mostra as ordens da banca real.

## Root Cause FINAL (saldo travado em $10000.03)
- O Cockpit calcula `liveEquity` (cockpit.html:6442-6449) como:
  `hasRealOkx ? saldo_real_okx : (hasGuardianEquity ? guardianEquity : baseEquity + liveTotalPnL)`
  onde `baseEquity` vem de `banca.saldo_total`.
- `hasGuardianEquity = guardianReport?.equity > 0`. O `guardianReport` vem de `bankroll_guardian.evaluate_bank_health()`, que EM PAPER forçava `sim_balance = OKX_SIMULATED_BALANCE` (~10000) e `banca["saldo_real_okx"]=sim_balance`, e calculava `equity` a partir disso. Logo `guardianEquity ≈ 10000` e SOBREPUNHA o `saldo_total` — por isso todas as fixas em `saldo_total`/`configured_balance` eram ignoradas pelo Net Worth.
- Adicional: `get_sandbox_unified_balance()` lia `t.pnl_pct` de ORM destacado (session fechada) → PnL 0 → saldo 10000. Tornou-se bulletproof com SQL aggregation (SUM).

## Work State
### Completed (commits em origin/main)
- **560019f** Swing Lab preços congelados (flash_agent local import).
- **df3ebba / 0ed0588 / 5debf3f** espelho de saldo (saldo_total/configured_balance=Sandbox, saldo_real_okx=0) + ordens (slots/swing como slots no /api/slots e WS live_slots).
- **fadf427** helper convertia ORM→dict (não resolveu) + removeu force-100 em get_banca_status.
- **73c876c** (FINAL): 
  - `bankroll_guardian.evaluate_bank_health` PAPER: `sim_balance = get_sandbox_unified_balance()` (não OKX_SIMULATED_BALANCE). Isso define `equity` (usado como Net Worth) E `saldo_real_okx` = saldo do Sandbox. Agora o Cockpit mostra o saldo consolidado do Sandbox (~$10.138).
  - `get_sandbox_unified_balance` reescrito com `SELECT SUM(pnl_pct)` (SQL agregado, sem acesso a atributo ORM) — bulletproof. Logger info com valor.

### Active
- (none)

### Caveats
- Header "Slots X/20" / `available_slots_count` ainda refletem slots reais (0 em PAPER).
- Deploy: o usuário precisa puxar/restart o commit 73c876c (não o fadf427).

## Next Move
- Redeploy 73c876c. Cockpit Net Worth deve mostrar ~$10.138,46 (igual à Banca Simulada Consolidada do Sandbox).
- Se ainda vier 10000, checar logs por `[V127] Sandbox unified balance = ...` e `/bankroll/guardian-report` (campo equity).

## Relevant Files
- backend/services/database_service.py: `get_sandbox_unified_balance` (SQL SUM, ~1193).
- backend/services/agents/bankroll_guardian.py: `evaluate_bank_health` PAPER (~598) usa saldo do Sandbox.
- backend/services/bankroll.py: `update_banca_status` seta saldo_total=sandbox em PAPER.
- backend/routes/system.py: `get_banca_data` PAPER usa sandbox; `/bankroll/guardian-report` (138).
- backend/routes/trading.py + backend/main.py: espelho de ordens em PAPER.
- frontend/cockpit.html: `liveEquity` (6442-6449) usa guardianEquity.
- Remote main = 73c876c. Commits: 560019f, df3ebba, 0ed0588, 5debf3f, fadf427, 73c876c.
