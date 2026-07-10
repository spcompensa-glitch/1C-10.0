# Estado Atual do Sistema — 1Crypten 7.0

*Ultima atualizacao: 2026-07-07 (V124.7 — SignalGenerator substitui BlitzSniperAgent: 3 estrategias no M30)*

---

## Resumo

- **Estado**: OPERACIONAL (producao OKX + sandbox simultaneos)
- **Versao do codigo**: V124.7
- **Exchange**: OKX (Portfolio Margin)
- **Deploy**: Railway + Docker

---

## Novidades V124.7
- **BlitzSniperAgent removido**: Substituido por `SignalGenerator.analyze_m30_swing()` em `signal_generator.py`. O BlitzSniperAgent usava apenas SMA9/21 crossover + scoring simples (score >= 75) — era uma versao empobrecida do motor de estrategias principal.
- **3 estrategias no M30**: `analyze_m30_swing()` reusa toda a infraestrutura de deteccao de padroes do SignalGenerator:
  - **DVAP/MOLA/FAS/LRT** → **ALPHA SHIELD** (divergencia RSI + volume climax + CHoCH, BB squeeze, funding extremo)
  - **TREND** → **VELOCITY FLOW** (SMA8/21 alinhado + volume)
  - **DECOR** → **DECOR SHADOW** (CVD exhaustion + RSI extremo)
- **Score minimo reduzido para 65** (era 75 no BlitzSniper) — mais sensivel, capturando setups mesmo em lateral moderada.
- **`_blitz_scan_loop` reformulado**: Chama `signal_generator.scan_m30_swing_watchlist()` em vez de `blitz_sniper_agent.scan_and_inject()`. Mantem cooldown, collision guard e injecao na signal_queue.
- **DECOR_HUNTER tambem atualizado**: `_analyze_decor_pair()` usa `signal_generator.analyze_m30_swing()` em vez de `blitz_sniper_agent.scan_for_blitz_signal()`. Threshold reduzido para 60.
- **Infra V124.6 mantida**: escadinha RANGING_SWING, partial TP 30%, `slot_type=BLITZ_30M`, trailing gap 10% continuam ativos.

## Novidades V124.6
- **Blitz M30 liberado em LATERAL**: `captain.py` — dois gates de regime (linhas ~1324 e ~1552) agora aceitam `is_blitz=True` ou `slot_type=BLITZ_30M` mesmo quando ADX < 25. Permite que swings 30M entrem antes do ADX evoluir para trending.
- **Nova escadinha `ORDER_STOP_LADDER_RANGING_SWING`**: gaps 2x maiores que a escada RANGING padrão (ex: primeiro degrau em +16% vs +8%) — `order_projection_service.py:42`. Dá respiro para o ADX sair de LATERAL para TRENDING.
- **slot_type como seletor de escada**: `get_stop_ladder()`, `get_active_level()`, `get_next_level()`, `get_phase()`, `build_projection()` em `order_projection_service.py` aceitam `slot_type` para escolher entre RANGING, RANGING_SWING e TRENDING.
- **Partial TP em +30% para BLITZ_30M**: `flash_agent.py:251` — `partial_tp_threshold = 30.0 if slot_type in ("BLITZ_30M",) else 15.0`. Swing precisa de mais espaço que scalping.
- **Trailing gap de 10% para BLITZ_30M**: `order_projection_service.py:153` — `trailing_gap = 10.0 if slot_type in ("BLITZ_30M",) else 5.0`.

