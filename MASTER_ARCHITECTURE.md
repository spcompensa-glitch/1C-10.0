# MASTER_ARCHITECTURE.md — 1Crypten 7.0

Fonte unica de verdade arquitetural. Baseado no codigo-fonte, nao em historico de versoes.

*Ultima atualizacao: 2026-07-11 (V126 — Memory Galaxy disco orbital + Hermes Chat cascade)*

---

## 1. Visao Geral

1Crypten e um sistema de trading automatizado para criptomoedas na OKX. Opera em modo PAPER (simulacao) e REAL (producao) simultaneamente, com gestao de risco por IA e stops progressivos (escadinha).

- **Plataforma**: Railway + Docker
- **Backend**: FastAPI (Python 3.12)
- **Frontend**: HTML/JS standalone (cockpit.html, ~430KB)
- **Banco principal**: PostgreSQL (Railway)
- **Cache**: Firebase RTDB (sincronizacao UI)
- **Exchange**: OKX (Portfolio Margin)

---

## 2. Stack de Agentes (AIOS)

O sistema usa 19 componentes/agentes especializados, cada um com responsabilidade unica:

### 2.1 Agentes de Decisao

| Agente | Arquivo | Funcao |
|--------|---------|--------|
| **CaptainAgent** | `agents/captain.py` | Despachante de sinais. Quality gate, regime gating, consensus de frota (Macro 15%, Whale 25%, SMC 30%, OnChain 30%). V20.5 |
| **OracleAgent** | `agents/oracle_agent.py` | Determinacao de regime de mercado. Grade ADX: RANGING (<25), TRENDING (>=25). Estabilizacao de 150s |
| **FlashAgent** | `agents/flash_agent.py` | Motor da escadinha e monitoramento de risco. Loop de 1s. Gerencia stops e take profits (saída parcial desativada para Scalping). |
| **BankrollGuardian** | `agents/bankroll_guardian.py` | Autorizacao de trades. Gating por regime, limites de slots, memoria por par |
| **SlotOperator** | `agents/slot_operator.py` | Observador/failsafe. Loop de 3s. Virtual stop loss monitoring |

### 2.2 Agentes de Sinal

| Agente | Arquivo | Funcao |
|--------|---------|--------|
| **SandboxSwingService**| `services/sandbox_swing_service.py`| Motor primário do Swing Lab. Realiza scan M30 a cada 5min e aplica Zero-Risk Stacking. |
| **SandboxScalpingEngine**| `services/sandbox_scalping_engine.py`| Motor primário do Scalping Lab (VWAP SNIPER). Varre M1/M5 a cada 60s. |
| **AmbushAgent** | `agents/ambush.py` | Entrada Fibonacci. Timeout 30min, deteccao Wyckoff, sweep tolerance 0.998x/1.002x |
| **WhaleTracker** | `agents/whale_tracker.py` | Fluxo institucional. CVD/OI, deteccao de armadilha, whale pulse >= 150k CVD |
| **OnChainWhaleWatcher** | `agents/onchain_whale_watcher.py` | Monitoramento blockchain. Bybit hot wallet, threshold $500k USDT / 200 ETH |

### 2.3 Agentes de Analise

| Agente | Arquivo | Funcao |
|--------|---------|--------|
| **MacroAnalyst** | `agents/macro_analyst.py` | Risco macro BTC. Correlacao Pearson (panic se >0.8 + BTC >2%), dominancia |
| **Librarian** | `agents/librarian.py` | DNA do ativo, rankings, setores. Ciclo 2h, quarantena 4h, blacklist memecoin |
| **LibrarianAuditor** | `agents/librarian_auditor.py` | Ajuste de bias. Ciclo 4h, range 0.5-1.2 |
| **TradeAnalyst** | `agents/trade_analyst.py` | Autopsia pos-trade. Analise 30min, sessoes Asia/London/NY |
| **SentimentSpecialist** | `agents/sentiment_specialist.py` | Sentimento retail. LS-Ratio + Funding Rate (sem LLM) |

### 2.4 Agentes de Infraestrutura

| Agente | Arquivo | Funcao |
|--------|---------|--------|
| **FleetAudit** | `agents/fleet_audit.py` | Paridade de estado. Reconciliacao 20s, Early ROI Panic (-80% em <300s), limpeza de fantasmas |
| **Quartermaster** | `agents/quartermaster.py` | Classificacao de leverage por wick: SMOOTH (<0.45, 50x), JUMPY (0.45-0.70, 20x), EXTREME (>0.70, 10x) |
| **HermesAgent** | `agents/hermes_agent.py` | Compliance/telemetria/chat. Cascade NVIDIA→DeepSeek→AIService, acesso MASTER_ARCHITECTURE.md + vault_galaxy |
| **JarvisBrain** | `agents/jarvis_brain.py` | Chat multi-dimensao (10 dimensoes: Trading, Filosofia, Familia, etc.) |
| **AIService** | `agents/ai_service.py` | Cascade de IA: DeepSeek → Gemini → OpenRouter (fallback para Hermes) |
| **ExecutionAuditorAgent** | `agents/execution_auditor.py` | Sentinel de Execução. Sanitiza sinais (chaves de preço), audita regras/limites de contratos OKX, força alavancagem de 50x e reporta alertas no Firebase. |
| **SandboxService** | `services/sandbox_service.py` | Forward Testing Lab. Espelha o sistema real com escadinha, stops adaptativos e fallback de preco. Ciclo 1s. |

### 2.5 Phase Detector (V120 — Explosao de Precos)

| Componente | Arquivo | Funcao |
|------------|---------|--------|
| **PhaseDetector** | `services/phase_detector.py` | Deteccao de Fase 1 (Acumulacao) e Fase 2 (Compressao) para antecipar movimentos explosivos 4-10% |

**Por que existe:** O sistema so detectava Fase 3 (detonacao). Muitas vezes o preco ja explodia antes do sinal ser gerado. Agora detectamos as fases anteriores para entrar mais cedo.

**Fase 1 — Acumulacao (institucional oculto):**
- OI Divergence: preco cai mas OI sobe (peso 25)
- CVD Divergence: preco cai mas CVD sobe (peso 30)
- Volume Trend: volume medio > 1.2x da media (peso 20)
- Funding negativo: < -0.05% (peso 15)
- Choch Detection: ruptureura de strutura (peso 10)
- Score >= 40 = Fase 1 detectada

**Fase 2 — Compressao (mola comprimida):**
- BB Width: percentil < 25% (peso 30)
- Range Compression: range近期 < 0.7x da media (peso 35)
- Volume Dry-up: volume < 0.8x da media (peso 25)
- Score >= 50 = Fase 2 detectada

**Explosion Score (composto):**
- Formula: (Phase1 + Phase2 + Funding Bonus) / 3.33
- Funding Bonus: se funding < -0.1% ou > +0.15%, +20 pontos
- Score >= 60 = sinal de ENTRADA recomendado
- Score 40-59 = sinal de ALERTA (preparar entrada)
- Score < 40 = sem sinal

**Integracao com as 3 estrategias:**
- VELOCITY FLOW: explosion_score alimenta confianca
- ALPHA SHIELD: explosion_score confirma DVAP/MOLA/FAS
- DECOR SHADOW: explosion_score detecta divergencias com compressao

---

## 3. Fluxo de Execucao

