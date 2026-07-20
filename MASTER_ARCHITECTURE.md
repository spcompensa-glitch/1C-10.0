# MASTER_ARCHITECTURE.md — 1Crypten 7.0

Fonte unica de verdade arquitetural. Extraido diretamente do codigo-fonte (nao de historico de versoes).
Este e o unico documento de arquitetura do projeto — o Hermes le os primeiros ~8000 caracteres deste arquivo em cada resposta (`hermes_agent.py:_load_architecture_context`), portanto os fatos mais criticos ficam no topo.

*Verificado contra o codigo em 2026-07-18. VERSION no codigo: `backend/main.py` VERSION="V131" / DEPLOYMENT_ID="V131_BUG_FIX". Correcoes criticas [V131] aplicadas sobre o V130 — ver Secao 14, item 18.*

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
| `SWING_LEVERAGE` / `SWING_STOP_ROI` | 50x / -35.0% ROI | [V132-SWING-2H] |
| `SWING_SCAN_INTERVAL` | 1800s (30m) | [V132-SWING-2H] |

**Swing Lab [V132-SWING-2H]**: `SWING_LEVERAGE`=50x, `SWING_MARGIN_PER_TRADE`=$200 (2% da banca consolidada), `SWING_SCAN_INTERVAL`=1800s, `SWING_STOP_ROI`=35.0 (stop inicial -35% ROI = 0.7% preco com 50x). Análise baseada no timeframe de **2H (120m)** com confirmação de micro-gatilho de precisão no **15m Stochastic RSI**.

> **[V127] Saldo exibido em PAPER**: `OKX_SIMULATED_BALANCE` e a base do Guardiao/sizing em PAPER, mas o *Net Worth* do Cockpit em PAPER NAO e `OKX_SIMULATED_BALANCE` — e a **Banca Simulada Consolidada do Sandbox** (`get_sandbox_unified_balance`, `database_service.py`: `BANCA_BASE` $10.000 + Σ(pnl_pct/100 × $200) sobre TODOS os trades Scalp+Swing). Ver Secao 8.6.

> Nota: `bankroll.py` le `settings.MARGIN_PER_TRADE_*` (0.50) e `settings.MAX_SLOTS_*` (16). Comentarios legados em `bankroll.py` citam "$2.00/$1.00" e "20/40" — esses valores NAO refletem o config atual.

---

## 3. Escadinha de Stops (fonte: `backend/services/order_projection_service.py` + `sandbox_service.py` + `sandbox_swing_service.py`)

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

### 3.2 `ORDER_STOP_LADDER_SCALPING` (VWAP SNIPER) [V132]
| Gatilho | Stop | Nome |
|---|---|---|
| 6% | 1.5% | GARANTIA_TAXAS_SCALP |
| 10% | 3.5% | LUCRO_CURTO_SCALP |
| 15% | 8% | LUCRO_MEDIO_SCALP |
| 22% | 15% | TRAILING_SCALP |

### 3.3 `ORDER_STOP_LADDER_SWING` (swing tendencia - V132 2H 50x)
| Gatilho | Stop | Nome |
|---|---|---|
| 15% | 0% | BREAKEVEN_2H |
| 35% | 10% | PROTECAO_PARCIAL |
| 70% | 35% | LUCRO_MEDIO_2H |
| 120% | 80% | EMANCIPADO_2H |
| 200% | 150% | SUPER_TENDENCIA |
| 350% | 280% | ALVO_ESTENDIDO_2H |

### 3.4 `ORDER_STOP_LADDER_SWING_LATERAL` (swing em lateral)
| Gatilho | Stop | Nome |
|---|---|---|
| 5% | 1.5% | BREAKEVEN_LATERAL |
| 15% | 5% | PRE_UNIT1_LATERAL |
| 30% | 15% | UNIT1_GARANTIDO |
| 60% | 30% | EMANCIPADO_LATERAL |
| 100% | 80% | TRAILING_LATERAL |

### 3.5 `ORDER_STOP_LADDER_TRENDING` (tendencia)
14/2, 25/10, 40/20, 60/40, 80/60, 100/80, 130/110, 150/110, 200/150, 300/220, 400/280, 500/350, 600/420, 700/500, 750/600, 800/650, 1000/800, 1200/1000.
Acima de 1200% ROI (APEX): niveis `ULTRA_*` a cada +200% ROI, stop = gatilho − 200%.

