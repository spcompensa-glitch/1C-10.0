# Estado Atual do Sistema — 1Crypten 7.0

*Ultima atualizacao: 2026-06-26 (V118.4 — Stop adaptativo por regime: LATERAL -10%, TRENDING -15%)*

---

## Resumo

- **Estado**: OPERACIONAL (producao OKX + sandbox simultaneos)
- **Versao do codigo**: V110.x (multiplas versoes por agente — ver MASTER_ARCHITECTURE.md secao 13)
- **Exchange**: OKX (Portfolio Margin)
- **Deploy**: Railway + Docker

---

## Componentes Ativos

| Componente | Status | Descricao |
|------------|--------|-----------|
| FastAPI Backend | ATIVO | API + WebSockets, porta 8085 |
| Cockpit UI | ATIVO | Dashboard desktop/mobile, ~430KB |
| PostgreSQL | ATIVO | SSOT persistente (Railway) |
| Firebase RTDB | ATIVO | Sincronizacao UI em tempo real |
| OKX REST | ATIVO | Execucao de ordens |
| OKX WebSocket | ATIVO | Feed de precos em tempo real |
| FlashAgent | ATIVO | Gestao de stops, ciclo 1s |
| CaptainAgent | ATIVO | Quality gate, routing de sinais |
| BankrollGuardian | ATIVO | Autorizacao de trades |
| OracleAgent | ATIVO | Deteccao de regime (ADX) |
| FleetAudit | ATIVO | Reconciliacao 20s |
| BlitzSniper | ATIVO | Extracao M30 |
| Librarian | ATIVO | DNA de ativos, rankings |
| MacroAnalyst | ATIVO | Risco macro BTC |
| WhaleTracker | ATIVO | Fluxo institucional |
| TradeAnalyst | ATIVO | Autopsia pos-trade |
| Quartermaster | ATIVO | Classificacao leverage |
| HermesAgent | ATIVO | Compliance/chat |
| PortfolioGuardian | DESATIVADO | Heartbeat apenas |
| SentinelAgent | ATIVO | Failsafe de posicoes |
| **SandboxService** | **ATIVO** | **Forward Testing Lab — espelha sistema real, ciclo 1s** |

---

## Regime de Mercado

**O regime gating foi removido** (V118). Todas as estrategias (VELOCITY FLOW, ALPHA SHIELD, DECOR SHADOW) operam em qualquer regime.

O risco e mitigado por:
- **GARANTIA_5**: stop → 0% aos +5% ROI (break-even antecipado)
- **Filtro de LONGS**: apenas pares desgrudados do BTC (Pearson < 0.35) com gas (confidence >= 70)

**MACRO-BLOCK**: LONGs aprovados pelo filtro de decorrelacao tambem furam o MACRO-BLOCK.

---

## Escadinha de Stops

### Lateral (simplificada) — V118
- 5% ROI -> stop 0% (GARANTIA_5 — break-even antecipado)
- 15% ROI -> saida parcial 50%
- 20%+ ROI -> trailing dinamico

### Tendencia (progressiva)
10 niveis de BREAKEVEN ate STAR (400% ROI), depois CROWN, SUPERNOVA, GOD_MODE, CHOKE_PREP, CHOKE, HYPER, APEX (1200%), e niveis ULTRA_* a cada 200% acima.

Veja `MASTER_ARCHITECTURE.md` secao 4 para a tabela completa.

---

## Limites Operacionais

| Parametro | Valor |
|-----------|-------|
| Max slots (config) | 16 |
| Max slots (guardian ranging) | 20 |
| Max slots (guardian trending) | 40 |
| Leverage padrao | 50x |
| Margem por slot (lateral) | $2.00 |
| Margem por slot (trending) | $1.00 |
| Teto stop inicial | 30% ROI |
| Intervalo FlashAgent | 1s |
| Intervalo FleetAudit | 20s |
| Intervalo scan radar | 5s |

---

## Funcionalidades Removidas (codigo ainda parcialmente presente)

| Feature | Status | Detalhe |
|---------|--------|---------|
| Moonbags | REMOVIDA do runtime | Entidade nao e mais criada. Codigo legado em `fleet_audit.py`, `database_service.py` e `firebase_service.py` ainda referencia moonbags para dados historicos |
| Portfolio Guardian (Knife-Drop) | DESATIVADO | Mantem apenas heartbeat |
| `should_emancipate` | SEMPRE False | Em `order_projection_service.py` |

---

## Conflitos Conhecidos no Codigo

1. **RISK_ZERO threshold**: `chat.py` (80%) vs `hermes_agent.py` (50%)
2. **Max slots**: `config.py` (16) vs `bankroll_guardian.py` (20/40) — camadas diferentes
3. **Reset banca**: `admin.py` diz $100, comentarios dizem $20
4. **Referencias Bybit**: `market.py` ainda usa nomes `BybitRest`, `BybitWS` (legado)
5. **Dois apps FastAPI**: Root `main.py` (Firebase-first) e `backend/main.py` (Postgres-first)

---

## Endpoints Principais

| Rota | Funcao |
|------|--------|
| `GET /api/health` | Health check com versao |
| `GET /api/slots` | Todos os slots ativos |
| `GET /api/system/state` | Estado completo do sistema |
| `GET /api/radar/pulse` | Sinais do radar |
| `GET /api/radar/regimes` | Regime por par |
| `POST /api/admin/reset-system` | Nuclear reset |
| `POST /api/hermes/chat` | Chat com IA |