```
Sinal Gerado (Radar/BlitzSniper)
    |
    v
CaptainAgent (Quality Gate)
    |-- Consenso de frota: Macro 15% + Whale 25% + SMC 30% + OnChain 30%
    |-- Threshold dinamico: 35% (2+ slots livres) ou 40% (normal)
    |-- Quartermaster: classificacao de wick -> leverage
    |
    v
BankrollGuardian (Autorizacao)
    |-- Regime gating: ADX < 25 = so DECOR; >= 25 = so VELOCITY/ALPHA. [V124.6] BLITZ bypass em LATERAL
    |-- Limites de slots: 20 (ranging) / 40 (trending)
    |-- Memoria por par: wins/losses, ROI medio, quarentena
    |-- Equity viva: base + realizado + PnL slots + PnL moonbags
    |
    v
BankrollManager (Execucao)
    |-- Stop inicial adaptativo: ATR + suporte/resistencia
    |-- Teto de stop: 30% ROI (config)
    |-- ExecutionCapacityGate: spread, profundidade, slippage, funding
    |-- Fila OKX (anti-429): OKXCommandQueue
    |
    v
FlashAgent (Gestao de Stops)
    |-- Ciclo: 1s por slot
    |-- Escadinha: progressao de stops por ROI
    |-- Peak ROI: memoria de pico para decisao
    |-- Confirmacao REST: quando WebSocket inconsistente
    |
    v
FleetAudit (Reconciliacao)
    |-- Ciclo: 20s
    |-- Early ROI Panic: -80% em <300s = saida emergencial
    |-- Ghost cleanup: slots sem ordem correspondente
```

---

## 4. Escadinha de Stops (Stop Ladder)

As escadinhas sao definidas em `order_projection_service.py`. Tres escadinhas coexistem: LATERAL (SCALPING), LATERAL (SWING) e TRENDING.
A selecao da escada correta e feita pelo `slot_type` do sinal — funcoes `get_stop_ladder()`, `get_active_level()`, `get_next_level()`, `get_phase()` aceitam `slot_type` como parametro.

### 4.1 Regime LATERAL (ADX < 25) — Scalping (padrao)

`ORDER_STOP_LADDER_RANGING` — usada por slots sem `slot_type=BLITZ_30M`. Degraus progressivos com folga calibrada.

| Gatilho ROI | Stop (ROI) | Nome | Status |
|------------|-----------|------|--------|
| 8% | 2% | GARANTIA_TAXAS | RISCO_ZERO |
| 12% | 5% | GARANTIA_LUCRO_CURTO | RISCO_ZERO |
| 20% | 10% | GARANTIA_LUCRO_MEDIO | RISCO_ZERO |
| 32% | 18% | GARANTIA_LUCRO_ALTO | RISCO_ZERO |
| 50%+ | Trailing (-2% do pico) | ALVO_MAXIMO_LATERAL | PROFIT_LOCK |

### 4.2 Regime LATERAL (ADX < 25) — Swing (Blitz M30)

`ORDER_STOP_LADDER_RANGING_SWING` — [V124.6] usada quando `slot_type=BLITZ_30M`. Gaps 2x maiores para dar tempo do ADX evoluir de LATERAL para TRENDING. Swing usa 20x leverage, entao stops em % ROI representam ~1/2.5 do movimento de preco vs 50x.

| Gatilho ROI | Stop (ROI) | Nome | Status |
|------------|-----------|------|--------|
| 16% | 2% | GARANTIA_TAXAS | RISCO_ZERO |
| 25% | 10% | GARANTIA_LUCRO_CURTO | RISCO_ZERO |
| 40% | 20% | GARANTIA_LUCRO_MEDIO | RISCO_ZERO |
| 60% | 35% | GARANTIA_LUCRO_ALTO | RISCO_ZERO |
| 80%+ | Trailing (-5% do pico) | ALVO_MAXIMO_SWING | PROFIT_LOCK |

### 4.3 Regime TENDENCIA (ADX >= 25)

`ORDER_STOP_LADDER_TRENDING` — Degraus progressivos para colher lucros em tendencia forte.

| Gatilho ROI | Stop (ROI) | Nome | Status |
|------------|-----------|------|--------|
| 14% | 2% | GARANTIA_TAXAS | RISCO_ZERO |
| 25% | 10% | GARANTIA_20 | RISCO_BAIXO |
| 40% | 20% | LUCRO_INICIAL | RISCO_ZERO |
| 60% | 40% | LUCRO_MEDIO | RISCO_ZERO |
| 80% | 60% | LUCRO_ALTO | RISCO_ZERO |
| 100% | 80% | LUCRO_GARANTIDO_100 | RISCO_ZERO |
| 130% | 110% | SUCESSO_TOTAL | PROFIT_LOCK |
| 150% | 110% | ALVO_150 | PROFIT_LOCK |
| 200% | 150% | WAVE | TRAIL_LOCK |
| 300% | 220% | ROCKET | TRAIL_LOCK |
| 400% | 280% | STAR | TRAIL_LOCK |
| 500% | 350% | CROWN | TRAIL_LOCK |
| 600% | 420% | SUPERNOVA | TRAIL_LOCK |
| 700% | 500% | GOD_MODE | TRAIL_LOCK |
| 750% | 600% | CHOKE_PREP | TRAIL_LOCK |
| 800% | 650% | CHOKE | TRAIL_LOCK |
| 1000% | 800% | HYPER | TRAIL_LOCK |
| 1200% | 1000% | APEX | TRAIL_LOCK |
| 100% | 75% | LUCRO_GARANTIDO | ESCADINHA |
| 130% | 110% | SUCESSO_TOTAL | PROFIT_LOCK |
| 150% | 110% | ALVO_150 | PROFIT_LOCK |
| 200% | 150% | WAVE | TRAIL_LOCK |
| 300% | 220% | ROCKET | TRAIL_LOCK |
| 400% | 280% | STAR | TRAIL_LOCK |
| 500% | 350% | CROWN | TRAIL_LOCK |
| 600% | 420% | SUPERNOVA | TRAIL_LOCK |
| 700% | 500% | GOD_MODE | TRAIL_LOCK |
| 750% | 600% | CHOKE_PREP | TRAIL_LOCK |
| 800% | 650% | CHOKE | TRAIL_LOCK |
| 1000% | 800% | HYPER | TRAIL_LOCK |
| 1200% | 1000% | APEX | TRAIL_LOCK |

### 4.3 Pos-APEX (acima de 1200%)

Niveis `ULTRA_*` a cada 200% ROI. Stop = gatilho - 200%.

| Gatilho | Stop |
|---------|------|
| ULTRA_1400 | +1200% |
| ULTRA_1600 | +1400% |
| ULTRA_1800 | +1600% |
| ULTRA_2000 | +1800% |

---

## 5. Filtro de Regime de Mercado

### 5.1 Grade ADX

**[V123] Regime gating RESTAURADO no Sandbox.** DECOR SHADOW opera APENAS em LATERAL (ADX < 25).
- Motivo: DECOR SHADOW é estratégia de reversão/exaustão — em TRENDING, o preço pode continuar caindo livremente.
- ALPHA SHIELD e VELOCITY FLOW operam em qualquer regime.
- **[V124.6] BLITZ (BlitzSniper M30) bypassa o regime gating em LATERAL** — `captain.py` libera sinais com `is_blitz=True` ou `slot_type=BLITZ_30M` mesmo em ADX < 25, permitindo que swings 30M entrem antes do ADX evoluir para trending.

| Condicao | Acao |
|----------|------|
| ADX < 25 | LATERAL: todas as estrategias permitidas + BLITZ bypass |
| ADX >= 25 | TENDENCIA: apenas VELOCITY FLOW e ALPHA SHIELD (DECOR SHADOW bloqueado) |

