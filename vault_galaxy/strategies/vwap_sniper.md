---
type: strategy
name: "VWAP_SNIPER"
tags:
  - strategy
---

# Configurações de Estratégia: VWAP_SNIPER

O robô de Scalping Micro opera sob o arquivo `services/sandbox_scalping_engine.py`. É um processo autônomo paralelo de alta frequência.
    
    - Filtro de Tendência: EMA 200 no gráfico M5.
    - Zona de Gatilho: Preço cruzando a linha do VWAP diário no gráfico M1.
    - Gatilho Técnico: Stochastic RSI em sobrecompra ou sobrevenda.