`ORDER_STOP_LADDER` (sem sufixo) e um alias de `TRENDING` para compatibilidade com o compliance do Hermes.

### 3.6 Proteções Adicionais (Scalping/Swing Sandbox)

**GARANTIA_12 — Risco Zero Imediato [V132]** (`sandbox_service.py:1571-1583`):
Quando `max_roi >= 12.0%` no Scalping (ou `>= 8.0%` nas demais estratégias) e `current_stop_roi < 0%`, stop vai a 0% ROI (break-even). Proteção imediata do capital com folga contra ruídos.

**GARANTIA_TRAIL — Trailing Dinâmico [V122 / V131-FIX / V132]** (`sandbox_service.py:1588-1615`):
Quando `max_roi >= breakeven_trigger`, stop = `max(1.5, max_roi × 0.60)` (60% do pico, mínimo +1.5%).
**[V131-FIX]** Correção de bug crítico: a condição `current_stop_roi < 0.0` impedia o trailing de avançar após a GARANTIA_8/12 mover o stop para 0%. Removida a condição.
**[V132]** Trailing no Scalping só ativa a partir de +12.0% de max_roi para dar runway.
Exemplos: pico +17% → stop +10.2%; pico +21% → stop +12.6%; pico +29% → stop +17.4%.

### 3.7 Equity Defense — Defesa Progressiva de Patrimônio [V128]

Sistema de proteção do saldo consolidado da banca Sandbox. Rastreia o pico da equity e protege
80% do lucro acumulado com stops progressivos por nível.

**Config** (`config.py:193-203`):
- `EQUITY_DEFENSE_LOCK_RATIO = 0.80` — 80% do lucro do pico é protegido
- `EQUITY_DEFENSE_STOP_L1 = 7.0%` — L1 LEVE: stop = pico - 7%
- `EQUITY_DEFENSE_STOP_L2 = 5.0%` — L2 MODERADO: stop = pico - 5%
- `EQUITY_DEFENSE_STOP_L3 = 3.0%` — L3 FORTE: stop = pico - 3%
- `EQUITY_DEFENSE_MIN_ROI = 5.0%` — ROI mínimo do trade para defesa aplicar (evita fechar trades com ROI baixo)

**Níveis de defesa** (`sandbox_service.py:1333-1368`):

| Banca (profit %) | Nível | Ação |
|---|---|---|
| < +3% | 0 OFF | Stop segue escadinha normal |
| +3% a +4.9% | 1 LEVE | Stop = pico - 7% |
| +5% a +9.9% | 2 MODERADO | Stop = pico - 5% |
| >= +10% | 3 FORTE | Stop = pico - 3% |
| abaixo do piso | 4 CRITICO | Fecha todos os trades |

**Piso protegido** (`database_service.py:296-301`):
```
peak = maior saldo já visto
peak_profit = peak - base ($10.000)
floor = base + (peak_profit × 0.80)

Exemplo: peak $10.900 → floor = $10.000 + ($900 × 0.80) = $10.720
```

**Enforcement** (`sandbox_service.py:1497-1527`, `flash_agent.py:507-547`):
- L1/L2/L3: sobe stop para `peak_roi - stop_pct` (só se > stop atual E max_roi >= 5%)
- CRITICO: fecha trade imediatamente com status `CLOSED_EQUITY_DEFENSE`
- Threshold: defesa só aplica quando ROI máximo do trade >= 5% (evita fechar trades marginais)
- Regra "só sobe": defense_stop só aplica se > stop atual da escadinha

**UI** (`sandbox.html`):
- Badge `🛡️ DEFESA` ao lado do `🔒 LOCK-IN` no card de Banca
- Cores: L1=azul, L2=amarelo, L3=laranja, CRITICO=vermelho+pulse
- Trade rows: indicador `EQUITY_L1/L2/L3/CRITICO`
- Tooltip: Pico | Piso | Banca | Stop%

### 3.8 Stops Iniciais

**Scalping Lab — VWAP SNIPER [V127.2 / V132]** (`sandbox_scalping_engine.py:47`):
- `_MAX_STOP_ROI = -8.0%` (0.16% preço com 50x).
- Stop = 1.0x ATR do 1m, máximo -8% ROI.
- GARANTIA_12 ativa em +12% ROI → stop vai a 0%.

