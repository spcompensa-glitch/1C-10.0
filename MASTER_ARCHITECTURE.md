# MASTER_ARCHITECTURE.md — 1Crypten 7.0

Fonte unica de verdade arquitetural. Extraido diretamente do codigo-fonte (nao de historico de versoes).
Este e o unico documento de arquitetura do projeto — o Hermes le os primeiros ~8000 caracteres deste arquivo em cada resposta (`hermes_agent.py:_load_architecture_context`), portanto os fatos mais criticos ficam no topo.

*Verificado contra o codigo em 2026-07-13. VERSION no codigo: `backend/main.py` VERSION="V124.7" / DEPLOYMENT_ID="V124.7_M30_SWING". Refinamentos [V127] (espelho PAPER Sandbox→Cockpit: saldo + ordens) aplicados sobre o V124.7 — ver Secao 8.6.*

---

## 1. Visao Geral

1Crypten e um sistema de trading automatizado para criptomoedas na OKX. Roda um app FastAPI unico (`backend.main:app`) que executa em paralelo o motor real e tres laboratorios de forward-testing (Sandbox, Swing Lab, Scalping Lab).

- **Entry point (unico)**: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT` (Procfile / railway.json / Dockerfile). **Nao existe `main.py` na raiz.**
- **Backend**: FastAPI (Python 3.12-slim)
- **Frontend**: HTML/JS standalone (`frontend/cockpit.html`, `sandbox.html`, `hermes-chat.html`, `memory_galaxy.html`)
- **Exchange**: OKX (SWAP / Portfolio Margin). Modo `PAPER` (simulado) ou `REAL`, via `OKX_EXECUTION_MODE`.
- **[V127] Semantica PAPER vs REAL (espelho do Cockpit)**: Em **PAPER**, o Cockpit (`cockpit.html`) representa o **Sandbox** — tanto o *Net Worth* (Banca Simulada Consolidada) quanto o *Painel de Custodia* (ordens ativas do Scalping Lab + Swing Lab). Em **REAL**, a OKX recebe as ordens scalping/swing do Sandbox (via `SWING_MIRROR_MODE`/espelhamento) e o Cockpit representa a banca real da OKX. Ver Secao 8.6.
- **Plataforma**: Railway + Docker
- **Persistencia**: PostgreSQL (SSOT) + Firebase (Firestore/RTDB) + SQLite (cache de klines)

---

## 2. Constantes Principais (fonte: `backend/config.py`)

| Constante | Valor | Fonte |
|-----------|-------|-------|
| `LEVERAGE` (padrao) | 50x | `config.py:133` |
| `MAX_SLOTS` (cap global) | 20 | `config.py:124` |
| `MAX_SLOTS_LATERAL` | 16 | `config.py:125` |
| `MAX_SLOTS_TRENDING` | 16 | `config.py:126` |
| `MARGIN_PER_TRADE_LATERAL` | $0.50 | `config.py:130` |
| `MARGIN_PER_TRADE_TRENDING` | $0.50 | `config.py:131` |
| `RISK_CAP_PERCENT` | 0.40 (40% da banca) | `config.py:132` |
| `MAX_INITIAL_STOP_ROI` (teto stop inicial) | 30% ROI | `config.py:148` |
| `RISK_ZERO_TRIGGER_ROI` / `RISK_ZERO_STOP_TARGET` | 50% → +25% (SSOT) | `config.py:128-129` |
| `ADX_MIN_ENTRY` | 22 | `config.py:142` |
| `ADX_TRENDING_THRESHOLD` | 25 | `config.py:144` |
| `ADX_STRONG_TREND_THRESHOLD` | 30 | `config.py:146` |
| `OKX_SIMULATED_BALANCE` | $100 (padrao) | `config.py:22` |
| `DECOR_HUNTER_MAX_SLOTS` / `MIN_CONFIDENCE` / `SCAN_INTERVAL` | 8 / 70 / 30s | `config.py:152-156` |

**Swing Lab (`config.py:164-181`)**: `SWING_LEVERAGE`=50x, `SWING_MARGIN_PER_TRADE`=$200, `SWING_VIRTUAL_BALANCE`=$10.000, `SWING_SCAN_INTERVAL`=300s, `SWING_MIRROR_MODE`=OFF, `SWING_STOP_ROI`=15.0 (stop inicial -15% ROI = 0.3% preco com 50x).

> **[V127] Saldo exibido em PAPER**: `OKX_SIMULATED_BALANCE` e a base do Guardiao/sizing em PAPER, mas o *Net Worth* do Cockpit em PAPER NAO e `OKX_SIMULATED_BALANCE` — e a **Banca Simulada Consolidada do Sandbox** (`get_sandbox_unified_balance`, `database_service.py`: `BANCA_BASE` $10.000 + Σ(pnl_pct/100 × $200) sobre TODOS os trades Scalp+Swing). Ver Secao 8.6.

> Nota: `bankroll.py` le `settings.MARGIN_PER_TRADE_*` (0.50) e `settings.MAX_SLOTS_*` (16). Comentarios legados em `bankroll.py` citam "$2.00/$1.00" e "20/40" — esses valores NAO refletem o config atual.

---

## 3. Escadinha de Stops (fonte: `backend/services/order_projection_service.py`)

Existem **5** escadas. A selecao e feita em `get_stop_ladder(roi, is_ranging, slot_type, strategy_class)`:
- `is_swing` = `slot_type` in (BLITZ_30M, SWING) **ou** `strategy_class` in (VELOCITY FLOW, ALPHA SHIELD, DECOR SHADOW)
- `is_scalping` = `strategy_class`=="VWAP SNIPER" **ou** `slot_type`=="SCALPING"
- Roteamento: swing+ranging→`SWING_LATERAL` · swing→`SWING` · scalping→`SCALPING` · ranging→`RANGING` · senao→`TRENDING`.

### 3.1 `ORDER_STOP_LADDER_RANGING` (lateral scalping padrao)
| Gatilho ROI | Stop ROI | Nome | Status |
|---|---|---|---|
| 8% | 2% | GARANTIA_TAXAS | RISCO_ZERO |
| 12% | 5% | GARANTIA_LUCRO_CURTO | RISCO_ZERO |
| 20% | 10% | GARANTIA_LUCRO_MEDIO | RISCO_ZERO |
| 32% | 18% | GARANTIA_LUCRO_ALTO | RISCO_ZERO |
| 50% | 48% | ALVO_MAXIMO_LATERAL | PROFIT_LOCK |
Acima de 20% ROI em ranging, a escada sobe dinamicamente de 1% em 1% (trailing gap 5%, ou 10% se `slot_type=BLITZ_30M`).

### 3.2 `ORDER_STOP_LADDER_SCALPING` (VWAP SNIPER)
| Gatilho | Stop | Nome |
|---|---|---|
| 4% | 1.5% | GARANTIA_TAXAS_SCALP |
| 6.5% | 3.5% | LUCRO_CURTO_SCALP |
| 10% | 6% | LUCRO_MEDIO_SCALP |
| 15% | 11% | TRAILING_SCALP |

### 3.3 `ORDER_STOP_LADDER_SWING` (swing tendencia)
2/0 (BREAKEVEN), 60/30 (PRE_UNIT1), 100/80 (UNIT1_GARANTIDO), 150/110 (EMANCIPADO), 200/170 (UNIT2), 300/250 (UNIT3).

### 3.4 `ORDER_STOP_LADDER_SWING_LATERAL` (swing em lateral)
5/1.5 (BREAKEVEN_LATERAL), 15/5 (PRE_UNIT1_LATERAL), 30/15 (UNIT1_GARANTIDO), 60/30 (EMANCIPADO_LATERAL), 100/80 (TRAILING_LATERAL).

### 3.5 `ORDER_STOP_LADDER_TRENDING` (tendencia)
14/2, 25/10, 40/20, 60/40, 80/60, 100/80, 130/110, 150/110, 200/150, 300/220, 400/280, 500/350, 600/420, 700/500, 750/600, 800/650, 1000/800, 1200/1000.
Acima de 1200% ROI (APEX): niveis `ULTRA_*` a cada +200% ROI, stop = gatilho − 200%.

`ORDER_STOP_LADDER` (sem sufixo) e um alias de `TRENDING` para compatibilidade com o compliance do Hermes.

---

## 4. Fluxo de Execucao

```
Sinal (SignalGenerator / DECOR_HUNTER / Swing Lab / Scalping Lab)
    v