**Filtro adicional V118 para LONGS:**
- Apenas pares desgrudados do BTC (Pearson < 0.35) com gas (confidence >= 70)
- LONGS aprovados tambem furam o MACRO-BLOCK

### 5.2 Direcao do BTC

Determinada por confluencia de variacao 15m + 1h:
- Ambas positivas => UP
- Ambas negativas => DOWN
- Divergencia => LATERAL (nao bloqueia)

### 5.3 Filtro Trend Bias

- Preco BTC < SMA 200 diaria => BEARISH: so SHORT permitido
- Preco BTC > SMA 200 diaria => BULLISH: so LONG permitido

---

## 6. Estrategias

| Estrategia | Regime | Descricao |
|------------|--------|-----------|
| **VELOCITY FLOW** (M30) | LATERAL+BLITZ | [V124.7] Swing 30M via SignalGenerator — SMA8/21 alinhado + volume |
| **ALPHA SHIELD** (M30) | LATERAL+BLITZ | [V124.7] Swing 30M via SignalGenerator — DVAP/MOLA/FAS/LRT |
| **DECOR SHADOW** (M30) | LATERAL+BLITZ | [V124.7] Swing 30M via SignalGenerator — CVD exhaustion + RSI extremo |
| **DECOR SHADOW** | LATERAL | Reversao de exaustao, decorrelacao BTC (Pearson < 0.35) |
| **DECOR_HUNTER** | LATERAL | Variacao do DECOR com caça a decorrelacao |
| **VELOCITY FLOW** | TENDENCIA | Momentum de alta, breakout de volatilidade |
| **ALPHA SHIELD** | TENDENCIA | Protecao de capital, entrada em pullback |
| **LRT** | Qualquer | Liquidez de alta frequencia |
| **DVAP** | Qualquer | Reversao de exaustao |
| **FAS** | Qualquer | Funding Squeeze (isento de alinhamento SMA 2H) |
| **MOLA** | Qualquer | Breakout de volatilidade |
| **ABCD / 1-2-3** | TENDENCIA | Tendencias geometricas |

---

## 7. Constantes Principais

### 7.1 Trading

| Constante | Valor | Fonte |
|-----------|-------|-------|
| Leverage padrao | 50x | `config.py` |
| Max slots (config) | 16 | `config.py:124` |
| Max slots (guardian ranging) | 20 | `bankroll_guardian.py` |
| Max slots (guardian trending) | 40 | `bankroll_guardian.py` |
| Margem lateral | $2.00 | `bankroll.py:54` |
| Margem trending | $1.00 | `bankroll.py:55` |
| Teto stop inicial | 30% ROI | `config.py:145` |
| Min gap entre entradas | 2s | `signal_generator.py` |
| Intervalo de scan | 5s | `signal_generator.py` |

### 7.2 Oracle & Regime

| Constante | Valor | Fonte |
|-----------|-------|-------|
| Periodo de estabilizacao | 150s | `oracle_agent.py` |
| ADX trending | 25 | `oracle_agent.py` |
| ADX minimo para entrada | 22 | `config.py:139` |
| ADX forte tendencia | 30 | `config.py:143` |

### 7.3 FlashAgent

| Constante | Valor | Fonte |
|-----------|-------|-------|
| Ciclo de trailing | 1s | `flash_agent.py` |
| TTL cache slots | 3s | `flash_agent.py` |
| Intervalo check DECOR | 60s | `flash_agent.py` |
| [V124.6] Partial TP SCALPING (LATERAL) | +15% ROI | `flash_agent.py:251` |
| [V124.6] Partial TP SWING (BLITZ_30M) | +30% ROI | `flash_agent.py:251` |

### 7.4 FleetAudit

| Constante | Valor | Fonte |
|-----------|-------|-------|
| Intervalo reconciliacao | 20s | `fleet_audit.py:24` |
| Periodo imunidade (novos) | 60s | `fleet_audit.py:88` |
| Early panic (idade < 300s) | -80% ROI | `fleet_audit.py:91` |
| Saida emergencia | -90% ROI | `fleet_audit.py:96` |
| Tolerancia desvio SL | 0.2% | `fleet_audit.py:152` |

### 7.5 Librarian

| Constante | Valor | Fonte |
|-----------|-------|-------|
| Intervalo de estudo | 7200s (2h) | `librarian.py:37` |
| Quarantena super | 14400s (4h) | `librarian.py:92` |
| Janela padrao negativa | 259200s (72h) | `librarian.py:106` |
| Top rankings | 25 | `librarian.py:408` |
| Download klines (fresh) | 1500 candles | `librarian.py:244` |

### 7.6 MacroAnalyst

| Constante | Valor | Fonte |
|-----------|-------|-------|
| Cache dominancia BTC | 600s (10min) | `macro_analyst.py:45` |
| Cache klines | 300s (5min) | `macro_analyst.py:98` |
| Threshold correlacao (panic) | 0.8 | `macro_analyst.py:129` |
| Threshold queda BTC (panic) | -2.0% em 1H | `macro_analyst.py:130` |
| Risk score range | 0-10 | `macro_analyst.py:225` |

### 7.7 WhaleTracker

| Constante | Valor | Fonte |
|-----------|-------|-------|
| Bull trap: CVD delta | > 40.000 + preco < 0.03% | `whale_tracker.py:75` |
| Bear trap: CVD delta | < -40.000 + preco > -0.03% | `whale_tracker.py:80` |
| Whale pulse | >= 150.000 CVD | `whale_tracker.py:86` |
| Presenca alta | abs(CVD) > 100.000 | `whale_tracker.py:99` |

### 7.8 AI Service

| Constante | Valor | Fonte |
|-----------|-------|-------|
| Rate limit visao | 10 RPM | `ai_service.py:29` |
| Timeout Gemini | 15s | `ai_service.py:218` |
| Timeout OpenRouter | 20s | `ai_service.py:256` |
| Backoff Gemini 429 | 120s | `ai_service.py:174` |
| Cascade | DeepSeek -> Gemini -> OpenRouter | `ai_service.py` |

---

## 8. Watchlists

### 8.1 RADAR_WATCHLIST (31 ativos)
Pares monitorados ativamente para sinais de trading.

### 8.2 ELITE_40_MATRIX (35 ativos)
Pares elite com alavancagem 50x na OKX.

### 8.3 DECOR_WATCHLIST (89 ativos)
Pares para estrategia de decorrelacao.

### 8.4 ASSET_BLOCKLIST
Ativos bloqueados permanentemente: DYDXUSDT, FILUSDT, ALGOUSDT, LTCUSDT.

### 8.5 Memecoin Blacklist
PEPE, DOGE, SHIB, FLOKI, BONK, WIF, MYRO, 1000SATS, ORDI, MEME, TURBO, PEOPLE.

---

## 9. Mapa de Setores

| Setor | Simbolos |
|-------|----------|
| AI | FET, AGIX, OCEAN, RNDR, NEAR, ROSE, TAO, GRT, AI, NFP, WLD, ARKM |
| MEME | PEPE, DOGE, SHIB, FLOKI, BONK, WIF, MYRO, 1000SATS, ORDI, MEME, TURBO, PEOPLE |
| L1 | BTC, ETH, SOL, ADA, DOT, AVAX, MATIC, LINK, BNB, ATOM, FTM, OP, ARB, APT, SUI, SEI, NEAR |
| DEFI | UNI, MKR, AAVE, SNX, LDO, JUP, RUNE, INJ, DYDX, CRV, 1INCH, GMX |
| INFRA | TIA, FIL, AR, GRT, DYM, PYTH, ALT |
| GAMEFI | IMX, BEAM, GALA, AXS, SAND, MANA, RON, APE |
| DEPIN | HNT, IOTX, POWR |
| PAYMENTS | TRX, XRP, LTC |