## Novidades V123.3
- **Contingência de Histórico (Vault)**: Se uma posição real legítima fechar na OKX (como AVAXUSDT) e a chamada de PnL fechado da API falhar ou atrasar, o `sync_slots_with_exchange` não deletará mais o slot sem logar. O backend agora calcula uma estimativa de PnL em tempo real com base no preço atual e grava o encerramento com sucesso na Vault.
- **Injeção de Saldo Real OKX**: O endpoint `/api/banca/data` agora consulta em tempo real a exchange master usando as chaves reais via `okx_service._get_headers` homologado (prevenindo erros de HMAC/fuso horário) e retorna `saldo_real_okx` no payload autenticado (`USER_MODE`).
- **Blindagem do Cockpit**: O hook `useBancaRT` no frontend (`cockpit.html`) agora é盲ado para reter o último saldo real positivo válido. Isso evita que transmissões em background do WebSocket (que enviam dados zerados ou parciais de simulação do Guardião) sobresscrevam a banca real na UI.

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
| BlitzSniper | SUBSTITUIDO V124.7 | Agora SignalGenerator.analyze_m30_swing() — 3 estrategias no M30 |
| Librarian | ATIVO | DNA de ativos, rankings |
| MacroAnalyst | ATIVO | Risco macro BTC |
| WhaleTracker | ATIVO | Fluxo institucional |
| TradeAnalyst | ATIVO | Autopsia pos-trade |
| Quartermaster | ATIVO | Classificacao leverage |
| HermesAgent | ATIVO | Compliance/chat |
| PortfolioGuardian | DESATIVADO | Heartbeat apenas |
| SentinelAgent | ATIVO | Failsafe de posicoes |
| **SandboxService** | **ATIVO** | **Forward Testing Lab — espelha sistema real, ciclo 1s** |
| **PhaseDetector** | **ATIVO** | **Deteccao Fase 1+2 (Acumulacao + Compressao) — Explosion Score** |

---

## Regime de Mercado

**[V123] Regime gating RESTAURADO no Sandbox** — DECOR SHADOW opera APENAS em LATERAL (ADX < 25).
- Motivo: DECOR SHADOW é estratégia de reversão/exaustão — em TRENDING, o preço pode continuar caindo livremente.
- ALPHA SHIELD e VELOCITY FLOW operam em qualquer regime.
- **[V124.6] BLITZ (BlitzSniper M30) bypassa regime gating** — `captain.py` libera sinais com `is_blitz=True` ou `slot_type=BLITZ_30M` mesmo em ADX < 25.

O risco e mitigado por:
- **GARANTIA_5**: stop → 0% aos +5% ROI (break-even antecipado)
- **Filtro de LONGS**: apenas pares desgrudados do BTC (Pearson < 0.35) com gas (confidence >= 70)

**MACRO-BLOCK**: LONGs aprovados pelo filtro de decorrelacao tambem furam o MACRO-BLOCK.

---

## Escadinha de Stops

Tres escadinhas convivem, selecionadas por `slot_type` em `order_projection_service.py`:

### Lateral Scalping (`ORDER_STOP_LADDER_RANGING`)
- +8% -> stop +2% (GARANTIA_TAXAS)
- +12% -> stop +5% (GARANTIA_LUCRO_CURTO)
- +20% -> stop +10% (GARANTIA_LUCRO_MEDIO)
- +32% -> stop +18% (GARANTIA_LUCRO_ALTO)
- +50%+ -> trailing -2% pico (ALVO_MAXIMO_LATERAL)
- Partial TP: +15% ROI

### Lateral Swing — Blitz M30 (`ORDER_STOP_LADDER_RANGING_SWING`) [V124.6]
- +16% -> stop +2% (GARANTIA_TAXAS)
- +25% -> stop +10% (GARANTIA_LUCRO_CURTO)
- +40% -> stop +20% (GARANTIA_LUCRO_MEDIO)
- +60% -> stop +35% (GARANTIA_LUCRO_ALTO)
- +80%+ -> trailing -5% pico (ALVO_MAXIMO_SWING)
- Partial TP: +30% ROI

### Tendencia (`ORDER_STOP_LADDER_TRENDING`)
14 niveis de GARANTIA_TAXAS ate APEX (1200% ROI), depois ULTRA_* a cada 200%.

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

