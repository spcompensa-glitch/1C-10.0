# 1Crypten — Protocolo de Reset

*Baseado no codigo-fonte. Atualizado em 2026-06-24.*

---

## 1. Tipos de Reset

### 1.1 Nuclear Reset (Completo)

**Endpoint**: `POST /api/admin/reset-system`

**O que limpa**:
- Slots ativos e historico
- Dados de banca
- Cache do Redis (tickers, CVD, OI, LS Ratios, locks)
- Estado do CaptainAgent (active_tocaias, processing_lock, cooldown_registry, daily_symbol_trades, slot_vacancy_tracker)
- BankrollManager (pending_slots, recent_openings)
- Firebase RTDB (system_state, active_slots, radar_pulse)
- Postgres (slots, radar_pulse, banca_status)

**Nao limpa**:
- Credenciais OKX
- Configuracoes de usuario
- Historico de trades (trade_history)

### 1.2 Reset de Sandbox

**Endpoint**: `POST /api/sandbox/reset`

**O que limpa**:
- Trades simulados
- Estatisticas sandbox

### 1.3 Hard Reset de Slot

**Funcao**: `hard_reset_slot()`

**O que limpa**:
- genesis_id, order metadata
- execution_audit
- Alvos, regime, score, flags auxiliares

**Preserva**:
- exit_price, pnl, current_stop_at_close (quando fechamento ja trouxe dados do executor)

---

## 2. Via Admin Panel

1. Acessar `/config` ou `/admin`
2. Clicar em "Nuclear Reset"
3. Confirmar acao

---

## 3. Via API

```bash
curl -X POST http://localhost:8085/api/admin/reset-system \
  -H "Authorization: Bearer <JWT_TOKEN>"
```

---

## 4. Pos-Reset

Apos nuclear reset:
1. Sistema reinicia com slots vazios
2. OracleAgent recalibra regime (150s de estabilizacao)
3. CaptainAgent retoma scan de sinais
4. FlashAgent comeca monitorar novos slots
5. Dashboard mostra estado limpo

---

## 5. Recuperacao

Se o sistema nao responder apos reset:
1. Verificar logs do backend
2. Checar conexao com PostgreSQL
3. Verificar credenciais OKX
4. Reiniciar container Railway se necessario

---

*Endpoint real: `POST /api/admin/reset-system`. Nao existe script `nuclear_reset_complete.py`.*
