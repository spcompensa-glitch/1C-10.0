# MASTER_ARCHITECTURE.md — 1Crypten 7.0

Fonte unica de verdade arquitetural. Baseado no codigo-fonte, nao em historico de versoes.

*Ultima atualizacao: 2026-06-26 (V118.4 — Stop adaptativo por regime: LATERAL -10%, TRENDING -15%)*

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

O sistema usa 18 agentes especializados, cada um com responsabilidade unica:

### 2.1 Agentes de Decisao

| Agente | Arquivo | Funcao |
|--------|---------|--------|
| **CaptainAgent** | `agents/captain.py` | Despachante de sinais. Quality gate, regime gating, consensus de frota (Macro 15%, Whale 25%, SMC 30%, OnChain 30%). V20.5 |
| **OracleAgent** | `agents/oracle_agent.py` | Determinacao de regime de mercado. Grade ADX: RANGING (<25), TRENDING (>=25). Estabilizacao de 150s |
| **FlashAgent** | `agents/flash_agent.py` | Motor da escadinha. Escritor unico de stops. Ciclo de 1s. Progressao ORDER -> ESCADINHA -> TRAILING |
| **BankrollGuardian** | `agents/bankroll_guardian.py` | Autorizacao de trades. Gating por regime, limites de slots, memoria por par |
| **SlotOperator** | `agents/slot_operator.py` | Observador/failsafe. Loop de 3s. Virtual stop loss monitoring |

### 2.2 Agentes de Sinal

| Agente | Arquivo | Funcao |
|--------|---------|--------|
| **BlitzSniper** | `agents/blitz_sniper.py` | Extracao M30. Cooldown 300s, score >= 80,双s Slots |
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
| **HermesAgent** | `agents/hermes_agent.py` | Compliance/telemetria/chat. DeepSeek integration, ESCADINHA_DOCS_SSOT |
| **JarvisBrain** | `agents/jarvis_brain.py` | Chat multi-dimensao (10 dimensoes: Trading, Filosofia, Familia, etc.) |
| **AIService** | `agents/ai_service.py` | Cascade de IA: DeepSeek -> Gemini -> OpenRouter |
| **SandboxService** | `services/sandbox_service.py` | Forward Testing Lab. Espelha o sistema real com escadinha, stops adaptativos e fallback de preco. Ciclo 1s. |

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
    |-- Regime gating: ADX < 25 = so DECOR; >= 25 = so VELOCITY/ALPHA
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

### 4.1 Regime LATERAL (ADX < 25)

Degraus simplificados para mercado lateral. Protecao cedo contra falsos rompimentos.

| Gatilho ROI | Stop (ROI) | Nome | Status |
|------------|-----------|------|--------|
| 5% | -10% | SL_5 | ESCADINHA |
| 10% | 0% | SL_BE | RISCO_ZERO |
| 15% | 0% | SAIDA_PARCIAL | TRAILING |
| 20%+ | Dinamico (-5% do pico) | TRAIL_20 | TRAILING |

### 4.2 Regime TENDENCIA (ADX >= 25)

Degraus progressivos para colher lucros em tendencia forte.

| Gatilho ROI | Stop (ROI) | Nome | Status |
|------------|-----------|------|--------|
| 10% | 0% | BREAKEVEN | RISCO_ZERO |
| 30% | 15% | LUCRO_INICIAL | RISCO_ZERO |
| 45% | 30% | LUCRO_MEDIO | RISCO_ZERO |
| 80% | 50% | LUCRO_GARANTIDO_80 | RISCO_ZERO |
| 100% | 75% | LUCRO_GARANTIDO | RISCO_ZERO |
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

**[V118] Regime gating removido.** VELOCITY FLOW, ALPHA SHIELD e DECOR SHADOW operam em qualquer regime.

| Condicao | Acao |
|----------|------|
| ADX < 25 | LATERAL: todas as estrategias permitidas (risco mitigado pela escadinha GARANTIA_5) |
| ADX >= 25 | TENDENCIA: todas as estrategias permitidas |

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
| PostgreSQL | SSOT persistente | `slots`, `radar_pulse`, `banca_status`, `sandbox_trades`, `moonbags` |
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