---

## 10. Endpoints da API

### 10.1 Market (`/api`)
| Metodo | Path | Descricao |
|--------|------|-----------|
| GET | `/api/elite-pairs` | Pares elegiveis 50x OKX |
| GET | `/api/btc/regime` | Regime BTC |
| GET | `/api/radar/pulse` | Sinais radar pulse |
| GET | `/api/radar/grid` | Grid de radar de mercado |
| GET | `/api/radar/librarian` | Inteligencia/rankings Librarian |
| GET | `/api/radar/regimes` | Analise de regime por par (60s cache) |
| GET | `/api/captain/tocaias` | Simbolos ativos em ambush |
| GET | `/api/trend/{symbol}` | Analise de tendencia 1H |
| GET | `/api/market/klines` | Proxy de klines (15m-4H) |
| GET | `/api/system/state` | Estado completo do sistema (1s cache) |
| GET | `/api/market/study` | Estudo com padroes/FVG/OB |

### 10.2 Trading
| Metodo | Path | Descricao |
|--------|------|-----------|
| GET | `/api/slots` | Todos os slots (publico) |

### 10.3 Sandbox (`/api/sandbox`)
| Metodo | Path | Descricao |
|--------|------|-----------|
| GET | `/api/sandbox/trades` | Listar trades sandbox (param: active_only) |
| GET | `/api/sandbox/stats` | Estatisticas gerais + regime atual + breakdown por estrategia |
| GET | `/api/sandbox/patterns` | Analise de padroes: whitelist/blacklist sugerida, win rate por direcao |
| GET | `/api/sandbox/analytics` | Analytics detalhado: loss por regime, simbolo, hora UTC, risk/reward |
| POST | `/api/sandbox/clear` | Limpar todo o historico sandbox |

### 10.4 Vault (`/api/vault`)
| Metodo | Path | Descricao |
|--------|------|-----------|
| POST | `/api/vault/save` | Salvar chaves encriptadas |
| GET | `/api/vault/status` | Status do vault |

### 10.5 Admin (`/api/admin`)
| Metodo | Path | Descricao |
|--------|------|-----------|
| GET | `/api/admin/users` | Listar usuarios (admin) |
| GET | `/api/admin/stats` | Stats do sistema |
| POST | `/api/admin/user/{username}/status` | Atualizar status usuario |
| POST | `/api/admin/lockdown` | Toggle lockdown |
| POST | `/api/admin/reset-system` | Nuclear reset |

### 10.6 Auth
| Metodo | Path | Descricao |
|--------|------|-----------|
| POST | `/login` | Login (JWT) |
| POST | `/register` | Registro (aprovacao pendente) |
| POST | `/refresh` | Refresh token |
| POST | `/logout` | Logout |
| GET | `/me` | Perfil usuario atual |
| POST | `/change-password` | Trocar senha |
| GET | `/users` | Listar usuarios (admin, paginado) |
| PUT | `/users/{user_id}/role` | Mudar role |
| DELETE | `/users/{user_id}` | Deletar usuario |
| POST | `/users/{user_id}/approve` | Aprovar usuario |
| POST | `/users/{user_id}/block` | Bloquear usuario |

### 10.7 Chat
| Metodo | Path | Descricao |
|--------|------|-----------|
| POST | `/api/hermes/chat` | Hermes chat (primario) |
| POST | `/api/hermes/compliance` | Forcar compliance check |
| GET | `/api/hermes/status` | Status Hermes |
| POST | `/api/chat` | Chat Jarvis legado |
| POST | `/api/chat/manual` | Chat manual com dimensoes |
| POST | `/api/chat/reset` | Resetar historico (API key) |
| GET | `/api/chat/status` | Status chat |
| POST | `/api/tts` | Text-to-speech |
| GET | `/api/tts/voices` | Vozes TTS |

### 10.8 System
| Metodo | Path | Descricao |
|--------|------|-----------|
| GET | `/api/test` | Teste basico |
| GET | `/api/debug/test` | Debug teste |
| GET | `/api/health` | Health check (VERSION, DEPLOYMENT_ID) |

---

## 11. Camadas de Dados

| Banco | Funcao | Tabelas Principais |
|-------|--------|-------------------|
| PostgreSQL | SSOT persistente | `slots`, `radar_pulse`, `banca_status`, `sandbox_trades`, `moonbags`, `chat_sessions`, `chat_messages` |
| Firebase Firestore | Multi-tenant, sync nuvem | `users`, `trade_history`, `trade_analytics`, `fleet_intelligence`, `vault_history` |
| Firebase RTDB | Estado em tempo real | `system_state`, `active_slots`, `radar_pulse`, `chat_status`, `banca` |
| SQLite | Cache de klines (librarian) | `klines` |

---

## 12. Deploy

| Componente | Valor |
|------------|-------|
| Plataforma | Railway + Docker |
| Python | 3.12-slim |
| PORT | 8085 |
| Procfile | `web: python main.py` / `worker: python worker.py` |
| Health Check | `GET /api/health` |
| Entry (Docker) | `uvicorn backend.main:app --host 0.0.0.0 --port 8085` |
| Entry (Railway) | `python main.py` |

---

## 13. Contradicoes Conhecidas no Codigo

1. ~~**RISK_ZERO**: `chat.py` diz 80% ROI, `hermes_agent.py` diz 50% ROI~~ ✅ RESOLVIDO V121: unificado em `config.py` (50% trigger → +25% stop)
2. **Versoes**: Multiplas versoes coexistem (V20.5 captain, V110.x services, V2.x hermes, etc.)
3. **Portfolio Guardian**: Importado e instanciado no `main.py` raiz mas marcado DESATIVADO
4. **Referencias Bybit legadas**: `market.py` ainda usa nomes `BybitRest`, `BybitWS`
5. **`get_slot_type()` sempre retorna "DVAP"** (V110.950)
6. ~~**Dois FastAPI apps**: Root `main.py` (Firebase-first) e `backend/main.py` (Postgres-first)~~ ✅ RESOLVIDO V120.4
7. ~~**Max slots**: `config.py` (16) vs `bankroll_guardian.py` (20/40)~~ ✅ RESOLVIDO V121: todas as camadas leem do mesmo `settings.MAX_SLOTS` (20)
8. **Reset banca**: `admin.py` diz $100 mas comentarios dizem $20
9. **`radar_pulse`**: Nao e arquivo separado — e estrutura de dados em database_service, firebase_service e websocket_service

---

## 14. Blacklist de Memecoins

`PEPE`, `DOGE`, `SHIB`, `FLOKI`, `BONK`, `WIF`, `MYRO`, `1000SATS`, `ORDI`, `MEME`, `TURBO`, `PEOPLE`
## 15. SandboxService — Forward Testing Lab

Servico que espelha o sistema real de forma fiel. Iniciado junto ao backend no startup SaaS.

