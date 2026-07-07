# 1Crypten — Protocolos de Trading

*Baseado no codigo-fonte. Atualizado em 2026-07-07 (V124.7).*

---

## 1. Filtro de Regime de Mercado

### 1.1 Grade ADX

| Condicao | Regime | Acao |
|----------|--------|------|
| ADX < 22 | MORTO | Nenhuma entrada permitida. Volatilidade insuficiente. |
| ADX 22-25 | TRANSICAO | Apenas trades a favor da direcao do BTC. [V124.7] M30 SWING (3 estrategias) bypassa este bloqueio via BLITZ bypass. |
| ADX >= 25 | TENDENCIA | Bloqueio de contra-tendencia. |
| ADX >= 30 | FORTE | Reforco do bloqueio contra-tendencia. |

### 1.2 Direcao do BTC

Determinada por confluencia de variacao 15m + 1h:
- Ambas positivas => UP
- Ambas negativas => DOWN
- Divergencia => LATERAL (nao bloqueia)

### 1.3 Trend Bias (SMA 200)

- Preco BTC < SMA 200 => BEARISH: so SHORT
- Preco BTC > SMA 200 => BULLISH: so LONG

---

## 2. Estrategias

### 2.0 M30 SWING — 3 Estrategias (SignalGenerator) [V124.7]

- **Regime**: LATERAL (ADX < 25) com BLITZ bypass
- **Timeframe**: 30M (analisado por SignalGenerator.analyze_m30_swing())
- **Mecanismo**: Reusa a infraestrutura completa do motor de estrategias principal:
  - DVAP/MOLA/FAS/LRT → **ALPHA SHIELD** (divergencia, squeeze, funding)
  - TREND → **VELOCITY FLOW** (SMA8/21 alinhado + volume)
  - DECOR → **DECOR SHADOW** (CVD exhaustion + RSI extremo)
- **Score minimo**: 65 (era 75 no BlitzSniper) — mais sensivel
- **Escadinha**: `ORDER_STOP_LADDER_RANGING_SWING` (gaps 2x maiores)
- **Partial TP**: +30% ROI (vs +15% scalping)
- **Leverage**: 20x (stop de preço ate ~4.0%)
- **Trailing gap**: 10% (vs 5% scalping)
- **Selecao por slot_type**: `slot_type=BLITZ_30M` ativa escada RANGING_SWING + partial TP 30%

### 2.1 DECOR SHADOW (LATERAL)

- **Regime**: ADX < 25
- **Mecanismo**: Reversao de exaustao com decorrelacao BTC
- **Requisito**: Pearson < 0.35 (obrigatorio)
- **Margem**: $2.00 por ordem
- **Max slots**: 20 (ranging)

### 2.2 DECOR_HUNTER (LATERAL)

- **Regime**: ADX < 25
- **Mecanismo**: Caca a decorrelacao com score elite
- **Bypass**: score >= 90 ou CVD > 50k ou ADX >= 50

### 2.3 VELOCITY FLOW (TENDENCIA)

- **Regime**: ADX >= 25
- **Mecanismo**: Momentum de alta, breakout
- **Margem**: $1.00 por ordem
- **Max slots**: 40 (trending)

### 2.4 ALPHA SHIELD (TENDENCIA)

- **Regime**: ADX >= 25
- **Mecanismo**: Protecao de capital, pullback

### 2.5 LRT (Liquidez de Alta Frequencia)

- **Regime**: Qualquer
- **Mecanisme**: Setup de liquidez

### 2.6 DVAP (Reversao de Exaustao)

- **Regime**: Qualquer
- **Mecanismo**: Reversao estrutural

### 2.7 FAS (Funding Squeeze)

- **Regime**: Qualquer
- **Mecanismo**: Desequilibrio de derivativos
- **Nota**: Isento de alinhamento SMA 2H

### 2.8 MOLA (Breakout de Volatilidade)

- **Regime**: Qualquer
- **Mecanismo**: Rompimento de volatilidade

### 2.9 ABCD / 1-2-3 / TREND

- **Regime**: TENDENCIA
- **Mecanismo**: Tendencias geometricas

---

## 3. Escadinha de Stops

Tres escadinhas definidas em `order_projection_service.py`, selecionadas por `slot_type`:

### 3.1 Regime LATERAL — Scalping (`ORDER_STOP_LADDER_RANGING`)

Usada por slots sem `slot_type=BLITZ_30M`. Partial TP em +15% ROI.

| Gatilho ROI | Stop (ROI) | Nome | Status |
|------------|-----------|------|--------|
| 8% | 2% | GARANTIA_TAXAS | RISCO_ZERO |
| 12% | 5% | GARANTIA_LUCRO_CURTO | RISCO_ZERO |
| 20% | 10% | GARANTIA_LUCRO_MEDIO | RISCO_ZERO |
| 32% | 18% | GARANTIA_LUCRO_ALTO | RISCO_ZERO |
| 50%+ | Trailing (-2% pico) | ALVO_MAXIMO_LATERAL | PROFIT_LOCK |

### 3.2 Regime LATERAL — Swing Blitz M30 (`ORDER_STOP_LADDER_RANGING_SWING`) [V124.6]

Usada quando `slot_type=BLITZ_30M`. Gaps 2x maiores. Partial TP em +30% ROI. Trailing gap 10%.

| Gatilho ROI | Stop (ROI) | Nome | Status |
|------------|-----------|------|--------|
| 16% | 2% | GARANTIA_TAXAS | RISCO_ZERO |
| 25% | 10% | GARANTIA_LUCRO_CURTO | RISCO_ZERO |
| 40% | 20% | GARANTIA_LUCRO_MEDIO | RISCO_ZERO |
| 60% | 35% | GARANTIA_LUCRO_ALTO | RISCO_ZERO |
| 80%+ | Trailing (-5% pico) | ALVO_MAXIMO_SWING | PROFIT_LOCK |

