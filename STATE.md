# Estado Atual do Projeto — 1Crypten (SaaS v5.5.0 / V110.999)

## Resumo Executivo
* **Versão:** `V110.999: Moonbag Deprecated & Dead Code Purge`
* **Data:** 2026-06-15
* **Estado:** `OPERATIONAL ✅`
* **Escopo:** Remoção total da entidade Moonbag do runtime e purga de ~580 linhas de código morto (moonbags, sentinel, escadinhas antigas). A ordem permanece no slot durante todo o ciclo de vida: `ORDER → ESCADINHA → TRAILING` sem emancipação para container separado. FlashAgent V2.0 é o escritor único de stops. Sistema opera com até 40 slots simultâneos, sem Facão Global, com gestão de risco 100% descentralizada por par. Correção de 3 bugs críticos que bloqueavam abertura de ordens (`margin`, `balance`, `settings`). Margem fixa de $2.00 por slot.

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
| **OKX Testnet** | PAPER mode | `-` | `PAPER ✅` |

---

## Bugs Corrigidos (Jun 15)
| Bug | Causa | Arquivo |
|---|---|---|
| `margin` UnboundLocalError | QM override não setava `margin` | `bankroll.py` |
| `balance` UnboundLocalError | `balance` nunca definido em `open_position` | `bankroll.py` |
| `settings` scoping BLITZ-LOOP | Import de `settings` abaixo do uso | `captain.py` |

## Código Removido (Jun 15)
- `flash_agent.py`: −480 linhas (moonbags, sentinel, constantes antigas)
- `slot_operator.py`: −90 linhas (escadinha antiga, emancipação)
- `order_projection_service.py`: `should_emancipate` sempre `False`
