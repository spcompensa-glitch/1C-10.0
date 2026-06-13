# 1CRYPTEN_SPACE_V4.0 - PROTOCOLO DE SOBERANIA (V110.960)

## 🎯 Arquitetura da Escadinha (Trailing Stop Progressivo)

O sistema opera sob o conceito de **Single Source of Truth (SSOT)** centralizado no `OrderProjectionService` com a nova arquitetura de Escadinha Unificada (sem a promoção física para moonbags).

### 1. Gatilhos de ROI e Proteção (Escadinha Integrada)
| Fase / Nível | Gatilho (ROI %) | Proteção SL (ROI %) | Status UI |
| :--- | :--- | :--- | :--- |
| **T1: Risk-Zero** | 50% | 15% | `RISK_ZERO` |
| **T2: Lucro Garantido** | 100% | 50% | `RISK_ZERO` |
| **T3: Sucesso Total** | 130% | 110% | `PROFIT_LOCK` |
| **T4: Alvo Emancipada** | 150% | 110% | `PROFIT_LOCK` |
| **T5: Wave** | 200% | 150% | `MOONBAG_TRAIL` |
| **T6: Rocket** | 300% | 220% | `MOONBAG_TRAIL` |
| **T7: Star** | 400% | 280% | `MOONBAG_TRAIL` |
| *Níveis adicionais* | Até 1200% ROI (Apex) | Trailing progressivo | `MOONBAG_TRAIL` |

### 2. Simetria Operacional (Long vs Short)
O sistema é 100% simétrico.
- **LONG (Buy)**: O Stop Loss é movido para **CIMA** conforme o preço sobe.
- **SHORT (Sell)**: O Stop Loss é movido para **BAIXO** conforme o preço desce.
- **ROI**: Calculado de forma absoluta. `+150%` em Short significa que o preço caiu o suficiente para atingir o alvo alavancado.

### 3. Performance de Monitoramento
- **Frequência**: O loop de monitoramento (`SlotOperatorAgent` e `FlashAgent`) roda a cada **0.2 a 1.0 segundos**.
- **Garantia**: Alta reatividade para capturar pavios rápidos e disparar o trailing stop protetivo direto nos slots.

### 4. Protocolo de Reset Nuclear
Para limpar o sistema e iniciar um novo ciclo de testes:
```powershell
python backend/scratch/reset_nuclear_v172.py
```
*Ação: Cancela ordens, limpa slots, reseta banca para $100 e apaga histórico.*

### 5. Consenso Híbrido Estratégico (V110.960+)
Todas as operações ativas entram por estratégias consensuais operando em 30M na matriz de 20 pares:
- **DVAP (Reversão Principal)**: Setup de divergência IFR 30M e volume clímax com gatilho CHoCH. Exige alinhamento com SMA de 2H.
- **MOLA (Breakout de Volatilidade)**: Setup de squeeze de volatilidade Bollinger. Exige estritamente ADX >= 25 do ativo para evitar rompimentos falsos.
- **ABCD & 1-2-3 (Seguidores de Tendência)**: Padrões harmônicos e pivôs clássicos. Exigem alinhamento estrito com a tendência da SMA de 2H.
- **Confluência de Médias (SMA 2H)**: Apenas Long se a tendência 2H for de alta (`BULLISH_ARMED`), e apenas Short se a tendência 2H for de baixa (`BEARISH_ARMED`).
- **Sizing Fixo**: $2.00 por ordem em toda a matriz de 20 pares ativos.

### 6. Atualizações de Interface (V110.960+)
- **Remoção de Moonbags**: Ocultação total do Moonbag Vault no modo mobile e desktop.
- **Timeframe 30M Principal**: Os gráficos do cockpit e os gráficos de ordem iniciam com o intervalo de 30 minutos por padrão.
- **Estratégia Dinâmica nos Cards**: O cockpit exibe a estratégia real disparada pelo sinal (DVAP, MOLA, ABCD, 1-2-3, TREND) de forma nativa e dinâmica.

---
**Status: ESTÁVEL | Versão: V110.960**