CaptainAgent (captain.py) — Quality gate + regime gating + consenso de frota
    | Consenso: Macro 15% + Whale 25% + SMC 30% + OnChain 30%
    | Quartermaster classifica o wick -> leverage
    v
BankrollGuardian (bankroll_guardian.py) — autorizacao
    | Regime gating por ADX + limites de slots + memoria por par
    v
Bankroll (bankroll.py) — execucao
    | Stop inicial adaptativo (teto 30% ROI) + ExecutionCapacityGate + OKXCommandQueue (anti-429)
    v
FlashAgent (flash_agent.py) — gestao de stops, ciclo 1s (escadinha)
    v
FleetAudit (fleet_audit.py) — reconciliacao 20s, Early ROI Panic, ghost cleanup
```

---

## 5. Filtro de Regime de Mercado (OracleAgent)

- Grade ADX: `< 25` = LATERAL (RANGING); `>= 25` = TENDENCIA (TRENDING). Estabilizacao 150s.
- DECOR SHADOW opera **apenas em LATERAL** (estrategia de reversao/exaustao).
- ALPHA SHIELD e VELOCITY FLOW operam em qualquer regime.
- BLITZ / Swing 30M (`slot_type=BLITZ_30M` ou `is_blitz=True`) faz bypass do gating em LATERAL (`captain.py`).
- Direcao BTC: confluencia var 15m + 1h. Trend bias: BTC vs SMA 200 diaria (bearish→so SHORT; bullish→so LONG).

---

## 6. Estrategias

| Estrategia | Regime | Descricao |
|---|---|---|
| VELOCITY FLOW | Qualquer / BLITZ | Momentum, SMA8/21 alinhado + volume |
| ALPHA SHIELD | Qualquer / BLITZ | Protecao de capital: DVAP/MOLA/FAS/LRT |
| DECOR SHADOW | LATERAL / BLITZ | Reversao de exaustao, decorrelacao BTC (Pearson) |
| DECOR_HUNTER | LATERAL | Caca a pares desgrudados do BTC (watchlist propria) |
| VWAP SNIPER | Scalping (M1/M5) | EMA200 M5 + toque no VWAP diario + Stoch RSI |
| LRT / DVAP / FAS / MOLA | Qualquer | Liquidez / exaustao / funding squeeze / breakout |

Swing 30M usa `SignalGenerator.analyze_m30_swing()` (reusa DVAP/MOLA/FAS/LRT + TREND + DECOR). O antigo `blitz_sniper.py` foi **removido** (V125.3).

---

## 7. Stack de Agentes / Servicos (`backend/services/agents/` + `backend/services/`)

### 7.1 Decisao & risco
- **CaptainAgent** (`agents/captain.py`) — despachante, quality gate, consenso de frota.
- **OracleAgent** (`agents/oracle_agent.py`) — regime de mercado (ADX), estabilizacao 150s.
- **FlashAgent** (`agents/flash_agent.py`) — motor da escadinha, ciclo 1s.
- **BankrollGuardian** (`agents/bankroll_guardian.py`) — autorizacao de trade. **[V127]** Em PAPER, `evaluate_bank_health` fonteia `equity`/`saldo_real_okx` a partir da **Banca Simulada Consolidada do Sandbox** (`get_sandbox_unified_balance`) — e esse `equity` e o *Net Worth* exibido no Cockpit em PAPER (ver Secao 8.6). Em REAL, `equity` vem do saldo real da OKX.
- **SlotOperator** (`agents/slot_operator.py`) — observador/failsafe, ciclo 3s.
- **Bankroll** (`services/bankroll.py`) — abertura/gestao de posicao real.

### 7.2 Sinal
- **SandboxSwingService** (`services/sandbox_swing_service.py`) — motor Swing Lab M30 (scan 5min, Zero-Risk Stacking cap 2, 15 slots total).
- **SandboxScalpingEngine** (`services/sandbox_scalping_engine.py`) — motor Scalping Lab (VWAP SNIPER, scan 60s).
- **SignalGenerator** (`services/signal_generator.py`) — motor principal de estrategias.
- **AmbushAgent** (`agents/ambush.py`) — entrada Fibonacci (timeout 30min).
- **WhaleTracker** (`agents/whale_tracker.py`) — fluxo institucional CVD/OI (whale pulse >= 150k).
- **OnChainWhaleWatcher** (`agents/onchain_whale_watcher.py`) — hot wallets (>$500k USDT / 200 ETH).

### 7.3 Analise
- **MacroAnalyst** (`agents/macro_analyst.py`) — risco macro BTC (Pearson panic >0.8 + BTC <-2%).
- **Librarian** (`agents/librarian.py`) — DNA do ativo/rankings (ciclo 2h).
- **LibrarianAuditor** (`agents/librarian_auditor.py`) — ajuste de bias (ciclo 4h, range 0.5–1.2).
- **TradeAnalyst** (`agents/trade_analyst.py`) — autopsia pos-trade (ciclo 30min).
- **SentimentSpecialist** (`agents/sentiment_specialist.py`) — LS-Ratio + Funding (sem LLM).

### 7.4 Infra
- **FleetAudit** (`agents/fleet_audit.py`) — reconciliacao 20s, Early ROI Panic (-80% em <300s).
- **Quartermaster** (`agents/quartermaster.py`) — leverage por wick: SMOOTH(<0.45,50x) / JUMPY(0.45–0.70,20x) / EXTREME(>0.70,10x).
- **HermesAgent** (`agents/hermes_agent.py`) — compliance/telemetria/chat; le este arquivo + `vault_galaxy/`.
- **JarvisBrain** (`agents/jarvis_brain.py`) — chat multi-dimensao (10 dimensoes).
- **AIService** (`agents/ai_service.py`) — cascade DeepSeek → Gemini → OpenRouter.
- **ExecutionAuditorAgent** (`agents/execution_auditor.py`) — sentinel de execucao: sanitiza chaves de preco, valida contratos OKX, forca leverage, alerta no Firebase.
- **PhaseDetector** (`services/phase_detector.py`) — deteccao de Fase 1 (acumulacao) e Fase 2 (compressao) para antecipar explosoes.
- **PortfolioGuardian** (`services/portfolio_guardian.py`), **SentinelAuditor** (`services/sentinel_auditor.py`) — iniciados no startup.

Iniciados no startup (`backend/main.py`): phase_detector, okx_ws_public/service, fleet_audit, hermes_agent, signal_generator (loops), captain, flash_agent, librarian, trade_analyst, portfolio_guardian, sentinel_auditor, sandbox_service, sandbox_swing_service, sandbox_scalping_engine.

---

## 8. Laboratorios de Forward-Testing

### 8.1 SandboxService (`services/sandbox_service.py`) — ciclo 1s
- Espelha o sistema real. Recebe sinais via `on_radar_pulse` → `_process_radar_signals`.
- Stop adaptativo por regime (fallback): LATERAL -8% ROI / TRENDING -10% ROI; capping -10%.
- Margem adaptativa por win rate do par: $1.00–$2.50 (`_get_adaptive_margin`).
- Cooldown pos stop-out **por (simbolo, direcao)**: **1800s** no 1o stop, **3600s** em stops consecutivos (>=2) — `sandbox_service.py:735`.
- Cooldown de transicao fria (tendencia→lateral): **900s** (`:551`).
- Confirmacao 5M (2/3 candles alinhados), Entry Sanity Check (70% do stop), auto-blocklist (PnL<-15% E WR<35% apos 3+ trades).
- Espelhamento real (V124.4): se `OKX_API_KEY_MASTER` + modo REAL, replica ordens; auditado pelo ExecutionAuditorAgent.

### 8.2 Scalping Lab — VWAP SNIPER (`services/sandbox_scalping_engine.py`)
- Scan 60s. Filtro tendencia EMA200 (M5); gatilho toque VWAP diario (M1, tol 0.15%); Stoch RSI (<25 LONG / >75 SHORT).
- Filtro ATR minimo **0.02%** do preco; Liquidity Sweep = +15 score; **score minimo 70** (V126).
- **Watchlist independente** (V128): `SCALPING_WATCHLIST` (20 pares) — separada da blocklist do Swing, pares bloqueados por Swing nao afetam Scalping.
- Banca $10.000, margem $200/trade, 50x isolada, **sem saidas parciais**. Stop = 1.0x ATR, teto -20% ROI.

### 8.3 Swing Lab — M30 (`services/sandbox_swing_service.py`)
- Scan a cada 5min no M30 via `SignalGenerator.analyze_m30_swing()`.
- Banca $10.000, margem $200/trade, 50x.
- **Stop inicial -15% ROI** (`SWING_STOP_ROI=15.0`): `stop_price = entry × (1 - 0.15/50) = entry × 0.997` (0.3% de oscilacao do preco).
- **Breakeven +4% ROI** (V128): protecao mais cedo, stop em 0% quando trade atinge +4% ROI.
- **Filtro de regime** (V128): bearish → so opera SHORT; bullish → so LONG.
- **Filtro de horario** (V128): pausa 14:00-15:00 UTC (pico de losses historico).
- **Blacklist dinamica** (V128): auto-bloqueio apos 3+ trades com WR<20%.
- **Confirmação 5m breakout** (`_get_5m_breakout_score`): filtro SOFT — retorna bonus de score (+10 ambos OK, +5 parcial, 0 nenhum).
- **Zero-Risk Stacking (cap 2)**: no maximo 2 posicoes com risco de mesa (SL abaixo da entrada). Novas entradas so quando uma existente vai a break-even (`sandbox_swing_service.py:170-182`).
- **UI Swing Table (V127)**: 22 colunas com score bar colorida (0-100), stop dist bar + 5m badge, pa_pattern, R:R estimado, tempo de posicao.

### 8.4 Constantes de banca do Sandbox UI (`routes/sandbox.py`)
`BANCA_BASE`=$10.000 (:20) · `MARGEM_SCALP`=$200 (:21) · `MARGEM_SWING`=$200 (:22) · alocacao maxima = 40% = $4.000 (:53).

### 8.5 Protocolo Lock-In (Proteção de Banca — V126)
- **Objetivo**: Proteger o capital simulado acumulado quando a banca atinge a meta mínima de crescimento.
- **Ativação**: Ocorre automaticamente quando o saldo consolidado (banca + PnL aberto de Scalp e Swing) cresce 10% (gatilho configurado em `SANDBOX_LOCK_IN_TRIGGER_PERCENT` padrão 10.0%, ou seja, >= $11.000).
- **Ação**: O stop loss das ordens ativas passa a ser recalculado de forma colada a 5% de recuo da margem de entrada por trade (`SANDBOX_LOCK_IN_STOP_PERCENT` padrão 5.0%), equivalente a 5.0% de ROI ou 0.10% de oscilação do preço do ativo a partir do pico.
- **Identificação**: O stop é marcado no banco e na UI como `LOCK-IN_5%` na fase de `DEFESA`.
- **Desativação**: O protocolo só é inativado caso a banca consolidada recue abaixo do saldo inicial de $10.000.

### 8.6 Espelho PAPER → Cockpit (V127)

Em modo `PAPER`, o Cockpit (`cockpit.html`) espelha o Sandbox integralmente, para que o operador veja a carteira simulada como se fosse a real:

- **Net Worth (Banca)**: vem da **Banca Simulada Consolidada do Sandbox** calculada por `DatabaseService.get_sandbox_unified_balance()` (`services/database_service.py`): `10000 + Σ(pnl_pct/100 × 200)` sobre **TODOS** os trades (fechados + ativos) de Scalping Lab e Swing Lab. Implementacao em SQL agregado (`SUM(pnl_pct)`) para evitar leitura de ORM destacado. Igual ao `virtual_balance` de `/api/sandbox/unified-state` (Secao 8.4).
  - Consumido por: `bankroll.update_banca_status` (`saldo_total`/`configured_balance`/`paper_equity` = saldo do Sandbox; `saldo_real_okx` forçado a `0.0` em PAPER p/ o Cockpit flutuar a base com o PnL), `system.get_banca_data` (PAPER), e `bankroll_guardian.evaluate_bank_health` (PAPER, que define o `equity` exibido como Net Worth).
- **Painel de Custodia (Ordens)**: `GET /api/slots` (`routes/trading.py`) e o broadcast WS `live_slots` (`main.py:slots_broadcast_loop`, a cada 5s) mesclam em PAPER as ordens ativas do Sandbox como slots:
  - Scalping Lab → `slot_type="SCALPING"`; Swing Lab → `slot_type="SWING"`.
  - Mapeamento via `_map_sandbox_trade_to_slot` (direction→side; entry_price/stop_loss/target → entry_price/current_stop/target_price; margin $200; leverage do settings).
  - O PnL ao vivo de cada ordem e recalculado no `GET /api/slots` via `build_projection` (preco real da OKX); o WS mantem symbol/entry entre os polls.
- **Net Worth no frontend**: `liveEquity` (`cockpit.html:6442-6449`) usa `guardianEquity` quando `guardianReport.equity > 0` — por isso o `equity` do Guardiao (agora = saldo do Sandbox em PAPER) e a fonte do Net Worth, e nao o `saldo_total` cru.

> **Caveat conhecido**: o header "Slots X/20" / `available_slots_count` ainda reflete os slots reais (0 em PAPER), nao o count do Sandbox. Apenas o Painel de Custodia (posicoes) e o Net Worth sao espelhados.

---

## 9. Watchlists (fonte: `backend/config.py`)

- **ELITE_40_MATRIX** (`:194`) — **35** pares elegiveis 50x OKX.
- **RADAR_WATCHLIST** (`:212`) — **26** pares (V126 removeu SAND, BCH, SOL, STX, EGLD).
- **DECOR_WATCHLIST** (`:233`) — **89** pares para o DECOR_HUNTER.
- **ASSET_BLOCKLIST** (`:266`) — set com ~55 simbolos bloqueados (inclui BTC/ETH como monitor-only, memecoins, stablecoins, metais, e pares de performance negativa no sandbox: AAVE, CRV, SUI, TRX, TIA, LINK, AVAX, SOL, JUP, ONDO, etc.).

---

## 10. Endpoints da API (routers registrados em `backend/main.py:821-834`)

| Prefixo | Router | Endpoints principais |
|---|---|---|
| `/api/auth` | `auth.py` | `/login`, `/register`, `/refresh`, `/logout`, `/me`, `/change-password`, `/users`, `/users/{id}/role`, `/users/{id}/approve`, `/users/{id}/block` |
| `/api/admin` | `admin.py` | `/users`, `/stats`, `/user/{username}/status`, `/lockdown`, `/reset-system` |
| `/api/sandbox` | `sandbox.py` | `/unified-state` (Banca Simulada Consolidada — fonte do espelho PAPER), `/trades`, `/stats`, `/patterns`, `/analytics`, `/clear`, `/swing/trades`, `/swing/stats`, `/swing/patterns`, `/swing/analytics`, `/swing/clear`, `/swing/mirror-status`, `/swing/mirror-toggle` |
| `/api/vault` | `vault.py` | `/save`, `/status` |
| `/api/sentinel` | `sentinel.py` | Auditoria de execucao |
| `/api/memory` | `memory_routes.py` | Memory Galaxy |
| `/api/account` | `tokens.py` | Credenciais OKX por usuario |
| `/api` | `market.py` | `/elite-pairs`, `/btc/regime`, `/radar/pulse`, `/radar/grid`, `/radar/librarian`, `/radar/regimes`, `/captain/tocaias`, `/trend/{symbol}`, `/market/klines`, `/system/state`, `/market/study` |
| `/api` | `trading.py` | `/slots` (em PAPER mescla ordens ativas do Sandbox: Scalp→SCALPING, Swing→SWING — Secao 8.6) |
| `/api` | `chat.py` | `/hermes/chat`, `/hermes/compliance`, `/hermes/status`, `/hermes/sessions` (GET/POST), `/hermes/sessions/{id}` (GET/DELETE/PATCH), `/chat`, `/chat/manual`, `/chat/reset`, `/chat/status`, `/tts`, `/tts/voices`, `/logs` |
| `/api` | `system.py` | `/test`, `/debug/test`, `/health` |
| — | `dashboard.py`, `aios.py`, `backtest_routes.py` | SPA / AIOS / backtest |

---

## 11. Camadas de Dados

| Banco | Funcao | Tabelas principais |
|---|---|---|
| PostgreSQL | SSOT persistente | `slots`, `radar_pulse`, `banca_status`, `sandbox_trades`, `moonbags`, `chat_sessions`, `chat_messages` |
| Firebase Firestore | Multi-tenant, sync nuvem | `users`, `trade_history`, `trade_analytics`, `fleet_intelligence`, `vault_history` |
| Firebase RTDB | Estado em tempo real | `system_state`, `active_slots`, `radar_pulse`, `chat_status`, `banca` |
| SQLite | Cache de klines (librarian) | `klines` |

---

## 12. Memory Galaxy & Hermes Chat

- **Memory Galaxy** (`services/galaxy_memory_service.py`): cofre Obsidian em `vault_galaxy/` com subpastas `trades/`, `journal/`, `strategies/`. Gravacao disparada em `database_service.save_trade_history_item`, transicoes de regime (`oracle_agent`) e chats do Hermes.
- **Hermes Chat** (`frontend/hermes-chat.html`, rota `/hermes`): cascade NVIDIA → DeepSeek → AIService (Gemini/OpenRouter). Persiste em Postgres (`chat_sessions`, `chat_messages`).
- **Contexto do Hermes**: le este `MASTER_ARCHITECTURE.md` (primeiros 8000 chars, cache 10min) + busca por keyword em `vault_galaxy/{journal,trades,strategies}/*.md` + intel wiki + compliance + dimensoes do JarvisBrain.

---

## 13. Deploy

| Componente | Valor |
|---|---|
| Plataforma | Railway + Docker |
| Python | 3.12-slim |
| PORT | 8085 |
| Entry (todos) | `uvicorn backend.main:app --host 0.0.0.0 --port $PORT --workers 1` |
| Health Check | `GET /api/health` |
| VERSION / DEPLOYMENT_ID | `V124.7` / `V124.7_M30_SWING` (`backend/main.py:68-69`) |

---

## 14. Observacoes Tecnicas Conhecidas

1. Multiplas versoes coexistem nos cabecalhos (V20.5 captain, V110.x services, V124–V126 features). O DEPLOYMENT_ID oficial e `V124.7`.
2. Referencias Bybit legadas: `market.py` ainda usa nomes `BybitRest`/`BybitWS` apesar de operar so na OKX.
3. `get_slot_type()` em `bankroll.py` retorna sempre "DVAP" (V110.950) — diferenciacao de tipo de slot e vestigial.
4. `radar_pulse` nao e arquivo: e estrutura de dados em `database_service`, `firebase_service` e `websocket_service`.
5. Comentarios legados em `bankroll.py` ($2/$1, 20/40) divergem do `config.py` atual (0.50, 16/16) — o `config.py` prevalece.
6. **[V127] Espelho PAPER Sandbox→Cockpit** (refinamento sobre o V124.7): em PAPER o *Net Worth* e o *Painel de Custodia* do Cockpit representam o Sandbox (Banca Simulada Consolidada via `get_sandbox_unified_balance` + ordens ativas Scalp/Swing como slots). `saldo_real_okx` e forçado a `0.0` em PAPER em `update_banca_status`. `OKX_SIMULATED_BALANCE` deixa de ser o saldo exibido em PAPER (subsituido pelo saldo do Sandbox), mas segue como base de sizing/guardian. Ver Secao 8.6.
7. **[V127] Swing Stop refinado**: stop inicial configuravel via `SWING_STOP_ROI` (padrao 5.0 = -5% ROI = 0.1% preco). Escadinha BREAKEVEN em +10% ROI (antes +30%). Confirmação de entry: candle 5m fecha na direcao + volume ≥ 1.5x media. Trade INJUSDT +15.7% (+$31.40) e DOTUSDT -5.3% (-$10.68) validaram o sistema (R:R 1:2.94).
8. **[V128] Swing Lab otimizado por simulacao**: STOP=10% (0.2% preco), BE=+2% (protecao rapida), regime filter (bearish→SHORT, bullish→LONG), hour filter (pausa 14-15 UTC), blacklist dinamica (auto-bloqueio apos 3+ trades com WR<20%). Simulacao mostrou que SHORTs tem 50% WR vs LONGs 10%.

---

*Documento unico de arquitetura. Substitui e consolida os antigos ARCHITECTURE_REFERENCE, DOCUMENTATION_INDEX, STATE, SNIPER_PROTOCOLS, RESET_PROTOCOL, RULES e REQUIREMENTS.*