**Scalping Lab — Stop Adaptativo [V123]** (`sandbox_service.py:321-400`):
- Tenta stop estrutural 30M (swing low/high + buffer) — aprovado se ROI entre -40% e -25%.
- Fallback: -25% ROI (0.5% preço com 50x).
- Teto rígido: -30% ROI (0.6% preço).

**Swing Lab — Stop Configurável e Micro-Gatilho [V132-SWING-2H]** (`sandbox_swing_service.py`):
- Alavancagem padrão de 50x com stop inicial rígido de **-35% ROI** (equivalente a 0.7% no preço).
- Análise baseada inteiramente no timeframe de **2H (120m)** com scan a cada 30 minutos (1800s).
- **Filtro de Entrada de Alta Precisão (15m):** Os sinais de 2H só iniciam o trade se o Stochastic RSI no gráfico de 15m estiver alinhado com a direção do trade.
- Zero-Risk Stacking regulado para no máximo 2 posições sob risco de mesa simultâneas.

**Execution Protocol — Breakeven Adaptativo [BLITZ]** (`execution_protocol.py:430-494`):
- DNA do ativo via Librarian: wick_multiplier e is_retest_heavy.
- Ativo limpo: breakeven em +30% ROI.
- Ativo instável: breakeven em +50% ROI.
- Pavio extremo/retest: breakeven em +60% ROI.

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

Swing 2H usa `SignalGenerator.analyze_m30_swing()` (reusa DVAP/MOLA/FAS/LRT + TREND + DECOR em timeframe de 120m). O antigo `blitz_sniper.py` foi **removido** (V125.3).

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
- **SandboxSwingService** (`services/sandbox_swing_service.py`) — motor Swing Lab 2H (scan 30min, Zero-Risk Stacking cap 2, 15 slots total).
- **SandboxScalpingEngine** (`services/sandbox_scalping_engine.py`) — motor Scalping Lab (VWAP SNIPER, scan 30s).
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

### 8.1 SandboxService (`services/sandbox_service.py`) — ciclo 1s **[V131-FIX]**
- Espelha o sistema real. Recebe sinais via `on_radar_pulse` → `_process_radar_signals`.
- Stop adaptativo por regime (fallback): LATERAL -8% ROI / TRENDING -10% ROI; capping -10%.
- Margem adaptativa por win rate do par: $1.00–$2.50 (`_get_adaptive_margin`).
- Cooldown pos stop-out **por (simbolo, direcao)**: **1800s** no 1o stop, **3600s** em stops consecutivos (>=2) — `sandbox_service.py:735`.
- Cooldown de transicao fria (tendencia→lateral): **900s** (`:551`).
- Confirmacao 5M (2/3 candles alinhados), Entry Sanity Check (70% do stop), auto-blocklist (PnL<-15% E WR<35% apos 3+ trades).
- Espelhamento real (V124.4): se `OKX_API_KEY_MASTER` + modo REAL, replica ordens; auditado pelo ExecutionAuditorAgent.
- **[V131-FIX] Limite de slots corrigido de 10 para 5** (`sandbox_service.py:709`): o limite do Radar estava em `>= 10` enquanto o VWAP SNIPER usa `_MAX_SLOTS=5`. Agora consistentes.
- **[V131-FIX] Anti-hedge via Radar** (`sandbox_service.py:751`): bloqueado trade em direção oposta se o par já tem trade ativo. Evita LONG+SHORT simultâneos no mesmo par.
- **[V131-FIX] GARANTIA_TRAIL desbloqueado** (`sandbox_service.py:1571`): removida condição `current_stop_roi < 0.0` que travava o trailing em 0% após GARANTIA_8 ativar.
- **[V131-FIX] `AttributeError: self.dynamic_margin` corrigido** (`sandbox_service.py:1546`): atributo inexistente substituído por leitura dinâmica de `trade.contract_meta["margin"]` com fallback $200.

### 8.2 Scalping Lab — VWAP SNIPER (`services/sandbox_scalping_engine.py`) **[V132-REFINADO]**
- Scan 30s. Filtro tendência EMA200 (M5); toque no VWAP diário (M1, tol 0.30%).
- **[V132-REFINADO] Gatilhos e confluência:**
    *   **BTC Trend Bias (15m):** Bloqueia LONGs se variação de 15m do BTC for < -0.40% e SHORTs se for > 0.40% (evita entrar contra fluxo).
    *   **Stochastic RSI (1m):** Exige cruzamento real de linhas: %K cruza acima de %D (LONG, k<35) ou cruzamento abaixo (SHORT, k>80).
    *   **Volume Relativo de 5m:** Rejeita novas entradas se o volume de 5m estiver < 1.1x acima da média simples de 20 períodos (evita mercados estagnados).
