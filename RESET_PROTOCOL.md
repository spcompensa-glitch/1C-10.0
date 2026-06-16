# ☢️ PROTOCOLO DE RESET NUCLEAR (ESTADO ZERO)

Este documento define o procedimento para resetar completamente o sistema 1Crypten para fins de teste ou reinício de banca.

### 🚀 Comando Rápido
Execute o comando abaixo no terminal da raiz do projeto:

```bash
python backend/nuclear_reset_complete.py
```

Ou via API (requer autenticação):
```
POST /api/system/nuclear-reset
```

### 🛠️ O que o Reset faz?
1. **Limpa Slots**: Todos os 40 slots voltam ao estado `LIVRE`.
2. **Reseta Banca**: O saldo total volta para **$100.00** (PAPER) ou reflete o equity real da exchange (REAL mode).
3. **Apaga Histórico**: Deleta permanentemente o histórico de trades, registros de Gênese e radar_pulse no Postgres.
4. **Redis FLUSHDB**: Limpa todos os caches voláteis — tickers, CVD, OI, LS Ratios, locks e filas de processamento.
5. **Firebase RTDB**: Reseta active_slots, vault_history e estado da banca no espelho de transmissão.
6. **Firestore**: Limpa o paper_engine (posições simuladas).
7. **Reseta estado interno**: Limpa tocaias, cooldowns, daily_symbol_trades, processing_locks, pending_slots e recent_openings do CaptainAgent em memória.

### ⚠️ Aviso Importante
Este procedimento é **irreversível**. Use-o apenas quando desejar iniciar um novo ciclo ou validar correções na lógica de Stop/Escadinha.

### 🔧 Configuração de Banca Pós-Reset
Após o reset, verifique as variáveis de ambiente no Railway:
- **PAPER mode:** `OKX_EXECUTION_MODE=PAPER` e `OKX_SIMULATED_BALANCE=100`
- **REAL mode:** `OKX_EXECUTION_MODE=REAL` com chaves OKX configuradas

---
*Documentação V2.0 - 1Crypten V111.1*