### 3.3 Regime TENDENCIA (`ORDER_STOP_LADDER_TRENDING`)

| Gatilho ROI | Stop (ROI) | Nome | Status |
|------------|-----------|------|--------|
| 14% | 2% | GARANTIA_TAXAS | RISCO_ZERO |
| 25% | 10% | GARANTIA_20 | RISCO_BAIXO |
| 40% | 20% | LUCRO_INICIAL | RISCO_ZERO |
| 60% | 40% | LUCRO_MEDIO | RISCO_ZERO |
| 80% | 60% | LUCRO_ALTO | RISCO_ZERO |
| 100% | 80% | LUCRO_GARANTIDO_100 | RISCO_ZERO |
| 130% | 110% | SUCESSO_TOTAL | PROFIT_LOCK |
| 150% | 110% | ALVO_150 | PROFIT_LOCK |
| 200% | 150% | WAVE | TRAIL_LOCK |
| 300% | 220% | ROCKET | TRAIL_LOCK |
| 400% | 280% | STAR | TRAIL_LOCK |
| 500% | 350% | CROWN | TRAIL_LOCK |
| 600% | 420% | SUPERNOVA | TRAIL_LOCK |
| 700% | 500% | GOD_MODE | TRAIL_LOCK |
| 750% | 600% | CHOKE_PREP | TRAIL_LOCK |
| 800% | 650% | CHOKE | TRAIL_LOCK |
| 1000% | 800% | HYPER | TRAIL_LOCK |
| 1200% | 1000% | APEX | TRAIL_LOCK |

### 3.4 Pos-APEX

A partir de 1200% ROI, niveis `ULTRA_*` a cada 200%. Stop = gatilho - 200%.

---

## 4. Stop Inicial Inteligente

- **Calculo**: ATR + suporte/resistencia estrutural
- **Teto**: 30% ROI (configuravel)
- **LONG**: stop abaixo da invalidacao tecnica
- **SHORT**: stop acima da invalidacao tecnica
- **Se stop > teto**: reposicionado para o teto
- **Se stop > max_risk_pct * 1.35**: entrada bloqueada

---

## 5. Quality Gate do Capitao

- **Threshold dinamico**: 35% (2+ slots livres) ou 40% (normal)
- **Consenso de frota**: Macro 15%, Whale 25%, SMC 30%, OnChain 30%
- **Bypass PAPER**: Nao — sinais bloqueados permanecem bloqueados em PAPER
- **Contrato OKX**: Avaliado antes do quality gate final

---

## 6. BankrollGuardian

### 6.1 Modos de Operacao

| Modo | Condicao | Slots | Score Minimo |
|------|----------|-------|-------------|
| ACUMULACAO | Equity >= base | 20/40 | Elevado |
| CAUTELOSO | Drawdown moderado | Reduzido | Elevado |
| DEFESA | Drawdown alto | Minimo | Maximo |
| PRESERVACAO_TOTAL | Equity critica | 0 | - |

### 6.2 Limites de Slots

| Camada | Lateral | Tendencia |
|--------|---------|-----------|
| config.py | 16 | 16 |
| bankroll_guardian.py | 20 | 40 |
| captain.py (hardcoded) | 20 | 20 |

**Nota**: Existem multiplas camadas de limite. O Guardian e o mais restritivo.

### 6.3 `slot_type` no BankrollGuardian

O parametro `slot_type` (`can_open_new_slot(symbol, slot_type)`) influencia:
- `BLITZ_30M`/`BLITZ` contam como **TRENDING** (slot pool de 40)
- `DECOR_HUNTER` tem contagem separada (max 2 simultaneos)
- `DECOR SHADOW`/`RANGING` usam pool LATERAL (20 slots)
- Slot types validos: `SNIPER`, `SWING`, `TREND`, `SCALP`, `SURF`, `BLITZ_30M`, `BLITZ`, `MOONBAG`, `PAPER_GHOST`

---

## 7. Filtros de Risco

### 7.1 ExecutionCapacityGate

- Valida book L2 antes de ordem
- Mede spread, profundidade, fill ratio, slippage
- Slippage > 20bps => reduz tamanho ou ordem Limit Post-Only
- PAPER: book falha = aviso; REAL: book falha = bloqueio

### 7.2 Cost Gate

- Custo projetado (taker + 24h funding) > 15% do lucro projetado => abortado

### 7.3 Panic Filter de Correlacao

- BTC > 2% em 1H + correlacao > 0.8 => entradas bloqueadas

### 7.4 Quartermaster

| Wick | Classificacao | Leverage | Margem |
|------|--------------|----------|--------|
| < 0.45 | SMOOTH | 50x | 1.0x |
| 0.45-0.70 | JUMPY | 20x | 2.5x |
| > 0.70 | EXTREME | 10x | 5.0x |

**Bloqueio**: EXTREME + BTC ADX < 25 => bloqueado (exceto PAPER)

### 7.5 FleetAudit (Saida Emergencial)

- **Early ROI Panic**: -80% em < 300s => saida automatica
- **Saida emergencia**: -90% ROI => fechamento imediato
- **Reconciliacao**: 20s, ghost cleanup

---

## 8. Simetria LONG/SHORT

- LONG: stop sobe conforme alvos sao rompidos
- SHORT: stop desce conforme alvos sao rompidos
- ROI sempre alavancado: preco real do stop depende de entrada, lado e leverage

---

*Fonte: codigo-fonte (`config.py`, `order_projection_service.py`, `captain.py`, `bankroll_guardian.py`, `flash_agent.py`). Nao historico de commits.*
