# Anchored Summary — 1Crypten / 1C-10.0 (Trading System)

## Objective
- Em PAPER, o Cockpit deve espelhar TODAS as ordens + a banca simulada do Sandbox (user rule). Em REAL, a OKX recebe scalping/swing do Sandbox e o Cockpit mostra as ordens da banca real.
- Bugs resolvidos nesta sessão (todos pushed para origin/main):
  1. Swing Lab (Sandbox) prices/ROI frozen.
  2. Cockpit "Net Worth" em PAPER mostrava ~$0/$100 → agora espelha saldo consolidado do Sandbox (~$10.138).
  3. Cockpit "Painel de Custódia" mostrava 0 posições em PAPER → agora espelha ordens ativas do Sandbox (Scalping + Swing).

## Important Details
- `OKX_EXECUTION_MODE="PAPER"` (config.py:21). `OKX_SIMULATED_BALANCE` (config.py:22) — no deploy parece ser 10000 (fallback do helper usava 10000). `SWING_MARGIN_PER_TRADE=200.0` (config.py:170).
- **Banca Simulada Consolidada** = `10000 + sum(pnl_pct/100 * 200)` sobre TODOS os trades (fechados+ativos) de scalp + swing. Fontes: `routes/sandbox.py:/unified-state` e `database_service.get_sandbox_unified_balance()` (devem bater).
- Cockpit lê `saldo_total` de `banca_status` (RTDB via `firebase_service.update_banca_status` + WS packet de `get_banca_status`).

## Work State
### Completed (commits)
- **560019f** Bug1: `flash_agent.py:485` local import shadowava `database_service` → UnboundLocalError → preços congelados. Removido.
- **df3ebba** Bug2: `bankroll.update_banca_status` + `system.get_banca_data` ancoravam saldo em OKX_SIMULATED_BALANCE e liam saldo REAL da OKX em PAPER. Adicionado `get_sandbox_unified_balance()`; em PAPER `saldo_total`/`configured_balance`/`paper_equity` = saldo do Sandbox e `saldo_real_okx=0`.
- **0ed0588** Bug2b: helper contava só ACTIVE; sandbox usa TODOS os trades. Corrigido (itera todos).
- **5debf3f** Bug3: `routes/trading.py` `_map_sandbox_trade_to_slot` + `GET /api/slots` e `main.py slots_broadcast_loop` mesclam ordens ativas do Sandbox (SCALPING/SWING) como slots em PAPER; fix `int(slot.id)` para ids string.
- **fadf427** Bug2c (RAIZ do saldo travado em 10000): 
  - `get_sandbox_unified_balance()` lançava/retornava 10000 porque lia `t.pnl_pct` de objetos ORM destacados (session fechada) → pnl 0. Agora converte ORM→dict via `_to_dict` (mesmo padrão do merge de ordens, que funciona) e lê `t.get("pnl_pct")`. Adicionado `logger.info` com valor calculado.
  - `database_service.get_banca_status` (LEITURA) FORÇAVA `saldo_total=100.0`/`configured_balance=100.0` em PAPER (linha 520-524) — sobrescrevia tudo. Removido; agora retorna o valor armazenado (definido pelo bankroll).
  - Testado com mock (dicts): retorna 10013.0 correto. Não dá para bater no Postgres de prod localmente.

### Active
- (none)

### Caveats conhecidos
- Header "Slots X/20" e `available_slots_count` ainda refletem slots reais (0 em PAPER), não o count do Sandbox. Painel de Custódia (posições) já espelha.
- `routes/trading.py:320` zera saldo para 100.0 só no endpoint manual de `nuclear_reset`/cleanup — não é hot path.

## Next Move
- Validar em produção: Cockpit desktop+mobile deve mostrar Net Worth ~$10.138 e as ordens do Sandbox no Painel de Custódia. Se ainda vier 10000, checar logs do servidor pela linha `[V127] Sandbox unified balance = ...` (confirma valor calculado) ou `[V127] Erro ao calcular...` (exception com traceback).
- Opcional: espelhar count de slots no header "Slots X/20" (ajustar `update_banca_status` para somar active sandbox).

## Relevant Files
- backend/services/database_service.py: `get_sandbox_unified_balance` (~1193) + `_to_dict` helper; `get_banca_status` (~515, removeu force-100); `update_banca_status` (~500, grava Postgres).
- backend/services/bankroll.py: `update_banca_status` PAPER (~1700) seta saldo_total=sandbox_balance, saldo_real_okx=0.
- backend/routes/system.py: `get_banca_data` PAPER (~109) usa sandbox balance.
- backend/routes/trading.py: `_map_sandbox_trade_to_slot`; `get_slots` merge PAPER; fix int(id).
- backend/main.py: `slots_broadcast_loop` merge PAPER (~565).
- backend/services/firebase_service.py: `update_banca_status` (230) grava Firestore+RTDB `banca_status`.
- backend/routes/sandbox.py: `/unified-state` (8) — fonte do virtual_balance.
- frontend/cockpit.html: `useSlotsRT` (1519), `Painel de Custódia` (5912/6620), `liveEquity` (6442-6449).
- Remote main = fadf427. Commits: 560019f, df3ebba, 0ed0588, 5debf3f, fadf427.
