# Estado Atual do Projeto — 1Crypten (SaaS v5.5.0 / V112.9)

## Resumo Executivo
* **Versão:** `V112.9: Intelligent Regime Gating & Trend Bias Filter`
* **Data:** 2026-06-21
* **Estado:** `OPERATIONAL REAL ✅`
* **Escopo:** Liberação das operações reais em mercado lateral exclusivamente para a estratégia DECOR SHADOW, implementação do filtro macro de direção do BTC (Trend Bias) em tempo real, adição de DYDX, FIL, ALGO e LTC à blocklist de ativos, e paridade total de gating macro no motor do Sandbox.
* **Watchlists e Escadinha:** Confirmada a regra de monitoração ampla (100 ativos na `RADAR_WATCHLIST` para encontrar oportunidades desgrudadas a qualquer momento) e lista reduzida de 41 ativos (`ELITE_40_MATRIX` + SOL) atuando exclusivamente em mercados com tendência confirmada (ADX >= 25) para proteção.

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
| Gatilho ROI | Stop sobe para / Ação | Fase |
|---|---|---|
| 5% | -10% (Degrau de Risco inicial reduzido) | ESCADINHA |
| 10% | 0% (Break-Even) | ESCADINHA |
| 15% | Saída Parcial de 50% (Stop mantém em 0%) | ESCADINHA |
| 20%+ | Trailing Stop Dinâmico (gatilho - 5%) | TRAILING |

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

## Melhorias e Atualizações (Jun 21)

### V112.9: Gating Inteligente Real e Filtro Macro Trend Bias do BTC

* **Liberação de Operações Reais em Mercado Lateral:** O Captain real e simulado (`captain.py`) agora permite a execução da estratégia `DECOR SHADOW` (e `DECOR_HUNTER`) em cenários de mercado lateralizado (ADX < 25), eliminando o bloqueio geral anterior.
* **Gating Estratégico por Regime:** Implementação de travas limpas por regime de volatilidade: em mercado lateral (ADX < 25), apenas `DECOR SHADOW` é aprovada; em mercado com tendência (ADX >= 25), apenas `VELOCITY FLOW` e `ALPHA SHIELD` são permitidas.
* **Filtro Macro Trend Bias (Direção do BTC):** O robô consulta a SMA 200 diária do BTC em tempo real: se o preço estiver abaixo da SMA 200 (BEARISH), apenas sinais do tipo `SHORT` são permitidos em qualquer estratégia (bloqueio de LONG). Se estiver acima da SMA 200 (BULLISH), apenas sinais do tipo `LONG` são executados (bloqueio de SHORT).
* **Paridade Total no Sandbox:** O motor do Sandbox (`sandbox_service.py`) foi atualizado para herdar o mesmo filtro de direção do BTC e gating por regime, garantindo que o laboratório estatístico replique exatamente a lógica executada nas contas reais da OKX.
* **Blocklist de Ativos Expandida:** Adicionados `DYDXUSDT`, `FILUSDT`, `ALGOUSDT` e `LTCUSDT` à `ASSET_BLOCKLIST` global (`config.py`) devido ao fraco desempenho histórico relatado nas estatísticas.

### V112.8: Degrau de Risco Progressivo (SL_5) e ROI do Stop na UI do Sandbox

* **Degrau de Risco Progressivo (Opção 2):** Injetada a regra de micro-defesa `SL_5` no stop ladder de regime lateral (`ORDER_STOP_LADDER_RANGING`): ao atingir **+5% ROI** (0.1% de preço), o stop sobe imediatamente de -20% para **-10% ROI**, cortando a perda máxima potencial pela metade no primeiro impulso antes de evoluir para Break-Even (0% a +10% ROI).
* **ROI do Stop na UI do Sandbox:** Atualizado o template de renderização da planilha do Sandbox no frontend (`sandbox.html`) para decodificar o `stop_roi` do estado do `FlashAgent` e mostrá-lo em tempo real ao lado do preço absoluto do Stop Loss (ex: `1.2454 (-10%)` ou `1.2454 (0%)`), facilitando o acompanhamento visual das escadinhas de stop.

### V112.7: Gating de Estratégia por Regime no Sandbox

* **Enforço de Regime no Sandbox:** Ajustado o Sandbox (`sandbox_service.py`) para filtrar ativamente as aberturas conforme a análise do Manus: em mercado lateral (ADX < 25), o Sandbox processa **apenas sinais de DECOR SHADOW** (D.S). Em mercado de tendência (ADX >= 25), processa **apenas VELOCITY FLOW (V.F) e ALPHA SHIELD (A.S)**. Isso alinha a simulação com as regras de produção e refina a amostragem estatística.