### 15.1 Fluxo de entrada de sinais
```
firebase_service.update_radar_pulse(signals)
    |
    +---> asyncio.create_task(sandbox_service.on_radar_pulse(signals))
              |
              v
          _process_radar_signals()
              |-- [V120] Filtro ADX/regime: REMOVIDO — todas as estrategias livres (VELOCITY, ALPHA, DECOR)
              |-- [V120] Filtro LONGS: relaxado (Pearson < 0.50 OU confidence >= 60)
              |-- [V120] LONGs aprovados furam MACRO-BLOCK (decor_bypass)
              |-- [V120] Asian Session Penalty: ADX >= 32 entre 23h-01h UTC
              |-- Filtro macro BTC (SMA 200 diaria)
              |-- Filtro blocklist (ASSET_BLOCKLIST + auto-blocklist + V120 blacklist)
              |-- Filtro horario abertura US (13:30-14:30 UTC)
              |-- Deduplicacao por signal_id
              |-- [V114] Cooldown 300s pos stop-out por simbolo
              |-- [V118.3] Confirmacao 5M (exige maioria 2/3 alinhada com direcao)
              |-- Entry Sanity Check (preco defasado)
              |-- [V120] Stop adaptativo por regime: LATERAL -8%, TRENDING -10%
              |-- [V120] Margem adaptativa por win rate do par ($1.00-$2.50)
              +---> save_sandbox_trade()
```

### 15.2 Resolucao de preco (fallback em cascata)
```
_get_current_price(symbol):
    1. WebSocket (okx_ws_public_service.get_current_price)
    2. REST OKX  (_get_rest_price -> /api/v5/market/ticker)
    3. Cache local (60s TTL)

_check_stop_hit(side, stop_price, symbol):
    1. Conservative price HIGH/LOW 120s (captura spikes intra-ciclo)
    2. Preco atual WS
    3. Fallback 2: _get_current_price() completo (REST + cache)
```

### 15.3 Stop adaptativo por regime

| Regime | ADX | Stop Inicial (V120) | Threshold Stale Entry |
|--------|-----|----------------------|----------------------|
| LATERAL | < 25 | **-8% ROI** | ROI imediato < -5.6% (floor -10%) |
| TENDENCIA | >= 25 | **-10% ROI** | ROI imediato < -7.0% (floor -10%) |

> **[V120]**: Stops otimizados para melhorar Risk/Reward de 0.61 para ~1.0.
> - LATERAL: -8% ROI (era -10%) — menor stop = loss menor
> - TRENDING: -10% ROI (era -15%) — pullbacks precisam de espaço mas menos que antes
> - Capping de segurança: -10% ROI máximo (era -12%)
> GARANTIA_5 (+5% ROI na escadinha) leva o stop a 0% rapidamente, protegendo o capital.
> GARANTIA_TAXAS (+3% ROI) ativa break-even com 1.5% para cobrir taxas.
> O floor de -10% no stale threshold evita descartes agressivos.

- Stop price calculado via `raw_price_from_roi()` com tick_size rounding (ROUND_CEILING para SHORT negativo).
- Entry Sanity Check: se ROI imediato ao abrir ja ultrapassou 70% do stop (floor: -10%), o sinal e descartado com log `[SANDBOX-STALE]`.

### 15.4 [V114] Cooldown pos stop-out

Apos cada `CLOSED_SL`, o simbolo entra em quarentena de **300 segundos** (5 minutos).
Durante esse periodo, qualquer novo sinal para o mesmo par e descartado automaticamente.

- Dict `_stop_cooldown: Dict[str, float]` em `SandboxService.__init__`
- Populado em `_process_trade_tick` no momento do `CLOSED_SL`
- Verificado em `_process_radar_signals` apos o check `already_active`
- Log `[SANDBOX-COOLDOWN-SET]` ao ativar; `[SANDBOX-COOLDOWN]` ao bloquear
- **Objetivo**: eliminar re-entries em cadeia (INJUSDT tinha 11 stops seguidos, ATOMUSDT 4)

### 15.5 [V118.3] Confirmacao 5M com alinhamento de tendencia

Antes de abrir qualquer trade, o sandbox verifica se o TF 5M esta alinhado com a direcao do sinal.

- Metodo: `_check_5m_confirmation(symbol, side)`
- Busca os 5 ultimos candles de 5M via `okx_rest_service.get_klines(symbol, interval="5", limit=5)`
- Usa o cache de 3min do `get_klines` (sem custo extra de API)
- Analisa os **3 candles fechados mais recentes** (ignora candle aberto em formacao) = 15 min de dados
- **Exige maioria 2/3 alinhada com a direcao do sinal**:
  - **SHORT**: precisa de >= 2 bearish (close < open) de 3 candles
  - **LONG**: precisa de >= 2 bullish (close > open) de 3 candles
- Se aprovado: score_boost = +10 (3/3) ou +5 (2/3)
- Se rejeitado: trade bloqueado com log `[SANDBOX-5M-BLOCK]`
- Edge case: se todos os candles sao DOJI/UNK (sem direcao definida), fail-open (aprova)
- Comportamento em falha de API: **fail-open** (aprova o trade, nao bloqueia por instabilidade)
- Log `[SANDBOX-5M]` ao registrar confirmacao

#### Motivo da mudanca V117 -> V118.3
O filtro V117 usava 2 candles e bloqueava apenas se AMBOS iam contra o sinal (0/2 confirmando).
Isso era muito permissivo: com apenas 1/2 confirmando (50%), trades entravam com o 5M indo contra
(como NEARUSDT SHORT que bateu stop em segundos porque o 5M estava bullish).

Com 3 candles e exigencia 2/3 (66%), o filtro agora bloqueia entradas onde o 5M nao esta claramente
alinhado com a direcao do sinal.

### 15.5.1 [V114] Confirmacao 1M (desativada no sandbox)

O filtro 1M original (V114) foi substituido pelo filtro 5M (V116, depois V118.3) por ser mais limpo e menos ruidoso.
O metodo `_check_1m_confirmation` ainda existe no codigo mas nao e chamado no fluxo normal.

### 15.6 Gestao de stops (paridade FlashAgent)
- **Peak ROI**: `max(current_roi, cached_peak, stored_peak)` — nao perde picos entre reinicializacoes.
- **Escadinha**: usa `OrderProjectionService.get_stop_ladder()` + `get_active_level()` — **identico ao FlashAgent real**. As funcoes aceitam `slot_type` para selecionar a escada correta (RANGING / RANGING_SWING / TRENDING).
- **Saida parcial lateral**: ao atingir +15% ROI em regime LATERAL, registra `has_taken_partial=True`; PnL final = media 50/50.
- **[V124.6] Saida parcial BLITZ_30M**: threshold de +30% ROI (vs +15% scalping), definido em `flash_agent.py:251` por `slot_type`.
- **Confirmacao REST antes de fechar**: apos `stop_hit=True`, busca preco fresco via REST antes de persistir o fechamento.
- **Auto-blocklist [V118]**: pares com PnL total < -15% E win rate < 35% apos 3+ trades bloqueados automaticamente em runtime (era 5/20/30). Verificado a cada 120s.
- **Transicao Fria ADX [V119]**: Ao mudar do regime de tendência para lateral, bloqueia novos sinais laterais por 15min (900s) para estabilização de volatilidade.
- **Espelhamento em Conta Real [V124.4]**: Se `OKX_API_KEY_MASTER` e `REAL` mode estiverem ativos, replica ordens a mercado, cruzadas e com 50x de alavancagem na OKX. O processo é auditado pelo **ExecutionAuditorAgent (Sentinel)**, que corrige chaves de preço corrompidas do webhook (ex: `entry_price_signal`), calibra quantidades segundo regras de contratos da OKX e barra ordens com margem acima do saldo da banca real, notificando no Firebase.

### 15.7 Constantes do SandboxService (V120)

