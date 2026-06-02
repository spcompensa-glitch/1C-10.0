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

## 🛡️ Segurança e Robustez
* **Modo de Operação Failsafe:** O sistema detecta automaticamente a ausência de chaves de API reais e migra instantaneamente para o **modo PAPER (simulação)** com saldo inicial injetado.
* **Autenticação:** JWT Token ativo no backend e controle Fortress Bypass com a senha de acesso padrão administrador configurada em ambiente seguro.
