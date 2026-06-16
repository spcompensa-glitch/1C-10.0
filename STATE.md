# Estado Atual do Projeto — 1Crypten (SaaS v5.5.0 / V111.1)

## Resumo Executivo
* **Versão:** `V111.2: Filtro de Regime de Mercado — Stop Cap + Direção`
* **Data:** 2026-06-16
* **Estado:** `OPERATIONAL REAL ✅`
* **Escopo:** Correção crítica do `BankrollGuardian` que impedia abertura de ordens em REAL mode: o `base_balance` usava o valor simulado (`$100`) em vez do equity real da exchange (~$20), causando `PRESERVACAO_TOTAL` com `min_score = 999.0` e bloqueando 100% dos sinais. Agora `base_balance = equity` em REAL mode. Watchlist expandida para 41 pares (ELITE_40_MATRIX + SOLUSDT). SOLUSDT removido do `ASSET_BLOCKLIST`. Remoção da restrição `LATERAL_ONLY_DECOR`. Escudo de correlação elevado para 0.95. Reset Nuclear integrado com Redis FLUSHDB. Sistema operacional com 8 posições ativas simultâneas no modo REAL da OKX.

---

## Recursos e Funcionalidades Ativas

### 1. Camada de Execução Descentralizada (Actor Model)
* **FlashAgent (V2.0):** Escritor único de stops e progressão de escadinha. Monitora todos os slots ativos a cada 1s. Usa `OrderProjectionService` como SSOT para cálculo de ROI, stops e níveis.
* **SlotOperatorAgent (1-40):** Agentes de observação e failsafe de slot. Não são mais escritores primários de escadinha ou emancipação.
* **CaptainAgent:** Despachante de sinais com quality gate. Consenso de frota com threshold de 20%.
* **BankrollManager:** Abertura de ordens com stop inicial adaptativo (estrutural + ATR) e ExecutionCapacityGate.

### 2. Escadinha Unificada (Ordem Única no Slot)
A mesma ordem permanece no slot do início ao fim. Cada alvo rompido apenas promove o stop.

**Regime LATERAL (ADX < 25):**
| Gatilho ROI | Stop sobe para | Fase |
|---|---|---|
| 30% | 5% | ESCADINHA |
| 50% | 25% | ESCADINHA |
| 70% | 50% | ESCADINHA |
| 100% | 80% | ESCADINHA |
| 150% | 110% | TRAILING |
| 200%+ | WAVE...APEX...ULTRA_* | TRAILING |

**Regime TENDÊNCIA (ADX ≥ 25):**
| Gatilho ROI | Stop sobe para | Fase |
|---|---|---|
| 50% | 15% | ESCADINHA |
| 100% | 50% | ESCADINHA |
| 130% | 110% | ESCADINHA |
| 150%+ | idêntico ao Lateral | TRAILING |

**Pós-1200%:** Níveis `ULTRA_*` a cada 200% ROI, stop = gatilho − 200%.

### 3. Portfolio Guardian & Algoritmo Knife-Drop (DESATIVADO ❌)
* O monitoramento de ROI consolidado e o Facão Global foram desativados.
* Controle de stops 100% descentralizado via FlashAgent por par.
* `PortfolioGuardian` mantém apenas heartbeat de integridade.

### 4. Moonbags (REMOVIDAS ❌)
* Entidade Moonbag completamente removida do runtime.
* ~580 linhas de código morto eliminadas de `flash_agent.py` e `slot_operator.py`.
* Métodos removidos: `_scan_all_moonbags`, `_process_moonbag`, `_update_moonbag_sl`, `_emancipate_slot`, `_close_moonbag`, `_forensic_close_paper_moonbag`, `_process_sentinel_stop`, `_check_gas_favorable_simple`, `_calculate_escadinha_stop`, `_get_status_risco`.
* Constantes antigas removidas: `ESCADINHA_DEGRAUS`, `ESCADINHA_BLITZ`, `MOONBAG_TRAILING_LEVELS`.
* Banco de dados mantém tabela `moonbags` para compatibilidade com dados históricos; novas moonbags não são criadas.

### 5. Camada de Dados e Sincronização
* **PostgreSQL (SSOT / Railway):** Banco primário: banca, slots, trade_history, radar_pulse.
* **Firebase / RTDB (Espelho de Transmissão):** UI reativa com latência ultra-baixa.
* **Hermes Broker (MQTT/gRPC):** Porta `50051`.