- **Leverage/Stops:** 50x isolada, margem dinâmica baseada em score (30%, 60% ou 100% da margem base de 2% da banca consolidada), stop inicial em -8% ROI.

### 8.3 Swing Lab — 2H (`services/sandbox_swing_service.py`) **[V132-SWING-2H]**
- Scan a cada 30min no timeframe de **2H (120m)** via `SignalGenerator.analyze_m30_swing()`.
- Banca consolidada dinâmica (Juros Compostos), margem inicial $200/trade (2% da banca total recalculado dinamicamente), 50x.
- **Stop inicial -35% ROI** (`SWING_STOP_ROI=35.0`): `stop_price = entry × (1 - 0.35/50) = entry × 0.993` (0.7% de oscilacao do preco).
- **Filtro de Entrada de Alta Precisão (15m):** Setup de 2H só entra se o Stochastic RSI no gráfico de 15m confirmar a direção do momentum (LONG `k_15m > d_15m`, SHORT `k_15m < d_15m`).
- **Zero-Risk Stacking (cap 2):** Permite no máximo 2 posições sob risco de mesa ao mesmo tempo. Novas entradas exigem que pelo menos uma das ordens ativas já tenha atingido o break-even (risco zero).

### 8.4 Constantes de banca do Sandbox UI (`routes/sandbox.py`)
`BANCA_BASE`=$10.000 (:20) · `MARGEM_SCALP`=dinâmica (2% da banca total) · `MARGEM_SWING`=dinâmica (2% da banca total) · alocacao maxima = 40% da banca consolidada total.

### 8.5 Protocolo Lock-In (Proteção de Banca — V126)
- **Objetivo**: Proteger o capital simulado acumulado quando a banca atinge a meta mínima de crescimento.
- **Ativação**: Ocorre automaticamente quando o saldo consolidado (banca + PnL aberto de Scalp e Swing) grows 10% (gatilho configurado em `SANDBOX_LOCK_IN_TRIGGER_PERCENT` padrão 10.0%, ou seja, >= $11.000).
- **Ação**: O stop loss das ordens ativas passa a ser recalculado de forma colada a 5% de recuo da margem de entrada por trade (`SANDBOX_LOCK_IN_STOP_PERCENT` padrão 5.0%), equivalente a 5.0% de ROI ou 0.10% de oscilação do preço do ativo a partir do pico.
- **Identificação**: O stop é marcado no banco e na UI como `LOCK-IN_5%` na fase de `DEFESA`.
- **Desativação**: O protocolo só é inativado caso a banca consolidada recue abaixo do saldo inicial de $10.000.

### 8.6 Espelho PAPER → Cockpit (V127 / V127.1 / V129)

Em modo `PAPER`, o Cockpit (`cockpit.html`) espelha o Sandbox integralmente, para que o operador veja a carteira simulada como se fosse a real:

- **Net Worth (Banca)**: vem da **Banca Simulada Realizada do Sandbox** calculada por `DatabaseService.get_sandbox_unified_balance()` (`services/database_service.py`): `10000 + Σ(pnl_pct/100 × margin_at_opening)` sobre **APENAS trades FECHADOS** (status `CLOSED_SL`, `CLOSED_TRAILING` ou `EMANCIPATED`) de Scalping Lab e Swing Lab. O PnL nao realizado dos trades ativos e calculado separadamente pelo `bankroll_guardian._live_bankroll_snapshot()`.
  - **[V127.1] Fix de dupla contagem**: Anteriormente (V127), `get_sandbox_unified_balance()` somava TODOS os trades (fechados + ativos), causando inflacao artificial do equity quando combinado com o `realized_pnl` do Guardian. Agora, o saldo realizado do Sandbox ja e o `base_balance` do Guardian, e o PnL dos slots ativos e adicionado apenas uma vez via `_live_bankroll_snapshot()`.
  - Consumido por: `bankroll.update_banca_status` (`saldo_total`/`configured_balance`/`paper_equity` = saldo realizado do Sandbox; `saldo_real_okx` forçado a `0.0` em PAPER), `system.get_banca_data` (PAPER), e `bankroll_guardian.evaluate_bank_health` (PAPER, que define o `equity` exibido como Net Worth).
