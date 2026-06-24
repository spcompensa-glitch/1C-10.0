# 1CRYPTEN_SPACE_V4.0 - PROTOCOLO DE STOPS E ALVOS (V111.3)

## Arquitetura Atual: Ordem Unica, Escadinha Continua

O sistema usa o `OrderProjectionService` como fonte oficial de alvos, stops, ROI e linhas do grafico. Nao existe mais promocao de ordem para Moonbag: todos os sinais aprovados viram ordens, e cada ordem continua buscando alvos sucessivos. Quando um alvo e rompido, o `FlashAgent` fixa/promove o stop da propria ordem.

## Filtro de Regime de Mercado (V111.2)

O BankrollGuardian agora bloqueia entradas com base no ADX e direcao do BTC:

| Condicao | Acao |
| :--- | :--- |
| **ADX < 22** (Mercado Morto) | Nenhuma entrada permitida. Volatilidade insuficiente. |
| **ADX 22-25** (Transicao) | Apenas trades a favor da direcao do BTC (LONG se UP, SHORT se DOWN). |
| **ADX ≥ 25** (Tendencia) | Bloqueio absoluto de contra-tendencia. SHORTs bloqueados em bull market. LONGs bloqueados em bear market. |
| **ADX ≥ 30** (Tendencia Forte) | Reforco do bloqueio contra-tendencia com threshold mais alto. |

A direcao do BTC e determinada por confluencia de variacao 15m + 1h:
- Ambas positivas => `UP`
- Ambas negativas => `DOWN`
- Divergencia => `LATERAL` (não bloqueia, pois não há direcao clara)

O `OracleAgent` agora e a SSOT desse contexto macro: recebe `btc_adx`, `btc_variation_1h` e `btc_variation_15m` do fluxo OKX, deriva `regime` na grade `22/25/30` e persiste o snapshot validado para recovery via LKG.

Para recalibrar essa grade com estudo historico do BTC na OKX, use `backend/scratch/study_oracle_btc_regime.py`.

## Stop Inicial Inteligente

Na abertura, o stop inicial nao e mais fixo em -50% ou -100% ROI. O `BankrollManager` calcula um plano de stop inicial:

- LONG: stop abaixo da invalidacao tecnica do setup, como fundo, sweep, suporte ou zona rompida.
- SHORT: stop acima da invalidacao tecnica do setup, como topo, sweep, resistencia ou zona rompida.
- Se o sinal trouxer `adaptive_sl`, `sl_price`, `stop_loss`, `invalidation_price` ou campos estruturais equivalentes, essa informacao tem prioridade.
- Se nao houver stop estrutural, o fallback usa ATR/range/volatilidade recente.
- Se o stop estrutural explicito ficar longe demais para o regime, a entrada e bloqueada em vez de aceitar risco fixo gigante.
- O stop inicial em tendencia e maior que em lateral para acomodar oscilacoes naturais de alta volatilidade.

### Teto de Stop Inicial (V111.2) — Atualizado V112.11

Para proteger banca pequena, o ROI do stop inicial **nunca ultrapassa 40%** (`MAX_INITIAL_STOP_ROI`) em tendencia,
ou 30% em lateral.
- Se ATR/estrutura indicar stop com risco > 40% ROI, o stop e reposicionado para o teto.
- Block de entrada (approved=False) ainda pode ocorrer se o stop estrutural ficar alem de `max_risk_pct * 1.35`.
- Logs `[STOP-CAP]` registram quando o cap e aplicado.

## Escadinha em Lateral

Mercado lateral protege cedo porque falso rompimento e comum.

| Alvo rompido (ROI) | Stop fixado (ROI) | Status |
| ---: | ---: | --- |
| 30% | 5% | `SL_0` |
| 50% | 25% | `RISCO_ZERO` |
| 70% | 50% | `RISCO_ZERO` |
| 100% | 80% | `PROFIT_LOCK` |
| 150% | 110% | `PROFIT_LOCK` |
| 200% | 150% | `TRAIL_LOCK` |
| 300% | 220% | `TRAIL_LOCK` |

## Escadinha em Tendencia (V112.11)

Mercado em tendencia usa degraus progressivos para proteger lucro sem fechar prematuramente.
A escadinha agora e unificada entre sandbox e execucao real.

### Nova Escada Progressiva

| Alvo rompido (ROI) | Stop fixado (ROI) | Nome do Degrau | Status |
| ---: | ---: | --- | --- |
| 10% | 0% | `BREAKEVEN` | `RISCO_ZERO` |
| 30% | 15% | `LUCRO_INICIAL` | `RISCO_ZERO` |
| 45% | 30% | `LUCRO_MEDIO` | `RISCO_ZERO` |
| 80% | 50% | `LUCRO_GARANTIDO_80` | `RISCO_ZERO` |
| 100% | 75% | `LUCRO_GARANTIDO` | `RISCO_ZERO` |
| 130% | 110% | `SUCESSO_TOTAL` | `PROFIT_LOCK` |
| 150% | 110% | `ALVO_150` | `PROFIT_LOCK` |
| 200% | 150% | `WAVE` | `TRAIL_LOCK` |
| 300% | 220% | `ROCKET` | `TRAIL_LOCK` |
| 400% | 280% | `STAR` | `TRAIL_LOCK` |

**Mudancas principais (vs V112.10):**
- MICRO_LOCK (20%->5%) removido — travava lucro cedo demais (0.4% de preco)
- PROFIT_BRIDGE (65%->40%) removido — fechava trades lucrativos prematuramente
- BREAKEVEN (10%->0%) adicionado — protecao basica de capital
- LUCRO_INICIAL (30%->15%) adicionado — primeiro lucro real com respiro
- LUCRO_MEDIO (45%->30%) adicionado — degrau intermediario para preencher gap
- Stop inicial em tendencia aumentado de -25% para -40% ROI (mais respiro para oscilacoes)

## Continuidade Pos-APEX

A partir de 1200% ROI, o sistema continua criando niveis `ULTRA_*` a cada 200% ROI. O stop fica 200% ROI atras do alvo rompido: `ULTRA_1400 -> stop +1200%`, `ULTRA_1600 -> stop +1400%`, e assim por diante.

## Simetria LONG/SHORT

- LONG: o stop sobe conforme os alvos sao rompidos.
- SHORT: o stop desce conforme os alvos sao rompidos.
- O ROI e sempre alavancado: o preco real do stop depende de entrada, lado e leverage.
