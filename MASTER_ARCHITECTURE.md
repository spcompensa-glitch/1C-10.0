# MASTER_ARCHITECTURE.md — 1Crypten 7.0

Fonte unica de verdade arquitetural. Baseado no codigo-fonte, nao em historico de versoes.

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

| Condicao | Acao |
|----------|------|
| ADX < 25 | LATERAL: apenas DECOR SHADOW executado |
| ADX >= 25 | TENDENCIA: apenas VELOCITY FLOW e ALPHA SHIELD |

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
| GET | `/api/sandbox/trades` | Listar trades sandbox |
| GET | `/api/sandbox/stats` | Estatisticas sandbox |
| POST | `/api/sandbox/trade` | Criar trade sandbox |
| DELETE | `/api/sandbox/trade/{id}` | Deletar trade sandbox |
| POST | `/api/sandbox/reset` | Resetar sandbox |

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

---

*Baseado no codigo-fonte em 2026-06-24. Atualizar ao modificar qualquer constante ou componente.*