---

## Componentes do Sistema e Status

| Componente | Função | Porta | Status |
| :--- | :--- | :--- | :--- |
| **FastAPI Backend** | API + WebSockets | `8085` | `OPERATIONAL ✅` |
| **Cockpit UI** | Interface unificada Desktop/Mobile | `-` | `OPERATIONAL ✅` |
| **PostgreSQL** | SSOT Railway | `5432` | `ONLINE ✅` |
| **Firebase RTDB** | Sincronizador UI | `-` | `ONLINE ✅` |
| **OKX** | Exchange real (Portfolio Margin) | `-` | `REAL ✅` |

---

## Melhorias e Atualizações (Jun 16)

### V111.2: Filtro de Regime, Stop Cap e Bloqueio de Contra-Tendência

* **Filtro de Regime de Mercado (BankrollGuardian):** Implementado `_get_market_data()` que lê ADX e direção do BTC (15m + 1h). Três zonas de decisão:
  - **Mercado Morto (ADX < 22):** Nenhuma entrada permitida — volatilidade insuficiente para operar.
  - **Zona de Transição (ADX 22-25):** Apenas trades a favor da direção do BTC (LONG se UP, SHORT se DOWN).
  - **Tendência Confirmada (ADX ≥ 25):** Bloqueio absoluto de contra-tendência (SHORT em bull, LONG em bear).
* **Stop Inicial com Teto Máximo (BankrollManager):** `_calibrate_initial_stop()` agora limita o ROI do stop a **30% máximo**. Se ATR/estrutura indicar um stop mais largo, o stop é reposicionado automaticamente. Logs `[STOP-CAP]` para debug.
* **Arquivos alterados:**
  - `backend/config.py` — novas constantes `ADX_MIN_ENTRY=22`, `ADX_TRENDING_THRESHOLD=25`, `ADX_STRONG_TREND_THRESHOLD=30`, `MAX_INITIAL_STOP_ROI=30`.
  - `backend/services/agents/bankroll_guardian.py` — `_get_market_data()` + filtro de regime em `authorize_new_trade()`.
  - `backend/services/bankroll.py` — cap de stop em `_calibrate_initial_stop()`.

### V111.1: REAL Mode Fix
* **Correção do BankrollGuardian:** `base_balance` agora usa o equity real da exchange em REAL mode, resolvendo o falso `PRESERVACAO_TOTAL` que bloqueava todas as ordens.
* **Resultado:** Sistema passou de 0 para 8 posições ativas com PnL médio de +4.4% imediatamente após o deploy.
* **Arquivo alterado:** `backend/services/agents/bankroll_guardian.py` — após computar o equity, seta `base_balance = equity` quando `OKX_EXECUTION_MODE != "PAPER"`.

### V111.0: Watchlist, LATERAL_ONLY_DECOR, CORRELATION_SHIELD & Redis
* **Watchlist Ampliada:** Expansão para 41 ativos unificados (`ELITE_40_MATRIX` + `SOLUSDT`).
* **SOLUSDT liberado:** Removido do `ASSET_BLOCKLIST` que o mantinha como "monitoring only".
* **Regime de Mercado Flexível:** Remoção de travas de tendência para mercado lateral (`LATERAL_ONLY_DECOR`), permitindo operações mais ágeis.
* **Escudo de Correlação:** Implementação do `CORRELATION_SHIELD = 0.95` (elevado de 0.85) para mitigar o risco de sobreposição direcional em ativos correlacionados.
* **DECOR_HUNTER Mode:** BankrollManager opera com max 10 slots, margem $2.00/par, usando live equity como referência.
* **Sincronia Total de Reset:** Implementação de flush profundo nos caches e filas do Redis unificado com resets PostgreSQL e Firebase.

## Código e Componentes Removidos / Depreciados
- `flash_agent.py`: −480 linhas (removido tratamento de moonbags e sentinel)
- `slot_operator.py`: −90 linhas (removidas referências de escadinha antiga e emancipação)
- `order_projection_service.py`: `should_emancipate` sempre `False`
- `portfolio_guardian.py`: Desativado o Knife-Drop ativo, reduzido a liveness heartbeat apenas.