1. ~~**RISK_ZERO threshold**: `chat.py` (80%) vs `hermes_agent.py` (50%)~~ ✅ RESOLVIDO V121
2. ~~**Max slots**: `config.py` (16) vs `bankroll_guardian.py` (20/40)~~ ✅ RESOLVIDO V121
3. **Reset banca**: `admin.py` diz $100, comentarios dizem $20
4. **Referencias Bybit**: `market.py` ainda usa nomes `BybitRest`, `BybitWS` (legado)
5. ~~**Dois apps FastAPI**: Root `main.py` (Firebase-first) e `backend/main.py` (Postgres-first)~~ ✅ RESOLVIDO V120.4

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
- **Banca Virtual (Scalping Lab)**: **$100.00 USD** | Margem: **$2.00/trade** (50x) | Trailing & Escadinha
- **Banca Virtual (Sandbox Unificado)**: **$100.00 USD** | Margem: **$2.00/trade** (Alavancagens: 50x Scalping / 50x Swing)
- **[V125.1] Divisão Consolidada (10/10 Slots)**: Máximo de 10 posições em paralelo para Scalping e 10 para Swing Lab (limite total de 20 slots consumindo até $40.00 da banca, garantindo saúde de margem na real se espelhado).
- **[V125.1] Zero-Risk Stacking (Swing)**: O robô de Swing abre estritamente 1 posição por ciclo e trava a fila. O próximo sinal de Swing só é aberto quando todas as posições ativas estiverem protegidas pelo Stop Loss (Break-even).
- **[V125.1] Painel Global de Espelho (Mirror)**: Interface unificada de `Espelho Real (OKX)`. Quando ligado, todas as novas ordens autônomas (tanto do radar de Scalp quanto do Swing M30) serão espelhadas para a conta real (sujeito à proteção de banca `check_min_margin`).
- **[V125] Motor Primário Autônomo**: O Swing Lab detecta setups M30 de forma autônoma e gerencia ordens virtuais e espelhos reais.
- **[V125] Cérebro Unificado de Stops**: O **FlashAgent** monitora centralizadamente e a cada 1s os stops de Scalping e Swing (Doutrina das Extrações no Swing, sem saída parcial de 50%).


- **[V123.1] Explosion Score mínimo: 35** (V123 havia elevado para 50 — estava paralisando o sistema em mercados com BTC plano/lateral. Valor calibrado da V119.)
- **[V123.1] Cooldown pós stop-out: 1800s (30min) no 1º stop**, 3600s (1h) se 2+ stops consecutivos. (Antes: 3600s mesmo no 1º stop — bloqueava reentradas mesmo após mudança de regime.)
- **[V123.1] VOL_DRY no DECOR SHADOW: condicional ao explosion_score** — score >= 45 permite entrada (compressão de preço já é evidência). Score < 45 + VOL_DRY = bloqueio total.
- **[V123] Regime gating RESTAURADO** — DECOR SHADOW opera APENAS em LATERAL (ADX < 25). ALPHA SHIELD e VELOCITY FLOW operam em qualquer regime.
- **[V122] Bug fix swing_high SHORT**: era `min()` (stop fraco), agora `max()` (stop robusto no swing mais distante)
- **[V122] GARANTIA_TRAIL**: trailing dinâmico a 60% do pico (antes: stop fixo +1.5% — perdia 90% dos ganhos)
- **[V122] DECOR SHADOW exige Fase 2**: ao menos 1 sinal P2: (BB comprimido ou Range compression) obrigatório
- **[V120] Stop inicial otimizado para R:R**:
  - Fallback: **-25% ROI** (0.5% no preço com 50x) — dá espaço para o preço respirar
  - Capping estrutural: **-30% ROI** max (0.6% no preço)
  - Busca estrutural 30M (swing low/high + buffer 0.15%) com fallback para regime fixo
  - GARANTIA_5 (+5% ROI) leva stop a 0% (protecao rapida do capital)
  - GARANTIA_TAXAS (+3% ROI) ativa break-even com 1.5% para cobrir taxas
- **[V120] Asian Session Penalty**: ADX >= 32 exigido entre 23h-01h UTC (pico de losses)
- **[V123.1] Cooldown pos stop-out: 1800s (30min)** no 1º stop; **3600s (1h)** se 2+ stops consecutivos por simbolo+direcao apos `CLOSED_SL`
  - Objetivo: eliminar re-entries em cadeia (INJUSDT 11x, ATOM 4x consecutivos) sem bloquear reentradas legais apos mudanca de regime
