# Estado Atual do Projeto — 1Crypten (SaaS v5.5.0 / V111.5)

## Resumo Executivo
* **Versão:** `V111.5: OKX REAL Mode Activation, Protobuf Version Fix, Score Threshold Upgrade & Escadinha 30% Protection`
* **Data:** 2026-06-18
* **Estado:** `OPERATIONAL REAL ✅`
* **Escopo:** Ativação real na OKX (`OKX_TESTNET=False`), correção do conflito crítico de versão do Protobuf (`protobuf==6.31.1`), aumento do threshold de score do Radar de 85 para `90` para filtrar trades de baixa probabilidade, inserção definitiva de **RENDERUSDT, ICPUSDT e CHZUSDT** na `ASSET_BLOCKLIST` devido ao péssimo histórico no sandbox, e inclusão de um novo degrau de proteção da escadinha (`30% ROI -> +5% Stop Loss`) salvando lucros antes de reversões.

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

## Melhorias e Atualizações (Jun 18)

### V111.4: PAPER-TEST-FIRE Purge & DECOR_HUNTER Pearson Fix

* **Remoção total do PAPER-TEST-FIRE:** Todos os bypasses de desenvolvimento foram removidos do runtime. As validações de Engine Space, Pullback Hunter, Needle Flip e Sentinela ADX agora executam a lógica real de mercado.
* **`_wait_for_needle_flip` reativado:** Antes retornava `True` instantaneamente sem monitorar o mercado. Agora executa o protocolo completo de até 60s para confirmar entrada.
* **`_validate_price_structure` reativado:** Antes retornava sucesso imediato sem validar pullback. Agora executa o Pullback Hunter real com adaptive SL.
* **`should_bypass_ambush` corrigido:** Era hardcoded `True` (todas as ordens ignoravam a Tocaia). Agora só faz DIRECT-ENTRY se `score >= 90` ou `CVD > 50k` ou `ADX >= 50`.
* **DECOR_HUNTER 2.0 Pearson fix:** O critério `is_decorrelated` foi corrigido para exigir Pearson `< 0.35` como condição **obrigatória** (antes `confidence >= 45` bastava para aprovar, mesmo com Pearson 0.95).
* **Arquivos alterados:**
  - `backend/services/agents/captain.py` — 6 blocos de PAPER-TEST-FIRE removidos; `should_bypass_ambush` corrigido.
  - `backend/services/signal_generator.py` — PAPER-TEST-FIRE removido; `is_decorrelated` agora requer Pearson baixo.
  - `backend/services/bankroll.py` — log PAPER-TEST-FIRE removido.

### V111.3: Oracle BTC Regime SSOT

* **Oracle alinhado à grade oficial `22/25/30`:** O `OracleAgent` agora deriva `regime` com a mesma tabela operacional do `BankrollGuardian`: `RANGING` (`ADX < 22`), `TRANSITION` (`22-25`), `TRENDING` (`>= 25`) e `ROARING` (`>= 30`).
* **Direção real do BTC dentro do Oracle:** `btc_direction` passa a ser fechado no próprio Oracle por confluência `15m + 1h`, retornando `UP`, `DOWN` ou `LATERAL`.
* **Sync corrigido do `btc_variation_15m`:** O `okx_ws_public` voltou a enviar a variação de 15 minutos ao Oracle, o que corrige snapshots parciais durante produção, reboot e recovery via LKG.
* **Persistência mais fiel no LKG:** O Oracle agora restaura também `btc_variation_15m` ao recuperar o último contexto válido do Firestore.
* **Estudo histórico para recalibragem:** Adicionado `backend/scratch/study_oracle_btc_regime.py` para estudar o M-ADX do BTC na OKX e revalidar a grade `22/25/30` quando necessário.

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