- **Painel de Custodia (Ordens)**: `GET /api/slots` (`routes/trading.py`) e o broadcast WS `live_slots` (`main.py:slots_broadcast_loop`, a cada 5s) mesclam em PAPER as ordens ativas do Sandbox como slots:
  - Scalping Lab → `slot_type="SCALPING"`; Swing Lab → `slot_type="SWING"`.
  - Mapeamento via `_map_sandbox_trade_to_slot` (direction→side; entry_price/stop_loss/target → entry_price/current_stop/target_price; margin $200; leverage do settings).
  - O PnL ao vivo de cada ordem e recalculado no `GET /api/slots` via `build_projection` (preco real da OKX); o WS mantem symbol/entry entre os polls.
- **Net Worth no frontend**: `liveEquity` (`cockpit.html:6442-6449`) usa `guardianEquity` quando `guardianReport.equity > 0` — por isso o `equity` do Guardiao (saldo realizado + PnL slots ativos em PAPER) e a fonte do Net Worth, e nao o `saldo_total` cru.

> **Caveat conhecido**: o header "Slots X/20" / `available_slots_count` ainda reflete os slots reais (0 em PAPER), nao o count do Sandbox. Apenas o Painel de Custodia (posicoes) e o Net Worth sao espelhados.
> **Nota V127.1**: o endpoint `/api/sandbox/unified-state` continua retornando o saldo consolidado com todos os trades (fechados + ativos) para fins de monitoramento no sandbox.html. Apenas o cálculo do Guardian (que alimenta o Cockpit) usa apenas trades fechados.

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
9. **[V127.1] Fix de dupla contagem de PnL**: Corrigido bug onde o equity do Guardian era inflado por somar o PnL realizado duas vezes (via `get_sandbox_unified_balance` que incluia TODOS os trades + `realized_pnl` do Firebase). Agora, `get_sandbox_unified_balance()` filtra APENAS trades fechados (`CLOSED_SL`, `CLOSED_TRAILING`, `EMANCIPATED`), e `_live_bankroll_snapshot()` em PAPER NAO soma `realized_pnl` novamente. Correções em: `database_service.py:1195-1223`, `bankroll_guardian.py:342-371`. Ver Secao 8.6.
10. **[V128→V127.2] Swing Stop restaurado para 5% ROI (0.1% preço)**: `SWING_STOP_ROI=5.0` (config.py:181). O V128 aumentou para 25% ROI (0.5% preço), causando 100% de trades Swing em stop (-25% cada). Restaurado para 5% (0.1% preço) para dar fôlego ao trade. Breakeven restaurado de +4% para +10% ROI.
11. **[V127.2] Scalping Stop restaurado para -8% ROI (0.16% preço)**: `_MAX_STOP_ROI=-8.0` (sandbox_scalping_engine.py:47). O V128 aumentou para -15% (0.3% preço), causando R:R 1:3 e expectancy negativa (-2.08% por trade). Restaurado para -8% (0.16% preço) para R:R ~1:1.
12. **[V127.2] GARANTIA_8 (antes GARANTIA_5)**: Threshold de proteção subiu de +5% para +8% ROI. Stop vai a 0% quando trade atinge +8% ROI. Evita violinada em lucros marginais.
13. **[V122] GARANTIA_TRAIL: trailing 60% do pico**: Quando max_roi >= 8% e stop < 0%, stop = max(1.5, max_roi × 0.60). Trade com pico +21% tem stop em +12.6% (não +1.5% fixo). Protege lucro sem travar cedo demais.
14. **[V128] Breakeven adaptativo BLITZ**: Execution Protocol usa DNA do ativo (Librarian) para definir breakeven: ativo limpo +30% ROI, instável +50%, pavio extremo +60%.
15. **[V128] Equity Defense — Defesa Progressiva de Patrimônio**: Protege o saldo consolidado da banca Sandbox. Rastreia o pico (`equity_peak`) e calcula um piso protegido = base + (peak_profit × 0.80). Níveis: OFF (<3%), L1 LEVE (+3%, stop=pico-7%), L2 MODERADO (+5%, stop=pico-5%), L3 FORTE (+10%, stop=pico-3%), CRITICO (abaixo do piso, fecha tudo). Enforcement em `sandbox_service.py:1497-1527` e `flash_agent.py:507-547`. Telemetria em `GET /api/sandbox/unified-state`. Badge UI no sandbox.html.
16. **[V129] Correção do Filtro de Regime e Filtro de Gás/Volume em LATERAL**: Corrigido bug que bloqueava ordens SHORT no regime LATERAL (usava `not is_bearish` incorretamente bloqueando o SHORT). Adicionada exigência de "gás" para o regime LATERAL: novos trades Swing exigem score >= 80 e volume_ratio >= 1.5x para garantir rompimentos fortes com momentum.
18. **[V131] Correções críticas de bugs identificados via diagnóstico do PostgreSQL Railway** (2026-07-18, banca em $9.537 = -4.63%):
    - **Leverage/Stop inconsistentes**: `_LEVERAGE` estava em 10x (V130) mas `sandbox_service.py` monitora com 50x real. Restaurado: `_LEVERAGE=50.0`, `_MAX_STOP_ROI=-8.0` (0.16% de preço).
    - **Hedge LONG+SHORT no mesmo par**: Detecção anti-duplicata em `_try_open_trade` bloqueava apenas mesma direção. Corrigido para bloquear qualquer trade ativo no par. Idem em `sandbox_service._process_radar_signals`.
    - **Race condition — mais de 5 slots abertos**: Resolvido com `asyncio.Lock()` (`_open_lock`) + refetch atômico dentro do lock.
    - **Limite de slots Radar era 10 (deveria ser 5)**: Corrigido para `>= 5`.
    - **GARANTIA_TRAIL travado em 0%**: Condição `current_stop_roi < 0.0` impedia o trailing de avançar após GARANTIA_8 mover stop para 0%. Removida a condição.
    - **`AttributeError: self.dynamic_margin`**: Corrigido para usar `trade.contract_meta["margin"]` com fallback $200.

