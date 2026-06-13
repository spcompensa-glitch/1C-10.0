# 1CRYPTEN_SPACE_V4.0 - PROTOCOLO DE SOBERANIA (V110.668)

## 🎯 Arquitetura da Escadinha (Trailing Stop Progressivo)

O sistema opera sob o conceito de **Single Source of Truth (SSOT)** centralizado no `ProtocolRegistry`.

### 1. Gatilhos de ROI e Proteção
| Fase | Gatilho (ROI %) | Proteção SL (ROI %) | Status UI |
| :--- | :--- | :--- | :--- |
| **T1: Risk-Zero** | 80% | 15% | `RISK_ZERO` |
| **T2: Emancipação** | 150% | 110% | `EMANCIPATED` |

### 2. Simetria Operacional (Long vs Short)
O sistema é 100% simétrico.
- **LONG (Buy)**: O Stop Loss é movido para **CIMA** conforme o preço sobe.
- **SHORT (Sell)**: O Stop Loss é movido para **BAIXO** conforme o preço desce.
- **ROI**: Calculado de forma absoluta. `+150%` em Short significa que o preço caiu o suficiente para atingir o alvo alavancado.

### 3. Performance de Monitoramento
- **Frequência**: O loop de monitoramento (`SlotOperatorAgent`) roda a cada **0.2 segundos**.
- **Garantia**: Alta reatividade para capturar "pavilhões" (wicks) rápidos e disparar a emancipação.

### 4. Protocolo de Reset Nuclear
Para limpar o sistema e iniciar um novo ciclo de testes:
```powershell
python 1CRYPTEN_SPACE_V4.0/backend/nuclear_reset.py
```
*Ação: Cancela ordens, limpa slots, reseta banca para $100 e apaga histórico.*

### 5. All-SWING Transition (V34.0+)
Todas as operações ativas do "Heavy Weights" agora entram com a estratégia **SWING**.
Isso elimina o modelo Scalp focado em ruído, com os seguintes benefícios:
- **Espaço para Respirar (Volatility Cap):** As ordens ganham uma proteção SL técnica e mais longa (1.5% a 3.5%, até 5% no *Big Swing*), absorvendo volatilidades bruscas de agulhadas normais.
- **Micro-Macro Targets:** A extração não é miúda; as posições visam os topos/fundos locais estruturais, focando no ROI de `150% a 470%` dependendo da alavancagem.
- **Escadinha Progressiva:** Uma vez no lucro (Risk-Zero / Profit-Lock), as ordens agem como um trailing seguro para capturar o movimento limpo até o fim da assimetria do mercado.

### 6. Atualizações de Interface (V110.708+)
- **Mobile Mode:** Remoção do Radar de Inteligência para focar exclusivamente na "Wealth Edition" e tabela de custódia na visualização para smartphones.
- **Desktop Mode:** Modificação do *Raciocínio IA*, que agora opera oculto e comprimido na tela das posições ativas, sendo visualizado via um botão ("toggle expand").

---
**Status: ESTÁVEL | Versão: V110.708**
