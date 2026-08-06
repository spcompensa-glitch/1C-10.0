# 1Crypten 7.0 — Elite Trading System

Sistema de trading automatizado para cripto na OKX. App FastAPI unico que roda o motor real + dois laboratorios de forward-testing (Scalping Lab e Swing Lab), com gestao de risco por IA e stops progressivos (escadinha).

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

## 🔮 Kronos Conviction Scorer (V134)

O 1C-7.0 agora conta com um **scorer de convicção baseado em séries temporais** usando o Kronos-mini (4.1M params, AAAI 2026).

### Modos de Operação

| Modo | Requisito | Descrição |
|------|-----------|----------|
| **REAL** 🚀 | `pip install kronos-forecast torch` | Inferência com Kronos-mini (CPU, ~200MB RAM, ~1-2s por predição) |
| **FALLBACK** 🛡️ | Nenhum (padrão) | Regressão linear simples — leve, rápido, sempre disponível |

O Kronos adiciona uma **5ª dimensão** ao consenso de frota do CaptainAgent, com peso de 18% no unified_score.

**Configuração** (via `.env`):
```bash
KRONOS_ENABLED=true
KRONOS_SCORE_WEIGHT=0.18
KRONOS_INTERVAL=5
KRONOS_TIMEOUT=5.0
```

**Testes**: `cd backend && pytest tests/test_kronos_scorer.py -v` (24 testes)

---

## Testes

```bash
cd backend && pytest                           # todos os testes
cd backend && pytest tests/test_kronos_scorer.py -v  # testes do Kronos (24)
pytest -m "not slow"                            # apenas rapidos
pytest --cov=backend/                           # com cobertura
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

## Changelog (V136-SWING)

### Swing Lab — Trades de 1-7 dias com stops progressivos e TP baseado em S/R

- **[SWING-TRAILING]** Trailing suave 50% (era 75%) + Breakeven +12% (era +4%) — trades duram mais sem dar lucro embora
- **[SWING-LEVERAGE]** Fix leverage: `SWING_LEVERAGE=50` (era 10, conflito com código que usava 50)
- **[SWING-PRICE-WINDOW]** Janela de preço 30min (1800s) para Swing — evita fechar em wicks de 2min
- **[SWING-GARANTIA]** GARANTIA_TRAIL split: 50% Swing / 75% Scalping (antes统一 75%)
- **[SWING-TP]** Take Profit baseado em S/R — detecta resistências acima e cria stop ratchet progressivo
- **[SWING-PATTERNS]** Detecção de padrões gráficos: Triângulos, Topo/Fundo Duplo, Head & Shoulders
- **[SWING-PATTERN-BOOST]** Padrões gráficos boostam score do sinal (+10 a +25 pontos)

### Arquivos modificados
| Arquivo | Mudança |
|---------|---------|
| `backend/services/sandbox_service.py` | GARANTIA_TRAIL split 50%/75%, Breakeven +12% Swing |
| `backend/services/sandbox_swing_service.py` | TP S/R integration, pattern detection boost |
| `backend/services/okx_ws_public.py` | `get_conservative_price_swing()` 30min window |
| `backend/services/agents/flash_agent.py` | TP hit check, swing price window |
| `backend/config.py` | `SWING_LEVERAGE=50`, `SWING_TP_*` configs |

### Arquivos criados
| Arquivo | Função |
|---------|--------|
| `backend/services/patterns/__init__.py` | Package init |
| `backend/services/patterns/triangle_detector.py` | Triângulos (simétrico/ascendente/descendente) |
| `backend/services/patterns/double_detector.py` | Topo/Fundo Duplo |
| `backend/services/patterns/hs_detector.py` | Head & Shoulders / Inverse H&S |
| `backend/services/pattern_detector.py` | PatternDetector unificado |

---

## Changelog (V134)

- **[KRONOS]** Novo serviço de scoring de convicção via séries temporais (`backend/services/kronos_scorer.py`)
- **[CAPTAIN]** Kronos integrado como 5ª dimensão no consenso de frota (peso 18% no unified_score)
- **[CONFIG]** 7 novas configurações: `KRONOS_ENABLED`, `KRONOS_MODEL_NAME`, `KRONOS_SCORE_WEIGHT`, etc.
- **[CLEANUP]** Remoção completa do legado Bybit (26 arquivos, `pybit` removido do requirements)
- **[TESTS]** 24 novos testes para o KronosScorer (24/24 passando)

**Mantenedor:** Jonatas Oliveira (@JonatasOliveira1983)
**Repositorio:** https://github.com/JonatasOliveira1983/1C-7.0
