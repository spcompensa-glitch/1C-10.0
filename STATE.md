# Estado Atual do Sistema — 1Crypten 7.0

*Ultima atualizacao: 2026-06-24*

---

## Resumo

- **Estado**: OPERACIONAL (producao OKX + sandbox simultaneos)
- **Versao do codigo**: V110.x (multiplas versoes por agente — ver MASTER_ARCHITECTURE.md secao 13)
- **Exchange**: OKX (Portfolio Margin)
- **Deploy**: Railway + Docker

---

## Componentes Ativos

| Componente | Status | Descricao |
|------------|--------|-----------|
| FastAPI Backend | ATIVO | API + WebSockets, porta 8085 |
| Cockpit UI | ATIVO | Dashboard desktop/mobile, ~430KB |
| PostgreSQL | ATIVO | SSOT persistente (Railway) |
| Firebase RTDB | ATIVO | Sincronizacao UI em tempo real |
| OKX REST | ATIVO | Execucao de ordens |
| OKX WebSocket | ATIVO | Feed de precos em tempo real |
| FlashAgent | ATIVO | Gestao de stops, ciclo 1s |
| CaptainAgent | ATIVO | Quality gate, routing de sinais |
| BankrollGuardian | ATIVO | Autorizacao de trades |
| OracleAgent | ATIVO | Deteccao de regime (ADX) |
| FleetAudit | ATIVO | Reconciliacao 20s |
| BlitzSniper | ATIVO | Extracao M30 |
| Librarian | ATIVO | DNA de ativos, rankings |
| MacroAnalyst | ATIVO | Risco macro BTC |
| WhaleTracker | ATIVO | Fluxo institucional |
| TradeAnalyst | ATIVO | Autopsia pos-trade |
| Quartermaster | ATIVO | Classificacao leverage |
| HermesAgent | ATIVO | Compliance/chat |
| PortfolioGuardian | DESATIVADO | Heartbeat apenas |
| SentinelAgent | ATIVO | Failsafe de posicoes |

---

## Regime de Mercado

O sistema opera exclusivamente com gating por regime ADX:

| ADX | Regime | Estrategias Permitidas |
|-----|--------|----------------------|
| < 25 | LATERAL | DECOR SHADOW, DECOR_HUNTER |
| >= 25 | TENDENCIA | VELOCITY FLOW, ALPHA SHIELD |

**Filtro de direcao BTC**: SMA 200 diaria determina se so LONG (acima) ou so SHORT (abaixo) sao permitidos.

---

## Escadinha de Stops

### Lateral (simplificada)
- 5% ROI -> stop -10%
- 10% ROI -> stop 0% (break-even)
- 15% ROI -> saida parcial 50%
- 20%+ ROI -> trailing dinamico

### Tendencia (progressiva)
10 niveis de BREAKEVEN ate STAR (400% ROI), depois CROWN, SUPERNOVA, GOD_MODE, CHOKE_PREP, CHOKE, HYPER, APEX (1200%), e niveis ULTRA_* a cada 200% acima.

Veja `MASTER_ARCHITECTURE.md` secao 4 para a tabela completa.

---

## Limites Operacionais

| Parametro | Valor |
|-----------|-------|
| Max slots (config) | 16 |
| Max slots (guardian ranging) | 20 |
| Max slots (guardian trending) | 40 |
| Leverage padrao | 50x |
| Margem por slot (lateral) | $2.00 |
| Margem por slot (trending) | $1.00 |
| Teto stop inicial | 30% ROI |
| Intervalo FlashAgent | 1s |
| Intervalo FleetAudit | 20s |
| Intervalo scan radar | 5s |

---

## Funcionalidades Removidas (codigo ainda parcialmente presente)

| Feature | Status | Detalhe |
|---------|--------|---------|
| Moonbags | REMOVIDA do runtime | Entidade nao e mais criada. Codigo legado em `fleet_audit.py`, `database_service.py` e `firebase_service.py` ainda referencia moonbags para dados historicos |
| Portfolio Guardian (Knife-Drop) | DESATIVADO | Mantem apenas heartbeat |
| `should_emancipate` | SEMPRE False | Em `order_projection_service.py` |

---

## Conflitos Conhecidos no Codigo

1. **RISK_ZERO threshold**: `chat.py` (80%) vs `hermes_agent.py` (50%)
2. **Max slots**: `config.py` (16) vs `bankroll_guardian.py` (20/40) — camadas diferentes
3. **Reset banca**: `admin.py` diz $100, comentarios dizem $20
4. **Referencias Bybit**: `market.py` ainda usa nomes `BybitRest`, `BybitWS` (legado)
5. **Dois apps FastAPI**: Root `main.py` (Firebase-first) e `backend/main.py` (Postgres-first)

---

## Endpoints Principais

| Rota | Funcao |
|------|--------|
| `GET /api/health` | Health check com versao |
| `GET /api/slots` | Todos os slots ativos |
| `GET /api/system/state` | Estado completo do sistema |
| `GET /api/radar/pulse` | Sinais do radar |
| `GET /api/radar/regimes` | Regime por par |
| `POST /api/admin/reset-system` | Nuclear reset |
| `POST /api/hermes/chat` | Chat com IA |

---

*Baseado no codigo-fonte. Nao em historico de versoes.*