| Constante | Valor | Localizacao |
|-----------|-------|-------------|
| Ciclo de monitoramento | 1s | `sandbox_service.py` |
| Banca virtual | **$100.00 USD** | `routes/sandbox.py:49` (`BANCA = 100.0`) |
| Margem media por trade | **$2.00** | `routes/sandbox.py:50` (`MARGEM_MEDIA = 2.0`) |
| Margem adaptativa | **$1.00-$2.50** (por win rate do par) | `sandbox_service.py:_get_adaptive_margin()` |
| Leverage (sandbox) | 50x | `sandbox_service.py` |
| Janela conservative price | 120s | `okx_ws_public.py:291` |
| TTL cache de preco | 60s | `sandbox_service.py` |
| [V120] Stop inicial LATERAL | **-8% ROI** (era -10%) | `sandbox_service.py` |
| [V120] Stop inicial TRENDING | **-10% ROI** (era -15%) | `sandbox_service.py` |
| [V120] Capping stop | **-10% ROI** (era -12%) | `sandbox_service.py` |
| Threshold stale entry | 70% do stop (floor -10%) | `sandbox_service.py` |
| [V119] Cooldown pos stop-out | **3600s (1 hora)** (impede re-entry consecutivo no mesmo par sob estresse) | `sandbox_service.py` |
| [V119] Cooldown transicao ADX | **900s (15 min)** do modo tendência para lateral (evita volatilidade residual) | `sandbox_service.py` |
| [V118.3] Candles 5M para confirmacao | 3 fechados (5 buscados), exige 2/3 alinhados com direcao | `sandbox_service.py` |
| [V120] Filtro LONGS | Pearson < 0.50 OU confidence >= 60 (era AND com 0.35/70) | `sandbox_service.py` |
| [V120] Asian Session Penalty | ADX >= 32 entre 23h-01h UTC | `sandbox_service.py` |
| [V120] GARANTIA_TAXAS | +3.0% ROI (era +3.5%) | `sandbox_service.py` |
| [V120] Partial TP TRENDING | +25% ROI (novo, era só LATERAL +15%) | `sandbox_service.py` |
| [V124.6] Partial TP BLITZ_30M | +30% ROI (vs +15% scalping) | `flash_agent.py:251` |
| Polling frontend | 2s | `sandbox.html` |
| Polling patterns | 5s | `sandbox.html` |
| Placeholder banca (HTML) | **$100.00 USD** | `sandbox.html:158` |
| Auto-blocklist check | 120s | `sandbox_service.py` |
| [V118] Auto-blocklist criterio | PnL < -15% E WR < 35% apos 3+ trades | `sandbox_service.py` |
| [V120] Static blocklist novos | ADA, GALA, ARB, OP, POL, NEAR | `config.py:ASSET_BLOCKLIST` |

### 15.8 Logs esperados no comportamento normal

| Log | Significado |
|-----|-------------|
| `[SANDBOX-OPEN]` | Trade aberto com Entry, SL, MktPrice, TickSize |
| `[SANDBOX-STALE]` | Sinal descartado — entry defasado (ROI imediato < threshold) |
| `[SANDBOX-TRANSITION-BLOCK]` | Sinal de contra-tendencia bloqueado por cooldown de transicao fria (900s) |
| `[SANDBOX-MIRROR-OPEN]` | Replicando abertura da ordem simulada na conta real da OKX |
| `[SANDBOX-MIRROR-CLOSE]` | Replicando fechamento/stop da ordem simulada na conta real da OKX |
| `[SANDBOX-FLASH]` | Degrau da escadinha ativado |
| `[SANDBOX-PARTIAL]` | Saida parcial 50% executada em lateral |
| `[SANDBOX-LOSS]` | Trade fechado no stop (com ROI, Entry, Exit, MaxROI) |
| `[SANDBOX-PRICE-UNAVAILABLE]` | Preco indisponivel em WS + REST + cache — trade pulado |
| `[SANDBOX-COOLDOWN-SET]` | Cooldown de 300s registrado apos stop-out |
| `[SANDBOX-COOLDOWN]` | Sinal bloqueado — simbolo em cooldown (com segundos restantes) |
| `[SANDBOX-5M]` | Confirmacao 5M: boost de score aplicado (+5 ou +10) |
| `[SANDBOX-BLOCKLIST]` | Simbolo bloqueado por blocklist estatica ou auto-blocklist |
| `[SANDBOX-MACRO-BLOCK]` | Sinal bloqueado por filtro macro BTC (SMA 200) |
| `[SANDBOX-OPEN-FILTER]` | Sinal bloqueado por filtro de abertura US (13:30-14:30 UTC) |
| `[SANDBOX-AUTO-BLOCKLIST]` | Par bloqueado automaticamente por performance critica |
| `[SANDBOX-V120-LONG]` | LONG descartado — filtro de decorrelação relaxado não atendido |
| `[SANDBOX-ASIAN-PENALTY]` | Sinal bloqueado — sessão asiática (23h-01h UTC) com ADX < 32 |

### 15.9 Bugs corrigidos (historial)

