# Estado Atual do Projeto — 1Crypten (SaaS v5.5.0 / V110.701)

## Resumo Executivo
* **Versão:** `V110.701: Ceifeiro 1200% & Escadinha Expandida`
* **Data:** 2026-05-31
* **Estado:** `OPERATIONAL ✅`
* **Escopo:** Robô de trading quantitativo automatizado com orquestração descentralizada de slots, integração com OKX e monitoramento de portfólio em tempo real.

---

## Recursos e Funcionalidades Ativas

### 1. Camada de Execução Descentralizada (Actor Model)
* **SlotOperatorAgent (1-4):** 4 instâncias de agentes de slot totalmente independentes gerenciando individualmente o ciclo de vida dos trades (Gênesis, Trailing Stop/Escadinha e arquivamento).
* **CaptainAgent:** Despachante de sinais puro e orquestrador central de consenso de frota (threshold de consenso tático de 60%).
* **OKX Master Bypass:** Se `OKX_API_KEY_MASTER` estiver no `.env`, o Capitão força a execução cirúrgica global na conta Master ("master") ignorando a Bybit.

### 2. Sniper & Trailing Stop Progressivo (Escadinha)
* Monitoramento de altíssima frequência (ciclo de **0.2 segundos**) para capturar pavios rápidos de mercado.
* **Gatilhos de ROI da Escadinha:**
  * **T1 (Break-Even):** 30% ROI → Stop Loss movido para 0%
  * **T2 (Profit Bridge):** 50% ROI → Stop Loss movido para 20%
  * **T3 (Risk-Zero):** 70% ROI → Stop Loss movido para 5%
  * **T4 (Profit-Lock):** 110% ROI → Stop Loss movido para 70%
  * **T5 (Emancipação / Moonbags):** 150% ROI → Stop Loss movido para 110%

### 3. Portfolio Guardian & Algoritmo Knife-Drop
* Máquina de estados atômica unificada monitorando o ROI consolidado da conta Master.
* **Knife-Drop ("O Facão"):** Dispara pânico global e fecha em lote ordens ativas via API OKX batch-orders caso haja recuo de 15% a partir do pico de ROI (gatilho em 70% ROI).
* **Moonbag Shield:** Posições marcadas como emancipada (T5) são blindadas no `portfolio_guardian.py` e excluídas do cálculo do Facão, evitando encerramentos prematuros.

### 4. Camada de Dados e Sincronização
* **PostgreSQL (SSOT / Railway):** Banco de dados primário guardando banca, slots, histórico de ordens (`trade_history`) e estado de persistência do Radar Pulse (`radar_pulse`).
* **Firebase / RTDB (Espelho de Transmissão):** Transmissão reativa para o Cockpit Dashboard com latência ultra-baixa.
* **Hermes Broker (MQTT/gRPC):** Servidor gRPC na porta `50051` e cliente MQTT para envio leve de cohorts.
* **Fallbacks Híbridos de Rede:** Em caso de queda ou inatividade deliberada do SDK do Firebase em servidores cloud, o backend direciona de forma transparente toda a leitura de histórico e pulso de radar diretamente para o PostgreSQL, evitando vazios e preservando o funcionamento da UI.

---

## Componentes do Sistema e Status de Serviços

## Testes Validados

### ✅ Ceifeiro 1200% (test_ceifeiro.py)
Validação completa do HarvesterAgent com **0 falhas**:
- Trailing Stop Progressivo: WAVE (200%), ROCKET (300%), STAR (400%), CROWN (500%), SUPERNOVA (600%), GOD_MODE (700%), CHOKE_HOLD (800%-1200%)
- Colheita Parcial: PRIMEIRA_COLHEITA (65% aos 250%), GOLDEN_COLHEITA (85% aos 600%), Safety Net (80% aos 700%), Parabolic Climax (90% aos 1000%)
- Paciência Absoluta: SL nunca regride
- Cooldown de 30 min respeitado entre colheitas

### ✅ Jornada Completa (test_jornada_completa.py)
Validação ponta a ponta com **0 falhas**:
- **FASE 1 - Slot Ativo**: STOP INICIAL (-100% ROI) → Break-Even (+30%) → Profit Bridge (+50%) → Risk Zero (+70%) → Profit Lock (+110%) → EMANCIPAÇÃO (+150%)
- **FASE 2 - Moonbag**: WAVE (200%) → ROCKET (300%) → STAR (400%) → CROWN (500%) → SUPERNOVA (600%) → GOD_MODE (700%) → CHOKE_HOLD (800-1200%) com colheitas parciais no caminho
- **FASE 3 - Tabela Consolidada**: Visualização completa da trajetória de $0 a 1200% ROI

## Componentes do Sistema e Status de Serviços

| Componente | Função | Porta | Status |
| :--- | :--- | :--- | :--- |
| **FastAPI Backend** | API de sincronização e WebSockets | `8002`/`8085` | `OPERATIONAL ✅` |
| **gRPC Hermes** | Tenancy em tempo real e gRPC Stream | `50051` | `OPERATIONAL ✅` |
| **Cockpit UI** | Interface Cyberpunk com Vault unificado Desktop/Mobile | `-` | `OPERATIONAL ✅` |
| **PostgreSQL** | Banco de dados Master e persistência de pulso | `5432` | `ONLINE ✅` |
| **Firebase RTDB** | Sincronizador reativo da UI | `-` | `ONLINE ✅` |