1. **RISK_ZERO**: `chat.py` diz 80% ROI, `hermes_agent.py` diz 50% ROI
2. **Versoes**: Multiplas versoes coexistem (V20.5 captain, V110.x services, V2.x hermes, etc.)
3. **Portfolio Guardian**: Importado e instanciado no `main.py` raiz mas marcado DESATIVADO
4. **Referencias Bybit legadas**: `market.py` ainda usa nomes `BybitRest`, `BybitWS`
5. **`get_slot_type()` sempre retorna "DVAP"** (V110.950)
6. **Dois FastAPI apps**: Root `main.py` (Firebase-first) e `backend/main.py` (Postgres-first)
7. **Reset banca**: `admin.py` diz $100 mas comentarios dizem $20
8. **`radar_pulse`**: Nao e arquivo separado — e estrutura de dados em database_service, firebase_service e websocket_service

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
              |-- [V118] Filtro ADX/regime: REMOVIDO — todas as estrategias livres
              |-- [V118] Filtro LONGS: apenas pares desgrudados (Pearson < 0.35) com gas
              |-- [V118] LONGs aprovados furam MACRO-BLOCK (decor_bypass)
              |-- Filtro macro BTC (SMA 200 diaria)
              |-- Filtro blocklist (ASSET_BLOCKLIST + auto-blocklist)
              |-- Filtro horario abertura US (13:30-14:30 UTC)
              |-- Deduplicacao por signal_id
              |-- [V114] Cooldown 300s pos stop-out por simbolo
              |-- [V118.3] Confirmacao 5M (exige maioria 2/3 alinhada com direcao)
              |-- Entry Sanity Check (preco defasado)
              |-- [V118.4] Stop adaptativo por regime: LATERAL -10%, TRENDING -15%
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

| Regime | ADX | Stop Inicial (V118.4) | Threshold Stale Entry |
|--------|-----|----------------------|----------------------|
| LATERAL | < 25 | **-10% ROI** | ROI imediato < -7.0% (floor -10%) |
| TENDENCIA | >= 25 | **-15% ROI** | ROI imediato < -10.5% (floor -10%) |

> **[V118.4]**: Stop inicial agora e adaptativo por regime (era fixo -5%).
> - LATERAL: -10% ROI — evita stops em chop de lateral
> - TRENDING: -15% ROI — pullbacks em tendencia precisam de mais espaco
> GARANTIA_5 (+5% ROI na escadinha) leva o stop a 0% rapidamente, protegendo o capital.
> O floor de -10% no stale threshold evita descartes agressivos em TRENDING.

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
- **Escadinha**: usa `OrderProjectionService.get_stop_ladder()` + `get_active_level()` — **identico ao FlashAgent real**.
- **Saida parcial lateral**: ao atingir +15% ROI em regime LATERAL, registra `has_taken_partial=True`; PnL final = media 50/50.
- **Confirmacao REST antes de fechar**: apos `stop_hit=True`, busca preco fresco via REST antes de persistir o fechamento.
- **Auto-blocklist [V118]**: pares com PnL total < -15% E win rate < 35% apos 3+ trades bloqueados automaticamente em runtime (era 5/20/30). Verificado a cada 120s.

### 15.7 Constantes do SandboxService (V113.2 / V114)

| Constante | Valor | Localizacao |
|-----------|-------|-------------|
| Ciclo de monitoramento | 1s | `sandbox_service.py` |
| Banca virtual | **$22.00 USD** | `routes/sandbox.py:49` (`BANCA = 22.0`) |
| Margem media por trade | **$0.75** | `routes/sandbox.py:50` (`MARGEM_MEDIA = 0.75`) |
| Margem simulada OKX | Entre $0.50 e $1.00 | `routes/sandbox.py:54` |
| Leverage (sandbox) | 50x | `sandbox_service.py` |
| Janela conservative price | 120s | `okx_ws_public.py:291` |
| TTL cache de preco | 60s | `sandbox_service.py` |
| [V118.4] Stop inicial adaptativo | LATERAL **-10%**, TRENDING **-15%** | `sandbox_service.py` |
| Threshold stale entry | 70% do stop (floor -10%) | `sandbox_service.py` |
| [V114] Cooldown pos stop-out | **300s (5 min)** | `sandbox_service.py` |
| [V118.3] Candles 5M para confirmacao | 3 fechados (5 buscados), exige 2/3 alinhados com direcao | `sandbox_service.py` |
| Polling frontend | 2s | `sandbox.html` |
| Polling patterns | 5s | `sandbox.html` |
| Placeholder banca (HTML) | **$22.00 USD** | `sandbox.html:158` |
| Auto-blocklist check | 120s | `sandbox_service.py` |
| [V118] Auto-blocklist criterio | PnL < -15% E WR < 35% apos 3+ trades | `sandbox_service.py` |

### 15.8 Logs esperados no comportamento normal

| Log | Significado |
|-----|-------------|
| `[SANDBOX-OPEN]` | Trade aberto com Entry, SL, MktPrice, TickSize |
| `[SANDBOX-STALE]` | Sinal descartado — entry defasado (ROI imediato < threshold) |
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
| Stop -5% muito apertado (stops precoces) | V118.4 | Stop fixo -5% em ambos regimes causava stops prematuralos. Fix: stop adaptativo LATERAL -10%, TRENDING -15%, GARANTIA_5 mantido |

---

*Baseado no codigo-fonte em 2026-06-25. Atualizar ao modificar qualquer constante ou componente.*
componente.*