| Bug | Commit | Descricao |
|-----|--------|-----------|
| WS=0 nao detectava stop | `5d77b0f` | `_check_stop_hit` nao consultava REST/cache quando WS retornava 0. Fix: Fallback 2 com `_get_current_price()` |
| Analytics: typo `fase` | `7175a80` | `state.get("fase")` deveria ser `state.get("phase")`. Fix: corrigido em `routes/sandbox.py:158` |
| Entry stale (MaxROI=0%) | `d92c28f` | Sandbox abria trades com preco de mercado ja alem do stop. Fix: Entry Sanity Check 70% do stop |
| Re-entries em cadeia | `855fcec` | INJUSDT/ATOM abriam identicos apos stop-out imediato. Fix: Cooldown 300s por simbolo (V114) |
| Entrada contra momentum | `855fcec` | Trades abriam com candles 1M indo na direcao oposta ao sinal. Fix: Confirmacao 1M 2/3 candles (V114) |
| Captain UnboundLocalError | V116 | `_run_user_execution_logic` crashava com `settings` nao importado. Fix: `from config import settings` no topo da funcao |
| MACRO-BLOCK impossivel bypass | V116 | DECOR SHADOW bloqueada por pearson > 0.85 (bypass impossivel). Fix: MACRO-BLOCK desativado em LATERAL, high_score_bypass em TRENDING |
| 1M-REJECT 100% sinais | V116 | Filtro 1M requeria 2/3 candles confirmando mas quase sempre 0/3 confirmavam. Fix: Substituido por 5M confirmation (boost, nao bloqueia) |
| Regime gating + GARANTIA_5 + LONGS filter | V118 | 100% VELOCITY FLOW, LONGS perdendo, escadinha nao capturava lucro. Fix: regime gating removido, GARANTIA_5 (break-even +5%), LONGS exigem decorrelacao+gas, auto-blocklist mais agressivo |
| 5M muito permissivo (NEARUSDT stops) | V118.3 | V117 usava 2 candles e so bloqueava se 0/2 confirmavam — trades entravam contra o 5M. Fix: 3 candles com exigencia 2/3 de alinhamento com direcao do sinal |
| Stop -10%/-15% ainda apertados (0% win rate sandbox) | V119 | Stops fixos nao respeitam estrutura 30M. Fix: stop estrutural baseado em swing low/high do TF 30M com buffer 0.15% |
| R:R 0.61, 100% SHORT, 0% ALPHA/DECOR | V120 | Stops muito largos (-12%/-15%), regime gating bloqueava estratégias, filtro LONG too restritivo. Fix: stops -8%/-10%, regime gating removido, filtro LONG relaxado (OR), Asian penalty, margem adaptativa, partial TP em TRENDING |
| Falhas Silenciosas no Sandbox Mirror | V124.4 | Sinais sem chave "price" (apenas "entry_price_signal") resultavam em 0.0, causando divisao por zero e travando o circuit breaker. Alavancagem tambem nao era setada na API. Fix: Auditoria pelo ExecutionAuditorAgent (Sentinel), sanitizacao de chaves, pre-configuracao de 50x e alertas no Firebase. |
| Altcoins M30 (Swing) travadas/stops curtos | V124.5 | O scan M30 (Blitz) era pausado se o BTC estivesse lateral. A alavancagem de 50x forçada limitava o stop inicial a 0.6% de preço (muito apertado para SUI). Fix: Removido pausa no scan em lateral, alavancagem de Swing definida para 20x (liberando stops de até 4.0% preço). |
| Blitz M30 bloqueado em LATERAL (Captain gates) | V124.6 | Sinais BLITZ_30M eram barrados pelos dois gates de regime em `captain.py` (ADX < 25 bloqueava VELOCITY/ALPHA, e segundo gate TREND_FOCUS). Fix: `is_blitz` bypass nos dois gates + escadinha `ORDER_STOP_LADDER_RANGING_SWING` com gaps 2x maiores + partial TP em +30% ROI no FlashAgent por `slot_type`. |
| BlitzSniperAgent substituido pelo SignalGenerator | V124.7 | BlitzSniperAgent removido — usava apenas SMA9/21 crossover com scoring simples (score >= 75). Substituido por `SignalGenerator.analyze_m30_swing()` que reusa toda a infraestrutura de deteccao de padroes do motor principal: DVAP/MOLA/FAS/LRT (ALPHA SHIELD), TREND (VELOCITY FLOW), DECOR (DECOR SHADOW). Score minimo reduzido para 65. Escadinha RANGING_SWING + partial TP 30% + `slot_type=BLITZ_30M` mantidos. |
| Motor Autônomo Swing Lab V2.0 e Scalping Lab V125.3 | V125.3 | Remoção completa do `blitz_sniper.py`. Criação do `sandbox_swing_service.py` (scan M30 a cada 5min com Zero-Risk Stacking de capacidade 2) e `sandbox_scalping_engine.py` (VWAP SNIPER no gráfico M1/M5 com ATR stops e sem saídas parciais). Exclusão do boot-shield no Cockpit, criação de botão Clear All no histórico do Vault, e responsividade mobile de layouts. |

---

## 16. Scalping Lab — VWAP SNIPER (V125.3)

O motor de scalping micro roda sob o arquivo `services/sandbox_scalping_engine.py`. É um processo autônomo paralelo de alta frequência.

### 16.1 Regras de Entrada
- **Ciclo:** Varredura a cada 60 segundos (M1/M5).
- **Filtro de Tendência (M5):** O preço deve estar acima (para LONG) ou abaixo (para SHORT) da EMA 200 no tempo gráfico de 5 minutos.
- **Zona de Gatilho (M1):** O preço deve tocar a linha de VWAP diário no gráfico de 1 minuto.
- **Oscilador de Entrada (M1):** Stochastic RSI no gráfico de 1 minuto deve confirmar sobrecompra/sobrevenda (<20 para LONG, >80 para SHORT).
- **Liquidity Sweeps (Boost):** Varredura de liquidação no livro (+15 pontos de score de momentum).

### 16.2 Regras de Saída e Gestão de Risco
- **Sem Saídas Parciais:** Para otimizar o ganho máximo no momentum imediato, as ordens de Scalping correm com **100% da mão com alavancagem de 50x** isolada até serem fechadas diretamente pelo Stop Loss ou Stop Gain.
- **Stop Loss Baseado em Volatilidade (ATR):** O Stop Loss é calculado dinamicamente com base no ATR recente, evitando stops fixos arbitrários em momentos de alta volatilidade.

---

## 17. Swing Lab — Motor Primário M30 (V125.3)

O robô de Swing Lab funciona de forma autônoma em `services/sandbox_swing_service.py`.

### 17.1 Regras de Entrada e Watchlist
- **Ciclo:** Varredura a cada 5 minutos no gráfico de 30 minutos.
- **Indicadores Confluentes:** Integração direta com o `SignalGenerator.analyze_m30_swing()`.
- **Fibonacci Golden Zone:** Confluência na região de ouro da Fibonacci de M30 (+20 pontos).
- **Price Action M30:** Padrões harmônicos e de velas de reversão em M30 (+15 pontos).
- **Margem Dinâmica:** Alocação de margem de **$5.00 USD** por trade virtual.

### 17.2 Zero-Risk Stacking (Capacidade 2)
Para limitar a exposição ao risco sistêmico de mercado, foi implementada uma trava de Stacking:
- **Limite de Risco:** O motor permite no máximo **2 posições simultâneas expostas a risco** (onde o Stop Loss atual está abaixo do preço de entrada).
- **Bloqueio:** Se houver 2 ordens sob risco, o ciclo de novas entradas é pausado.
- **Desbloqueio:** Novas entradas são liberadas imediatamente quando pelo menos uma das posições existentes tem o seu Stop Loss movido para o Break-even ou superior pelo FlashAgent (garantindo risco zero na operação).

---

## 18. Refinamentos Visuais & UX Cockpit (V125.3)

