# Requisitos do Sistema — 1Crypten V110.701

Este documento lista os requisitos necessários para execução, hospedagem e monitoramento estável do sistema de trading **1Crypten**.

---

## 💻 Ambiente de Execução
* **Runtime:** Python 3.10+ (recomendado Python 3.10.11 para estabilidade de dependências do backtest como numpy e pandas).
* **Banco de Dados Relacional:** PostgreSQL (SSOT no Railway) para persistência imutável de slots, status de banca e histórico de operações.
* **Mensageria e Sincronização:**
  * **Firebase Realtime Database:** Utilizado exclusivamente como espelho reativo de baixa latência para sincronização visual do dashboard.
  * **HiveMQ Cloud Broker:** Servidor MQTT externo para despacho de cohorts.

---

## ⚡ Conectividade & APIs
* **Exchange Integrada:** OKX API (Portfolio Margin Mode).
* **Endpoints Requeridos:**
  * WebSocket Privado da OKX para acompanhamento de posições em tempo real.
  * API HTTP de ordens em lote (`/api/v5/trade/batch-orders`) para fechamento rápido via Knife-Drop.
* **Hermes Broker:** Porta `50051` (gRPC assíncrono HTTP/2) liberada para tenancy em tempo real.
* **FastAPI Portas:** Porta `8085` por default (`Dockerfile` EXPOSE + `backend/config.py:65`). Plataformas de deploy (Railway, Cloud Run) podem injetar override via env var `PORT` em tempo de execução. O Gunicorn sempre vincula em `:$PORT`.

---

## 🌐 Configuração de Modo de Execução (REAL vs PAPER)

### Variáveis de Ambiente Essenciais

| Variável | Descrição | Valores | Default |
|:---------|:-----------|:--------|:--------|
| `OKX_EXECUTION_MODE` | Modo de operação do sistema | `PAPER` ou `REAL` | `PAPER` |
| `OKX_SIMULATED_BALANCE` | Banca simulada (usada apenas em PAPER) | número (USD) | `100.0` |
| `OKX_API_KEY` | Chave pública da OKX | string | — |
| `OKX_API_SECRET` | Chave secreta da OKX | string | — |
| `OKX_API_PASSPHRASE` | Senha da API OKX | string | — |

### Exemplo de Configuração REAL no Railway
```
OKX_EXECUTION_MODE=REAL
OKX_API_KEY=seu-api-key-aqui
OKX_API_SECRET=seu-api-secret-aqui
OKX_API_PASSPHRASE=sua-passphrase-aqui
```

> ⚠️ **IMPORTANTE:** Em REAL mode, o `BankrollGuardian` usa o **equity real da exchange** como `base_balance`, não o `OKX_SIMULATED_BALANCE`. Isso evita o falso drawdown de -80% que ativava `PRESERVACAO_TOTAL` e bloqueava todas as ordens (bug V111.1 corrigido).

### Fluxo de Detecção
1. Se `OKX_EXECUTION_MODE=REAL` e chaves OKX válidas → sistema opera na conta real
2. Se `OKX_EXECUTION_MODE=PAPER` ou chaves ausentes → sistema opera em simulação com `OKX_SIMULATED_BALANCE`

---

## 🛡️ Segurança e Robustez
* **Modo de Operação Failsafe:** O sistema detecta automaticamente a ausência de chaves de API reais e migra instantaneamente para o **modo PAPER (simulação)** com saldo inicial injetado.
* **Proteção de Drawdown em REAL mode:** O BankrollGuardian detecta drawdown real a partir do peak_equity da exchange, protegendo a banca mesmo sem referência de banca simulada.
* **Autenticação:** JWT Token ativo no backend e controle Fortress Bypass com a senha de acesso padrão administrador configurada em ambiente seguro.
* **Isolamento de Chaves:** As chaves da OKX são lidas exclusivamente de variáveis de ambiente, nunca armazenadas em código ou arquivos .env versionados.
