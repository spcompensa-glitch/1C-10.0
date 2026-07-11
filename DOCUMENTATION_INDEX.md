# 1Crypten — Indice de Documentacao

*Atualizado em 2026-07-11 (V126). Baseado no codigo-fonte.*

---

## Documentos Principais

| Documento | Descricao |
|-----------|-----------|
| **[MASTER_ARCHITECTURE.md](./MASTER_ARCHITECTURE.md)** | Arquitetura completa do sistema: agentes, fluxo de execucao, escadinha de stops, endpoints, constantes, watchlists |
| **[STATE.md](./STATE.md)** | Estado atual: componentes ativos, regime de mercado, limites operacionais, conflitos conhecidos |
| **[SNIPER_PROTOCOLS.md](./SNIPER_PROTOCOLS.md)** | Protocolos de trading: estrategias, escadinha detalhada, filtros de risco, quality gate |
| **[RESET_PROTOCOL.md](./RESET_PROTOCOL.md)** | Procedimentos de reset do sistema |
| **[README.md](./README.md)** | Quick start, visao geral, deploy, endpoints principais |

---

## Documentacao do Frontend

| Documento | Descricao |
|-----------|-----------|
| **[frontend/README.md](./frontend/README.md)** | Arquitetura do frontend |
| **[frontend/LOGIN_GUIDE.md](./frontend/LOGIN_GUIDE.md)** | Fluxo de autenticacao |
| **[frontend/hermes-chat.html](./frontend/hermes-chat.html)** | Hermes Chat — Interface de conversacao com IA (V126) |
| **[frontend/memory_galaxy.html](./frontend/memory_galaxy.html)** | Memory Galaxy — 3D galaxy visualization (V126) |

---

## Referencia de Codigo

| Documento | Descricao |
|-----------|-----------|
| **[ARCHITECTURE_REFERENCE.md](./ARCHITECTURE_REFERENCE.md)** | Referencia tecnica completa: todas as constantes, thresholds, endpoints, agentes — extraido diretamente do codigo |

---

## Regras e Padroes

| Documento | Descricao |
|-----------|-----------|
| **[RULES.md](./RULES.md)** | Referencia para regras — aponta para SNIPER_PROTOCOLS.md e MASTER_ARCHITECTURE.md |
| **`.opencode/skills/`** | Skills reutilizaveis (backend-patterns, database-migrations, testing, deployment, security) |

---

## Fluxos Principais

### Sinal → Execucao
```
Signal Generation
    ↓
CaptainAgent (Quality Gate)
    ↓
Regime Gating (Oracle)
    ├─→ LATERAL? DECOR SHADOW
    └─→ TENDENCIA? VELOCITY FLOW + ALPHA SHIELD
    ↓
BankrollManager (Capacidade)
    ├─→ Sandbox: simulate_order()
    └─→ Real: place_atomic_order()
    ↓
FlashAgent (Stops)
    ├─→ Monitora 1s
    ├─→ Atualiza stop
    └─→ Fecha no SL/TP
```

### Atualizacao do Dashboard
```
Backend (WebSocket)
    ├─→ Slots: 500ms
    ├─→ Tickers: 1s
    ├─→ Status: 5s
    ↓
Frontend (HTML/JS)
    ├─→ Cockpit: slots, banca, radar
    └─→ Render em tempo real
```

---

## Categorias de Testes

| Categoria | Descricao |
|-----------|-----------|
| Unitarios | Logica de funcoes individuais |
| Integracao | Interacao entre componentes (mock OKX API) |
| E2E | Fluxo completo sinal → execucao |

### Executar Testes
```bash
pytest                           # Todos
pytest -m "not slow"             # Apenas rapidos
pytest --cov=backend/            # Com cobertura
```

---

## Mapa de Solucao de Problemas

| Problema | Causa Raiz | Solucao |
|----------|-----------|---------|
| "Only sending to Sandbox" | `OKX_EXECUTION_MODE=PAPER` | Setar REAL no .env |
| Erro 429 OKX | Muitas chamadas rapidas | OKXCommandQueue (anti-429) |
| Dashboard nao atualiza | WebSocket morto | Reiniciar backend |
| Slots nao abrem | Regime gate bloqueando | Verificar ADX |
| Frontend nao carrega | Cache do browser | Ctrl+Shift+Delete |

---

## Checklist de Deploy

- [ ] Testes passando: `pytest backend/tests/`
- [ ] Variaveis de ambiente configuradas
- [ ] Frontend construido: `npm run build`
- [ ] Dependencias instaladas: `pip install -r requirements.txt`
- [ ] Banco inicializado
- [ ] Backend iniciando: `python main.py`
- [ ] Login funcionando: http://localhost:8085/
- [ ] Cockpit carregando: http://localhost:8085/cockpit.html
- [ ] WebSocket conectado (DevTools Network)
- [ ] Ordem teste em sandbox

---

## Contato

- **Repositorio**: https://github.com/JonatasOliveira1983/1C-7.0
- **Commits**: https://github.com/JonatasOliveira1983/1C-7.0/commits/main
- **Issues**: https://github.com/JonatasOliveira1983/1C-7.0/issues

---

*Baseado no codigo-fonte. Nao em historico de versoes.*