### 18.1 Velocidade e Carregamento (Sem Boot Shield)
- O elemento `#boot-shield` (tela preta com logo e mensagens de inicialização do Babel) foi completamente removido do [cockpit.html](file:///c:/Users/spcom/Desktop/1C-7.0/frontend/cockpit.html). A interface principal carrega instantaneamente.

### 18.2 Limpeza Completa do Histórico (Vault History)
- Adicionado o botão `delete_sweep` (ícone de vassourinha) no bloco do histórico do cockpit.
- Rota dedicada `DELETE /api/history/clear/all` que remove registros do Postgres, RTDB e documentos do Firestore.

### 18.3 Responsividade Mobile
- **Header Adaptativo:** Títulos e botões de controle quebram em colunas em viewports estreitos.
- **Grids Fluidos:** O grid de ativos no observatório (`observatory.html`) altera dinamicamente entre 3, 5 e 10 colunas dependendo do tamanho da tela do dispositivo.
- **Cards de Status Reorganizados:** O painel de *Patrimônio Líquido* e *Guardião da Banca* foi redesenhado em cartões simétricos discretos (`bg-white/[0.02]`) com barras de integridade de gradiente fluido.

---

## 19. Memory Galaxy — Obsidian Second Brain (V125.4)

O sistema de memória persistente e auto-documentada foi implementado para conectar notas markdown estruturadas com conexões do Obsidian em `vault_galaxy/`.

### 19.1 Componente e Serviços
- **`services/galaxy_memory_service.py`:** Gerenciador do cofre Obsidian. Cria diretórios e formata os arquivos em Markdown com propriedades no frontmatter e tags associativas.

### 19.2 Estrutura da Galáxia
- **`vault_galaxy/trades/`:** Registra cada operação realizada.
- **`vault_galaxy/journal/`:** Agrupa eventos do sistema e ordens de trade sob a nota diária do respectivo dia (ex: `journal/2026-07-11.md`). Inclui chats do Hermes (`Chat_Hermes_YYYY-MM-DD.md`).
- **`vault_galaxy/strategies/`:** Documentação detalhada dos limites e regras operacionais.

### 19.3 Triggers de Gravação
- **Salvamento de Trades:** Integrado em `database_service.py` (`save_trade_history_item`). Toda persistência de trade dispara uma task assíncrona que grava a nota do trade e gera o link no diário.
- **Transição de Regime:** Integrado em `oracle_agent.py` (`update_market_data`). Registra no diário diário mudanças de tendência (ADX e direção do BTC).
- **Chat Hermes:** Toda conversa é salva em `vault_galaxy/journal/Chat_Hermes_YYYY-MM-DD.md` com YAML frontmatter.

---

## 20. Hermes Chat — Interface de Conversação (V126)

Chat com IA integrada ao sistema completo 1Crypten. UI estilo Gemini com sidebar de histórico, voz (Whisper) e cascade de LLMs.

### 20.1 Frontend (`hermes-chat.html`)
- **Rota:** `/hermes` (serve `hermes-chat.html`)
- **Layout:** Sidebar esquerda (histórico de conversas) + área do chat (mensagens + input)
- **Sidebar:** Lista de sessões, busca, criar nova conversa, deletar
- **Chat:** Mensagens com avatar (Hermes roxo, user verde), indicador de digitação, suporte a markdown
- **Input:** Textarea com Enter para enviar, botão de voz (Whisper)
- **Model badge:** Exibe a LLM ativa na sidebar footer (nvidia/deepseek)
- **Menu:** Idêntico ao cockpit (logo, Banca, Hermes, ADM submenu, Sair)

### 20.2 Cascade de LLMs
```
1. NVIDIA (nemotron-4b-chat) ← PRIMÁRIO
2. DeepSeek (deepseek-chat)  ← SECUNDÁRIO
3. AIService (Gemini/OpenRouter) ← FALLBACK
```
- Cada LLM é tentada em sequência; se uma falhar, a próxima é usada
- Resposta inclui `context.model_used` para a UI atualizar o badge

### 20.3 Backend — Endpoints
| Método | Rota | Função |
|--------|------|--------|
| `POST` | `/api/hermes/chat` | Chat principal (salva user+assistant no DB) |
| `GET` | `/api/hermes/sessions` | Lista sessões do usuário |
| `POST` | `/api/hermes/sessions` | Cria nova sessão |
| `GET` | `/api/hermes/sessions/:id` | Carrega mensagens de uma sessão |
| `DELETE` | `/api/hermes/sessions/:id` | Deleta sessão + mensagens |
| `PATCH` | `/api/hermes/sessions/:id` | Renomeia sessão |

### 20.4 Persistência (PostgreSQL)
- **`chat_sessions`:** id (UUID), title, user_id, model, created_at, updated_at, message_count
- **`chat_messages`:** id (serial), session_id, role (user/assistant/system), content, context (JSON), created_at
- Tabelas auto-criadas por `Base.metadata.create_all` no boot

### 20.5 Contexto do Hermes
O Hermes acessa automaticamente:
1. **MASTER_ARCHITECTURE.md** — Arquitetura atual do sistema (cache 10min)
2. **vault_galaxy/** — Busca por keyword em journal, trades, strategies
3. **Intel Wiki** — Conteúdo de `intel_wiki.html` (cache 5min)
4. **Compliance** — Divergências ativas quando relevantes
5. **Dimensões JarvisBrain** — 10 dimensões de personalidade detectadas

### 20.6 Integração com Memory Galaxy
- Chat Hermes salva em `vault_galaxy/journal/Chat_Hermes_YYYY-MM-DD.md`
- Memory Galaxy exibe esses arquivos na aba "Recent"
- Graph visualization inclui nós de chat como category `journal`
- Busca no vault gera contexto para as respostas do Hermes

---

## 21. Memory Galaxy — Layout em Disco e Animação Orbital (V126)

### 21.1 Layout em Disco Elíptico (XZ)
O grafo 3D foi redesenhado como um disco galáctico horizontal inspirado no OMI OS Memory:
- **X** = eixo horizontal (width)
- **Z** = eixo de profundidade (depth) — ambos no mesmo plano
- **Y** = espessura vertical (±4px) — disco fino, quase 2D

```
Y (vertical)
↑   ┌──────────────────────────────┐
│   │  ★ ★ ★ ★ ★ ★ ★ ★ ★ ★ ★ ★  │  ← Y = ±4px (espessura)
│   │ ★ ★ ★ ★ ★ ★ ★ ★ ★ ★ ★ ★ ★ │
│   │  ★ ★ ★ ★ ★ ★ ★ ★ ★ ★ ★ ★  │
│   └──────────────────────────────┘
└──────────────────────────────────→ X (horizontal)
```

### 21.2 Parâmetros da Elipse
| Constante | Valor | Descrição |
|-----------|-------|-----------|
| `ELLIPSE_RX` | 115 | Raio horizontal |
| `ELLIPSE_RZ` | 65 | Raio vertical (profundidade) |
| `ELLIPSE_CLIP` | 0.92 | Margem de corte (10% de borda) |
| Opacidade da borda | 0.03 | Fronteira sutil da galáxia |

### 21.3 Layout dos Nós
- **Distribuição polar:** `r = 12 + rand * 100` (evita centro vazio)
- **Escala radial:** `x = r * 1.1`, `z = r * 0.55` (formato elíptico)
- **Clamp elíptico:** nós além de 0.92 da elipse são trazidos para dentro
- **Espessura Y:** `Y = (rand - 0.5) * 4` (uniforme) + offset por categoria

### 21.4 Nós e Links
- **Nós do vault:** Tamanho 6, cor por categoria (trades=verde, strategies=roxo, journal=azul)
- **Dust (poeira):** 250 nós extras em regiões externas para densidade visual
- **Hermes:** ★ fixo no centro (0, 0, 0), tamanho 25, cor `#7c3aed`
- **Links:** Opacidade 0.12, espessura 0.5, coloridos por relationship

### 21.5 Câmera
- **Posição:** `{ x: 0, y: 80, z: 180 }` (ângulo levemente inclinado)
- **Foco:** `{ x: 0, y: 0, z: 0 }`
- **Fundo:** `#020208` (azul muito escuro)
- **Estrellas fixas:** 400 pontos aleatórios (profundidade visual)

### 21.6 Animação Orbital (Vortex)
Todas as estrelas (nós + dust) orbitam em tempo real dentro da elipse:

```
tick():
    para cada nó com __threeObj:
        angle += speed (0.0006 base / dist)
        x = cos(angle) * r * 1.1
        z = sin(angle) * r * 0.55
        clamp(x, z) dentro da elipse
        update __threeObj.position(x, y, z)
```

| Parâmetro | Valor | Descrição |
|-----------|-------|-----------|
| Speed base | 0.0006 | Velocidade angular inicial |
| Speed衰减 | `1 + (r / 80)` | Nós distantes orbitam mais lento |
| Clamp | 0.92 | Nunca escapam da elipse |
| Pausa na interação | 3s | Ao usar mouse, animação pausa |

### 21.7 Background — Estrelas Fixas
- 400 pontos em esfera (r = 400-600)
- Tamanho fixo 1.0, opacidade 0.8
- Criadas uma vez, nunca atualizadas

### 21.8 Background — Nebulosa (4 camadas)
- Cada camada: esfera (r = 350), cor única, opacidade 0.06
- Camadas: azul (#3b82f6), roxo (#8b5cf6), rosa (#ec4899), ciano (#06b6d4)

---

*Última atualização: V126 — Memory Galaxy Layout em Disco + Animação Orbital + Hermes Chat*