- **[V118.3] Confirmacao 5M com alinhamento de tendencia** (substituiu V117):
  - Busca 5 candles de 5M, verifica os 3 mais recentes FECHADOS
  - Exige maioria 2/3 alinhada com a direcao do sinal:
    - SHORT: precisa de >= 2 bearish de 3 candles (senao BLOQUEIA)
    - LONG: precisa de >= 2 bullish de 3 candles (senao BLOQUEIA)
  - Score boost: 3/3 = +10 FORTE, 2/3 = +5 MODERADA
  - **[V123] fail-safe**: falha na API BLOQUEIA entrada (era fail-open)
- **[V116] MACRO-BLOCK relaxado**:
  - LATERAL (ADX < 25): MACRO-BLOCK desativado
  - TRENDING: sinais com score >= 80 furam MACRO-BLOCK (high_score_bypass)
  - **[V120]**: LONGs aprovados pelo filtro de decorrelacao tambem furam MACRO-BLOCK
- **Entry Sanity Check**: descarta sinais com ROI imediato ja < 70% do stop (floor -10%)
- **Resolucao de preco**: WS -> REST -> cache (60s TTL)
- **Conservative price**: HIGH/LOW dos ultimos 120s para capturar spikes intra-ciclo
- **Escadinha**: usa `OrderProjectionService` identico ao sistema real
- **Peak ROI**: persistido em cache + banco (sobrevive a reinicializacoes)
- **[V120] Saida parcial**: +15% ROI em LATERAL + **+25% ROI em TRENDING** -> 50% saida imediata; PnL = media 50/50
- **[V118] Auto-blocklist**: pares com PnL < -15% E WR < 35% apos 3+ trades bloqueados em runtime
- **[V120] Static blocklist**: ADAUSDT, GALAUSDT, ARBUSDT, OPUSDT, POLUSDT, NEARUSDT (performance extrema negativa)
- **[V120] Margem adaptativa**: $1.00 (WR<60%) / $1.50 (WR>=60%) / $2.00 (WR>=70%) / $2.50 (WR>=80%)

### Logs do Sandbox (V123)
| Log | Significado |
|-----|-------------|
| `[SANDBOX-OPEN]` | Trade aberto |
| `[SANDBOX-STALE]` | Entry defasado — descartado |
| `[SANDBOX-REGIME-BLOCK]` | DECOR SHADOW bloqueado — opera apenas em LATERAL |
| `[SANDBOX-DECOR-VOLDRY-BLOCK]` | DECOR SHADOW bloqueado — volume seco (VOL_DRY) |
| `[SANDBOX-V123-LONG]` | LONG descartado — filtro de decorrelação não atendido |
| `[SANDBOX-ASIAN-PENALTY]` | Sinal bloqueado — sessão asiática (23h-01h UTC) com ADX < 32 |
| `[SANDBOX-COOLDOWN-SET]` | Cooldown 300s/3600s iniciado apos stop-out |
| `[SANDBOX-COOLDOWN]` | Sinal bloqueado — simbolo em cooldown |
| `[SANDBOX-5M]` | Confirmacao 5M (+5/+10 block/boost) |
| `[SANDBOX-V123]` | Stop estrutural 30M calculado (swing level + buffer) |
| `[SANDBOX-5M-BLOCK]` | Trade bloqueado — 5M nao alinhado com direcao do sinal |
| `[SANDBOX-FLASH]` | Degrau da escadinha (GARANTIA_5 aos +5%, GARANTIA_TAXAS aos +3%) |
| `[SANDBOX-PARTIAL]` | Saida parcial 50% executada (LATERAL +15% ou TRENDING +25%) |
| `[SANDBOX-LOSS]` | Trade fechado no stop |
| `[SANDBOX-AUTO-BLOCKLIST]` | Par bloqueado por performance critica |
| `[SANDBOX-BLOCKLIST]` | Simbolo bloqueado por blocklist estatica |
| `[SANDBOX-EXPLOSION-BLOCK]` | Trade bloqueado — explosion_score < 35 (sem evidência mínima de Fase 1+2) |
| `[SANDBOX-DECOR-VOLDRY-BLOCK]` | DECOR SHADOW bloqueado — VOL_DRY + explosion_score < 45 |
| `[SANDBOX-DECOR-VOLDRY-ALLOW]` | DECOR SHADOW permitido com VOL_DRY — explosion_score >= 45 (compressão forte compensa) |
| `[EXPLOSION-SCORE]` | Explosion Score calculado para um simbolo |

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
