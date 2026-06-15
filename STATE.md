# Estado Atual do Projeto — 1Crypten (SaaS v5.5.0 / V110.980)

## Resumo Executivo
* **Versão:** `V110.980: BlitzSniper Restringido & Identificação de Estratégias (20 Pares)`
* **Data:** 2026-06-13
* **Estado:** `OPERATIONAL ✅`
* **Escopo:** Transição para a arquitetura de **Consenso Híbrido com Hierarquia de Prioridades** e **BlitzSniper** operando exclusivamente nos **20 pares oficiais** (`RADAR_WATCHLIST`), blindando o sistema contra ativos não homologados. Adicionalmente, implementamos o mapeamento preciso das estratégias geradoras de sinais no Cockpit (`DECOR`, `V-RECOVERY`, `BOX-BREAKOUT`) para evitar rotulações genéricas como `TREND`, bem como um design sutil e profissional para as barras de rolagem (scrollbars). A margem por ordem segue em **$2.00** fixos.

---

## Recursos e Funcionalidades Ativas

### 1. Camada de Execução Descentralizada (Actor Model)
* **SlotOperatorAgent (1-4):** 4 instâncias de agentes de slot totalmente independentes gerenciando individualmente o ciclo de vida dos trades (Gênesis, Trailing Stop/Escadinha e arquivamento).
* **CaptainAgent:** Despachante de sinais puro e orquestrador central de consenso de frota (threshold de consenso tático de 60%).
* **OKX Master Bypass:** Se `OKX_API_KEY_MASTER` estiver no `.env`, o Capitão força a execução cirúrgica global na conta Master ("master") ignorando a Bybit.

### 2. Sniper & Trailing Stop Progressivo (Escadinha Integrada)
* Monitoramento de altíssima frequência (ciclo de **0.2 segundos**) para capturar pavios rápidos de mercado.
* **Gatilhos de ROI da Escadinha Unificada (Sem Emancipação Física):**
  * **T1 (Risk-Zero):** 50% ROI → Stop Loss movido para +15% ROI (Fôlego/Taxas)
  * **T2 (Lucro Garantido):** 100% ROI → Stop Loss movido para +50% ROI
  * **T3 (Sucesso Total):** 130% ROI → Stop Loss movido para +110% ROI
  * **T4 (Alvo Emancipada):** 150% ROI → Stop Loss movido para +110% ROI
  * **T5 (Wave):** 200% ROI → Stop Loss movido para +150% ROI (Direto no Slot)
  * **T6 (Rocket):** 300% ROI → Stop Loss movido para +220% ROI (Direto no Slot)
  * **Níveis subsequentes:** Segue o trailing de moonbag integrado (STAR, CROWN, SUPERNOVA, GOD_MODE, etc.) até o APEX de 1200% e além.

### 3. Portfolio Guardian & Algoritmo Knife-Drop (DESATIVADO ❌)
* **Desativado em Produção (V2.0):** Em favor da arquitetura de ultra-diversificação de até 40 slots paralelos, o monitoramento de ROI consolidado e o botão de pânico global "Knife-Drop" (Facão) foram desativados para evitar o encerramento indevido de posições saudáveis devido à variação de outros pares.
* **Heartbeat de Integridade:** O `PortfolioGuardian` mantém apenas um loop minimalista de pulso (heartbeat) para o `SentinelAuditor` validar que o módulo está ativo e operacional no ecossistema de microsserviços.
* **Gerenciamento Descentralizado:** O controle de stops, alvos e o mecanismo "Flash Risco Zero" agora são executados de forma 100% descentralizada e cirúrgica pelo **FlashAgent** diretamente nos slots operacionais.

### 4. Camada de Dados e Sincronização
* **PostgreSQL (SSOT / Railway):** Banco de dados primário guardando banca, slots, histórico de ordens (`trade_history`) e estado de persistência do Radar Pulse (`radar_pulse`).
* **Firebase / RTDB (Espelho de Transmissão):** Transmissão reativa para o Cockpit Dashboard com latência ultra-baixa.
* **Hermes Broker (MQTT/gRPC):** Servidor gRPC na porta `50051` e cliente MQTT para envio leve de cohorts.
* **Fallbacks Híbridos de Rede:** Em caso de queda ou inatividade deliberada do SDK do Firebase em servidores cloud, o backend direciona de forma transparente toda a leitura de histórico e pulso de radar diretamente para o PostgreSQL, evitando vazios e preservando o funcionamento da UI.

---

## Componentes do Sistema e Status de Serviços

| Componente | Função | Porta | Status |
| :--- | :--- | :--- | :--- |
| **FastAPI Backend** | API de sincronização e WebSockets | `8085` | `OPERATIONAL ✅` |
| **Hermes Dashboard** | Kanban e interface interativa do Hermes | `9119` | `OPERATIONAL ✅` |
| **gRPC Hermes** | Tenancy em tempo real e gRPC Stream | `50051` | `OPERATIONAL ✅` |
| **Cockpit UI** | Interface Cyberpunk com Vault unificado Desktop/Mobile | `-` | `OPERATIONAL ✅` |
| **PostgreSQL** | Banco de dados Master e persistência de pulso | `5432` | `ONLINE ✅` |
| **Firebase RTDB** | Sincronizador reativo da UI | `-` | `ONLINE ✅` |
| **N8N DAG** | Macro-orchestrator (ciclo 5min, 4 paths paralelos) | `-` | `ONLINE ✅` |
| **OKX Master** | Portfolio Margin + WebSocket privado (Hermes broker) | `-` | `CONNECTED ✅` |

## Testes Validados

### ✅ Ceifeiro 1200% (test_ceifeiro.py)
Validação completa do HarvesterAgent com **0 falhas**:
- Trailing Stop Progressivo: WAVE (200%), ROCKET (300%), STAR (400%), CROWN (500%), SUPERNOVA (600%), GOD_MODE (700%), CHOKE_HOLD (800%-1200%)
- Colheita Parcial: PRIMEIRA_COLHEITA (65% aos 250%), GOLDEN_COLHEITA (85% aos 600%), Safety Net (80% aos 700%), Parabolic Climax (90% aos 1000%)
- Paciência Absoluta: SL nunca regride
- Cooldown de 30 min respeitado entre colheitas

### ✅ Jornada Completa (test_jornada_completa.py)
Validação ponta a ponta com **0 falhas**:
- **FASE 1 - Slot Ativo**: STOP INICIAL (-100% ROI) → Risk-Zero (+80% ROI / SL +15%) → EMANCIPAÇÃO (+150% ROI / SL +110%)
- **FASE 2 - Moonbag**: WAVE (200%) → ROCKET (300%) → STAR (400%) → CROWN (500%) → SUPERNOVA (600%) → GOD_MODE (700%) → CHOKE_HOLD (800-1200%) com colheitas parciais no caminho
- **FASE 3 - Tabela Consolidada**: Visualização completa da trajetória de $0 a 1200% ROI
