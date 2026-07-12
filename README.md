# 1Crypten 7.0 — Elite Trading System

Sistema de trading automatizado para cripto na OKX. App FastAPI unico que roda o motor real + tres laboratorios de forward-testing (Sandbox, Swing Lab, Scalping Lab), com gestao de risco por IA e stops progressivos (escadinha).

> Arquitetura completa e a fonte de verdade tecnica: **[MASTER_ARCHITECTURE.md](./MASTER_ARCHITECTURE.md)**.

---

## Quick Start

**Requisitos:** Python 3.12+ e credenciais OKX.

```bash
git clone https://github.com/JonatasOliveira1983/1C-7.0.git
cd 1C-7.0
pip install -r requirements.txt
cp .env .env.local   # edite com suas credenciais OKX

# Inicia o app (entry point unico)
uvicorn backend.main:app --host 0.0.0.0 --port 8085
```

- **URL:** http://localhost:8085
- **Login padrao:** `admin` / `admin123`

---

## Configuracao (variaveis criticas)

```bash
OKX_EXECUTION_MODE=REAL          # REAL = live | PAPER = simulado
OKX_API_KEY_MASTER=<chave>
OKX_API_SECRET_MASTER=<secret>
OKX_PASSPHRASE_MASTER=<passphrase>
OKX_TESTNET=False
PORT=8085
JWT_SECRET_KEY=<chave-aleatoria>
FIREBASE_CREDENTIALS_PATH=serviceAccountKey.json   # opcional
```

---

## Deploy

- **Plataforma:** Railway + Docker (Python 3.12-slim, PORT 8085).
- **Entry point:** `uvicorn backend.main:app --host 0.0.0.0 --port $PORT --workers 1`.
- **Health check:** `GET /api/health`.
- Branch `main` → auto-deploy.

---

## Endpoints principais

| Rota | Metodo | Funcao |
|------|--------|--------|
| `/api/health` | GET | Health check |
| `/api/slots` | GET | Slots ativos |
| `/api/system/state` | GET | Estado do sistema |
| `/api/radar/pulse` | GET | Sinais do radar |
| `/api/sandbox/stats` | GET | Estatisticas do sandbox |
| `/api/hermes/chat` | POST | Chat IA (Hermes) |
| `/api/auth/login` | POST | Login (JWT) |
| `/api/admin/reset-system` | POST | Nuclear reset |

Lista completa de routers/prefixos em `MASTER_ARCHITECTURE.md` (secao 10).

---

## Testes

```bash
pytest                     # todos
pytest -m "not slow"       # apenas rapidos
pytest --cov=backend/      # com cobertura
```

---

## Troubleshooting

| Problema | Causa | Solucao |
|----------|-------|---------|
| "Only sending to Sandbox" | `OKX_EXECUTION_MODE=PAPER` | Setar `REAL` no .env |
| Erro 429 OKX | Muitas chamadas rapidas | OKXCommandQueue (anti-429) ja ativo |
| Dashboard nao atualiza | WebSocket morto | Reiniciar backend |
| Slots nao abrem | Regime gate (ADX) | Verificar `/api/system/state` |

---

**Mantenedor:** Jonatas Oliveira (@JonatasOliveira1983)
**Repositorio:** https://github.com/JonatasOliveira1983/1C-7.0