### V112.6: Otimização do Sandbox (Stop Dinâmico e Correção de Slippage)

* **Stop Inicial Dinâmico no Sandbox:** Calibrado o stop inicial simulado para herdar o regime atual (ADX < 25). Se estiver em mercado lateral, o Stop Loss inicial é definido em **-20% ROI** (0.4% de preço). Se estiver em tendência, permanece em **-30% ROI** (0.6% de preço).
* **Failsafe contra Slippage Virtual:** Corrigido o cálculo de PnL no loop do Sandbox. Quando um stop é violado por spikes abruptos no WebSocket (ex: INJUSDT registrando -567%), o simulador agora recalcula a saída exatamente no preço do Stop Loss configurado, evitando a distorção artificial do histórico de trades do Sandbox.

### V112.5: Escadinha e Saídas Defensivas em Mercado Lateral

* **Break-Even em 10%:** No regime lateral (ADX < 25), o stop é movido imediatamente para o preço de entrada (0% ROI) assim que a operação atinge +10% ROI, protegendo o trade contra reversões abruptas de canal.
* **Saída Parcial de 15% (TP 50%):** Ao atingir +15% ROI em mercado lateral, o FlashAgent executa o fechamento parcial de 50% da posição na OKX, registrando a mudança no audit do slot no DB (`has_taken_partial` no `execution_audit`) e atualizando a margem/tamanho do slot.
* **Trailing Stop a partir de 20%:** A partir de +20% ROI no regime lateral, o trailing stop assume o controle dinâmico travado a exactly `ROI Pico - 5%` (passo contínuo de 1%), blindando os ganhos residuais.
* **Isolamento de Tendência:** As novas regras aplicam-se estritamente quando `is_ranging == True`. O modo de tendência (`TRENDING`) mantém intocado seu stop ladder largo (50% -> 100% -> 130% -> Trailing 150%+), permitindo colher lucros superiores (300%, 500%, 800% ou mais) normalmente.

## Melhorias e Atualizações (Jun 20)

### V112.0: Proteção de Regime (Regime Gating) e Trailing Stop Agressivo D.S

* **Regime Gating:** Implementada trava rígida para impedir que o sistema opere estratégias direcionais/fortes (`VELOCITY FLOW`) quando o Oráculo indicar um mercado `LATERAL`. Em contrapartida, `DECOR SHADOW` foi restringido para não atuar em mercado de `TENDÊNCIA`.
* **Proteção em Múltiplos Níveis:** Gating aplicado no núcleo de inteligência (`signal_generator.py`), no motor de simulação (`sandbox_service.py`) e no despachante final (`captain.py`).
* **Trailing Stop 50/70 para D.S:** Otimizado o motor de projeção de ordens (`order_projection_service.py`) no regime Lateral: quando a operação atinge +50% de ROI, o stop é defendido em +40%. Ao bater +70%, o alvo principal é garantido com stop em +50%, subindo elásticamente a partir daí.
* **Cockpit UI Atualizado:** A exibição de Regimes no HUD do frontend agora especifica visualmente o status das estratégias (ex: `LATERAL (V.F PAUSADO | D.S ATIVO)`).

### V111.8: Visualização 2H Unificada, Otimização de SMA e Expansão SaaS 40 Slots

* **Exibição Padrão de 2H na UI**: O seletor de Timeframe do cockpit e do grid principal (Eagle Vision) foi ajustado para ter o timeframe de **2H** (120m) como padrão inicial, com identificação limpa `"2H INTERVAL"` no HUD.
* **Correção da Escala e Traçado da SMA**: 
  - Resolvido o TypeError causado por valores nulos na filtragem do array de SMA no frontend.
  - Ajustadas as séries de SMA 21 e SMA 100 para herdar explicitamente a escala direita (`priceScaleId: 'right'`), além de aumentar a espessura da linha (`lineWidth: 4`) para destaque.
  - Corrigido o backend (`okx_rest.py`) para expandir o limite de histórico de klines de 144 para **300 candles**, resolvendo definitivamente o corte prematuro/encurtamento visual da linha da SMA 100 amarela.
* **SaaS 40 Slots**: Modificado o core do backend (`captain.py`, `bankroll.py`, `vault_service.py`) para suportar a totalidade de slots SaaS de `1` a `40` ativos em concorrência no Postgres e Firebase.
* **Contadores de Estratégias no Sandbox**: Integrado contadores reativos na Navbar do Sandbox para mapear as 3 estratégias de forma paralela.

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