---

## Sandbox — Forward Testing Lab

- **URL**: https://1crypten.space/sandbox
- **Banca Virtual**: **$22.00 USD** | Margem media: **$0.75/trade** (entre $0.50 e $1.00) | Leverage: 50x
  - Objetivo: espelhar a banca real do usuario na OKX ($22 USD)
  - PnL calculado: `(ROI% / 100) * $0.75` por trade; total como % da banca $22
- **Hook de sinais**: `firebase_service.update_radar_pulse()` dispara `on_radar_pulse()` a cada ciclo do Radar
- **Monitoramento**: loop de 1s identico ao FlashAgent
- **[V118] Estrategias**: regime gating REMOVIDO — VELOCITY FLOW, ALPHA SHIELD e DECOR SHADOW operam em qualquer regime
- **[V118] LONGS filtrados**: apenas pares desgrudados do BTC (Pearson < 0.35) com gas (CVD/volume, confidence >= 70)
- **[V118.4] Stop inicial adaptativo por regime**:
  - **LATERAL (ADX < 25)**: **-10% ROI** (mais espaco em mercado lateral)
  - **TRENDING (ADX >= 25)**: **-15% ROI** (mais folga para pullbacks em tendencia)
  - GARANTIA_5 (+5% ROI) leva stop a 0% (protecao rapida do capital)
- **[V114] Cooldown pos stop-out**: 300s por simbolo+direcao apos `CLOSED_SL` (600s se 2+ stops consecutivos na mesma direcao)
  - Objetivo: eliminar re-entries em cadeia (INJUSDT 11x, ATOM 4x consecutivos)
- **[V118.3] Confirmacao 5M com alinhamento de tendencia** (substituiu V117):
  - Busca 5 candles de 5M, verifica os 3 mais recentes FECHADOS
  - Exige maioria 2/3 alinhada com a direcao do sinal:
    - SHORT: precisa de >= 2 bearish de 3 candles (senao BLOQUEIA)
    - LONG: precisa de >= 2 bullish de 3 candles (senao BLOQUEIA)
  - Score boost: 3/3 = +10 FORTE, 2/3 = +5 MODERADA
  - fail-open se API falhar ou candles insuficientes
- **[V116] MACRO-BLOCK relaxado**:
  - LATERAL (ADX < 25): MACRO-BLOCK desativado
  - TRENDING: sinais com score >= 80 furam MACRO-BLOCK (high_score_bypass)
  - **[V118]**: LONGs aprovados pelo filtro de decorrelacao tambem furam MACRO-BLOCK
- **Entry Sanity Check**: descarta sinais com ROI imediato ja < 70% do stop (floor -10%)
- **Resolucao de preco**: WS -> REST -> cache (60s TTL)
- **Conservative price**: HIGH/LOW dos ultimos 120s para capturar spikes intra-ciclo
- **Escadinha**: usa `OrderProjectionService` identico ao sistema real
- **Peak ROI**: persistido em cache + banco (sobrevive a reinicializacoes)
- **Saida parcial**: +15% ROI em LATERAL -> 50% saida imediata; PnL = media 50/50
- **[V118] Auto-blocklist**: pares com PnL < -15% E WR < 35% apos 3+ trades bloqueados em runtime (era 5+ trades, -20%, 30%)

### Logs do Sandbox (V118)
| Log | Significado |
|-----|-------------|
| `[SANDBOX-OPEN]` | Trade aberto |
| `[SANDBOX-STALE]` | Entry defasado — descartado |
| `[SANDBOX-LONG-FILTER]` | LONG descartado — par nao esta desgrudado do BTC |
| `[SANDBOX-COOLDOWN-SET]` | Cooldown 300s/600s iniciado apos stop-out |
| `[SANDBOX-COOLDOWN]` | Sinal bloqueado — simbolo em cooldown |
| `[SANDBOX-5M]` | Confirmacao 5M (+5/+10 block/boost) |
| `[SANDBOX-5M-BLOCK]` | Trade bloqueado — 5M nao alinhado com direcao do sinal |
| `[SANDBOX-FLASH]` | Degrau da escadinha (GARANTIA_5 aos +5%) |
| `[SANDBOX-LOSS]` | Trade fechado no stop |
| `[SANDBOX-AUTO-BLOCKLIST]` | Par bloqueado por performance critica |

---

## Endpoints Principais

| Rota | Funcao |
|------|--------|
| `GET /api/health` | Health check com versao |
| `GET /api/slots` | Todos os slots ativos |
| `GET /api/system/state` | Estado completo do sistema |
| `GET /api/radar/pulse` | Sinais do radar |
| `GET /api/radar/regimes` | Regime por par |
| `POST /api/admin/reset-system` | Nuclear reset |
| `POST /api/hermes/chat` | Chat com IA |
| `GET /api/sandbox/trades` | Trades do sandbox |
| `GET /api/sandbox/stats` | Estatisticas + regime |
| `GET /api/sandbox/patterns` | Whitelist/blacklist sugerida |
| `GET /api/sandbox/analytics` | Analytics detalhado |
| `POST /api/sandbox/clear` | Limpar sandbox |

---

*Baseado no codigo-fonte. Nao em historico de versoes.*