19. **[V132] Otimização de R:R no Scalping Lab** (2026-07-18):
    - **Limpeza de Base de Dados**: Encerramento manual via script SQL de dois trades travados há >8.5h (`SOLUSDT` e `VETUSDT`).
    - **Garantia de Risco Zero a +12% ROI**: Elevação do patamar do break-even de +8% para +12% no VWAP SNIPER para dar mais runway contra ruídos de preço.
    - **Escadinha de Scalping afrouxada**: Nova escala `ORDER_STOP_LADDER_SCALPING` configurada como (+6%/+1.5%, +10%/+3.5%, +15%/+8.0%, +22%/+15.0%) para dar distância entre o preço atual e o stop, maximizando a captura de lucros e pagando as perdas de -8% de forma estatisticamente lucrativa.
20. **[V132-REFINADO / V132-SWING-2H] Otimização e Refinamento do Sandbox** (2026-07-20):
    - **Scalping Lab:** Injetados os filtros de confluência inteligente: *BTC Trend Bias* no gráfico de 15m, *cruzamento real do Stochastic RSI (K/D)* na sobrevenda/sobrecompra, e *Volume Relativo de 5m* mínimo de 1.1x.
    - **Swing Lab:** Transicionado o motor autônomo para operar no gráfico macro de **2H (120m)** com alavancagem forçada de **50x** e stop loss inicial rígido de **-35% ROI** (0.7% no preço). Scan executado a cada 30min (1800s).
    - **Micro-Gatilho de Precisão (15m):** As ordens de 2H do Swing Lab agora são filtradas na entrada pelo alinhamento do Stochastic RSI no tempo menor de 15m.
    - **Escadinha de Swing 2H 50x:** Atualizada a escala `ORDER_STOP_LADDER_SWING` para gatilho de break-even a +15% ROI, e níveis escalonados (+35%/+10%, +70%/+35%, +120%/+80%, +200%/+150%, +350%/+280% de lucro).
    - **Risco de mesa do Swing:** Mantido limite rígido de no máximo 2 posições sob risco de mesa simultâneas.

---

*Documento unico de arquitetura. Substitui e consolida os antigos ARCHITECTURE_REFERENCE, DOCUMENTATION_INDEX, STATE, SNIPER_PROTOCOLS, RESET_PROTOCOL, RULES e REQUIREMENTS.*
