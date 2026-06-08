# MASTER_ARCHITECTURE.md — V110.823 "Cockpit Noise Cleanup & 30M TF"
# Fonte da Verdade Arquitetural — Sincronizado com RULES.md

> **⚠️ NOTA DE DEPRECIAÇÃO:** O version log abaixo (entradas V5.x, V110.4xx, V110.5xx, V110.6xx, V110.7xx, V110.8xx) reflete o estado arquitetural **na data de publicação de cada versão**, como snapshot histórico. Para a arquitetura **atual e consolidada (V110.823)**, consulte a seção `## 🏗️ ARQUITETURA DE SISTEMA (V110.823)` no final deste documento. Entradas individuais não devem ser usadas como referência de comportamento vigente — a seção consolidada é a fonte de verdade.

## 🚀 ROADMAP DE VERSÕES & MARCOS TÉCNICOS

*   **V110.823: COCKPIT NOISE CLEANUP & 30M TF [JUN 08]**
    - **Sem badge piscando de tocaia/radar:** o gráfico remove o indicador visual `TOCAIA ATIVA`/`SINAL DO RADAR`; origem do sinal fica no fluxo, não no HUD operacional.
    - **Ícones legados ocultos no gráfico:** fileira `public`/baleia/bolt/MOLA/123/ABCD deixa de aparecer no header do ativo, mantendo o foco no estado do Flash.
    - **Gutter limpo:** labels legados de `T1/T2/T3/T4/T5`, `TARGET`, `SMA 21` e `SMA 100` deixam de aparecer no gutter lateral; linhas podem existir, mas sem poluir texto.
    - **Timeframe 30m exposto:** seletores de timeframe passam a oferecer `30m`, alinhado ao TF principal usado pelo sistema para estratégias BLITZ/abertura de ordens.

*   **V110.822: FLASH-FIRST COCKPIT LANGUAGE [JUN 08]**
    - **Flash como protagonista visual:** textos operacionais do gráfico e HUD passam a priorizar `FLASH MONITORANDO`, `FLASH STOP`, `FLASH RISCO ZERO`, `FLASH LUCRO TRAVADO` e `FLASH EMANCIPANDO`.
    - **Menos mitologia interna na UI:** `Tocaia` e `Ceifeiro` continuam existindo no backend/fluxo, mas deixam de ser protagonistas na tela operacional; o foco visível vira estado do stop, próximo alvo e risco vivo.
    - **Gráfico mais limpo:** linhas antigas/rompidas continuam desenhadas, porém só `FLASH STOP` ativo e próximo degrau exibem label no eixo/gutter, reduzindo a concatenação visual.
    - **Painel renomeado:** `Target Visualization / Multi-Grid Matrix Controller` vira `Flash Map / Stops, alvos e risco vivo`; `System Engine` vira `Flash Engine`.
    - **Moonbag focada no Flash:** hover de moonbag troca `Ceifeiro: Surf Eterno` por comunicação operacional `FLASH EM CONTROLE`, alinhada com stops contínuos pós-1200%.

*   **V110.821: INFINITE MOONBAG TRAIL [JUN 08]**
    - **Moonbag sem teto em 1200%:** `OrderProjectionService` remove o limite lógico `MAX_TARGET`; 1200% vira `APEX` e a projeção continua com níveis `ULTRA_1600`, `ULTRA_2000`, `ULTRA_2400` etc.
    - **Stops mais próximos no pós-1200:** níveis `ULTRA_*` usam stop 250% ROI abaixo do alvo rompido, evitando devolver uma pernada extrema quando o preço reverte.
    - **Gap fechado antes de 1200:** escada oficial ganha `CHOKE_PREP 750% -> stop 600%`, `CHOKE 800% -> stop 650%` e `HYPER 1000% -> stop 800%`, além de `APEX 1200% -> stop 1000%`.
    - **Próximo alvo oficial:** a projeção passa a expor `next_level` com preço do stop e preço do alvo, permitindo que slots e moonbags mostrem a continuidade correta.
    - **Gráfico alvo + stop:** `cockpit.html` desenha linhas discretas de alvo rompido/futuro (`target_price`) e stop correspondente (`price`), destacando apenas o stop ativo do Flash.
    - **Regressão OPN:** teste cobre moonbag SHORT em ~784% ROI com stop ativo `CHOKE_PREP 600%`, próximo `CHOKE 800%` e continuação após 1200% com `ULTRA_1600/2000`.

*   **V110.820: GUARDIAN RADAR SCORE GATE [JUN 08]**
    - **Score correto no Guardião:** `BankrollGuardian.authorize_new_trade()` passa a usar `signal.score`/`score_radar` como métrica principal do score mínimo da banca, mantendo `unified_confidence` como telemetria auxiliar.
    - **Correção do bloqueio de oportunidades 99:** sinais com Radar Score 99 deixam de ser bloqueados por `unified_confidence` abaixo de 80 durante `ACUMULACAO_PROTEGIDA`.
    - **Auditoria no Capitão:** `CaptainAgent` preserva `score`, `radar_score` e `unified_confidence` na decisão do Guardião para explicar cada liberação/bloqueio.
    - **Teste de regressão:** `tests/test_bankroll_guardian.py` cobre o caso real `score=99` e `unified_confidence=59.7`.

*   **V110.819: FLASH PROFIT STOP CONFIRMATION [JUN 08]**
    - **Stop de lucro com confirmação REST:** quando o preço conservador do WebSocket/cache não acusa violação, o Flash confirma o stop com preço REST fresco da OKX antes de manter a ordem aberta.
    - **Fechamento síncrono de lucro:** `FLASH_PROFIT_SL` passa a aguardar `_close_position()`, reduzindo a chance de slot continuar aberto após stop de lucro já tocado.
    - **Teste do caso ZEC:** `tests/test_flash_stop_invariants.py` cobre LONG com `current_stop` acima da entrada e preço atual abaixo do stop, garantindo fechamento por Flash.

*   **V110.818: FLASH PEAK LOCK & FULL SLOTS [JUN 07]**
    - **Flash com memória de pico:** slots passam a usar o maior ROI recente observado (`peakROI`) para decidir escadinha/emancipação, usando máxima recente no LONG e mínima recente no SHORT. Se a ordem toca 150% e volta rápido, o Flash ainda aplica a trava correta.
    - **Emancipação sem salto perdido:** projeções de slot com ROI acima de 200% continuam exigindo passagem por `EMANCIPACAO` antes de virar moonbag, evitando pulo direto para fase moonbag sem promoção.
    - **Stop crítico síncrono:** atualização de stop e promoção por Flash deixam de ser fire-and-forget no caminho crítico de slot, reduzindo janela de estado velho.
    - **Guardião com 4 slots em lucro:** em `ACUMULACAO_PROTEGIDA`, o Guardião mantém score mínimo elevado, lucro protegido e suspensões, mas libera 4/4 slots. Redução de slots fica reservada para `CAUTELOSO`, `DEFESA` e `PRESERVACAO_TOTAL`.
    - **Testes de regressão ZEC:** `tests/test_flash_stop_invariants.py` cobre pullback após pico de emancipação, e `tests/test_order_projection_service.py` cobre slot acima de 200% ainda exigindo emancipação.

*   **V110.817: FLASH STOP MAP [JUN 07]**
    - **Mapa completo de stops no gráfico:** o Cockpit passa a desenhar todos os `projection.levels` do backend desde a escadinha até a moonbag, sem remover o nível que coincide com o stop atual.
    - **Design discreto e operacional:** níveis futuros usam linhas finas/pontilhadas e baixa opacidade; níveis já conquistados usam linhas finas sólidas; o nível ativo do Flash recebe cor/espessura de destaque.
    - **Labels modernos e curtos:** níveis aparecem como `BE`, `PB`, `RZ`, `PL`, `EM`, `WAVE`, `RKT`, `STAR`, `CRN`, `SN`, `GOD` e `MAX`, com o ROI do stop. A linha de stop aplicado fica como `STOP ATUAL`.
    - **Sem target legado quando há projeção oficial:** ao existir `projection.levels`, o gráfico remove a linha genérica de `TARGET` e mostra apenas o mapa oficial de stops do backend.

*   **V110.816: FLASH STOP INVARIANTS [JUN 07]**
    - **Invariante única de stop:** `FlashAgent` centraliza a regra de melhoria de stop em `_stop_improves()`, garantindo a mesma direção lógica para LONG e SHORT em slots, emancipação e moonbags.
    - **Teste do caso XPL:** novo `tests/test_flash_stop_invariants.py` cobre a moonbag SHORT com stop persistido pior que o hard-lock. O teste confirma que o Flash usa o stop de `+110%` e fecha quando o preço já violou esse piso.
    - **Garantia de não-regressão:** testes passam a cobrir direção de stop LONG/SHORT, hard-lock mínimo de moonbag e projeção oficial escadinha/emancipação/moonbag.

*   **V110.815: MOONBAG HARD-LOCK GUARD [JUN 07]**
    - **Piso obrigatório de emancipação:** `FlashAgent` passa a impor em toda moonbag um hard-lock mínimo de `+110%` ROI, usando o maior valor entre `flash_last_stop_roi` e `110%`.
    - **Correção de moonbag antiga:** se uma moonbag existente estiver com stop pior que o piso, o Flash corrige o stop; se o preço já violou o hard-lock, sincroniza o stop no paper e fecha a moonbag por SL.
    - **Promoção sem perda de trava:** `database_service.promote_to_moonbag()` aceita `emancipation_stop` e grava a moonbag já com o stop de emancipação, em vez de copiar um stop antigo do slot.
    - **UI protegida contra RTDB antigo:** `useMoonbagsRT` mescla payload RTDB sem `projection` com o último payload REST enriquecido e reduz o polling REST para 15s, evitando `FLASH: MONITORANDO`/`$0.00` quando a API já tem projeção oficial.

*   **V110.814: SLOT CARD TACTICAL LABELS [JUN 07]**
    - **Próximo degrau correto:** cards de slot passam a calcular `Próx` pelo próximo `projection.levels.trigger_roi`, com fallback local apenas se uma ordem legada chegar sem níveis.
    - **Stop alvo sem ambiguidade:** `Stop Alvo` passa a exibir o nome do próximo nível e o stop ROI correspondente, por exemplo `PROFIT_BRIDGE +25%`, em vez de cair em `INICIAL`.
    - **Stop Flash sem ruído:** o aviso de stop sugerido só aparece quando `projection.recommended_stop` melhora o stop atual para o lado da ordem, evitando recomendação antiga/retroativa na UI.

*   **V110.813: COCKPIT EQUITY SSOT FIX [JUN 07]**
    - **Banca verdadeira no topo:** `cockpit.html` passa a usar `guardianReport.equity` como patrimônio líquido quando o relatório do Guardião está disponível.
    - **Moonbag sem inflação de PnL:** cards de Moonbag exibem `projection.pnl_usd` oficial em dólares, evitando transformar ROI alavancado em dólar com fallback de margem incorreto.
    - **PnL aberto backend-first:** soma agregada de slots/moonbags usa `projection.pnl_usd` ou `pnl_usd` antes de qualquer cálculo local emergencial.
    - **Resultado da sessão alinhado:** o número ao lado do patrimônio usa `guardianReport.session_profit`, mantendo a UI sincronizada com o backend.

*   **V110.812: GUARDIÃO COM EQUITY VIVA [JUN 07]**
    - **Equity operacional real:** `BankrollGuardian` deixa de depender apenas de `banca.saldo_total` e passa a calcular a banca viva com `base_balance + PnL realizado + PnL aberto dos slots + PnL aberto das moonbags`.
    - **Proteção de lucro por pico:** o Guardião usa `peak_equity` para travar lucro acumulado. Acima de 1x da banca base, entra em `ACUMULACAO_PROTEGIDA`, eleva score mínimo e reduz novos slots liberados.
    - **Auditoria transparente:** `/api/bankroll/guardian-report` passa a expor `stored_equity`, `calculated_equity`, `realized_pnl`, `open_slots_pnl`, `open_moonbags_pnl` e `protected_floor`.
    - **Alinhamento com o Cockpit:** a inteligência da banca passa a enxergar o mesmo lucro vivo mostrado na UI, incluindo moonbags em andamento e slots negativos antes do stop.

*   **V110.811: GUARDIÃO DA BANCA NA UI [JUN 07]**
    - **Banca unificada desktop/mobile:** `cockpit.html` passa a consumir `/api/bankroll/guardian-report` via `useBankrollGuardianRT`, com cache local e atualização leve a cada 30s.
    - **Inteligência visível:** os painéis de banca no Desktop e Mobile exibem saúde do Guardião, modo operacional, score mínimo, lucro protegido, devolução permitida e pares suspensos.
    - **Sem duplicar fonte de verdade:** o frontend continua mostrando equity/PnL já calculados na UI, mas a decisão operacional da banca vem do backend pelo `BankrollGuardian`.

*   **V110.810: GUARDIÃO DA BANCA PREVENTIVO [JUN 07]**
    - **Novo agente `BankrollGuardian`:** criado em `backend/services/agents/bankroll_guardian.py` para proteger a saúde da banca antes da abertura de ordens. Ele lê banca, slots, moonbags e histórico para decidir se a banca está em `ACUMULACAO`, `CAUTELOSO`, `DEFESA` ou `PRESERVACAO_TOTAL`.
    - **Gate acima do Capitão:** `CaptainAgent` passa a consultar o Guardião antes de chamar `bankroll_manager.open_position()`. O Guardião pode bloquear nova entrada por drawdown, excesso de slots, score insuficiente para o modo atual ou par suspenso por prejuízo recente.
    - **Memória por par:** o Guardião calcula wins/losses, ROI médio, sequência de perdas e quarentena de símbolos. Pares com fechamento em prejuízo entram em suspensão temporária conforme severidade e recorrência.
    - **Comunicação PT-BR:** nova rota pública `/api/bankroll/guardian-report` retorna `message_ptbr`, score de saúde, modo, lucro protegido, devolução permitida, slots permitidos e pares suspensos.
    - **Facão reclassificado:** o `PortfolioGuardian`/Knife-Drop permanece como ferramenta emergencial de corte; o Guardião da Banca é o cérebro preventivo de acumulação e preservação.

*   **V110.809: SLOT EMANCIPATION TARGET MATH FIX [JUN 07]**
    - **Card com alvo correto de 150% ROI:** `cockpit.html` deixa de usar o preço do nível de projeção como alvo visual de Emancipação quando esse nível representa stop protegido. O card calcula o gatilho visual de 150% diretamente por `entry * (1 + 1.5/leverage)` para LONG e `entry * (1 - 1.5/leverage)` para SHORT.
    - **Confirmação matemática:** auditoria manual nos slots ativos confirmou que o ROI backend e o ROI recalculado com `50x` batem exatamente para LONG/SHORT. Contratos OKX (`tickSize`, `ctVal`, `lotSize`, `minQty`, `maxLeverage`) seguem sendo a fonte de precisão para execução, margem, quantidade e PnL.
    - **Validação:** Babel standalone transformou os 7 scripts `text/babel` do Cockpit sem erro.

*   **V110.808: SLOT CARD FLASH TELEMETRY CLEANUP [JUN 07]**
    - **Card operacional e sem duplicidade:** removida a pilha de ícones legados (`public`, baleia, `bolt`, `info`) dos slots. O badge tático passa a seguir `projection.active_level` e `projection.flash`, não `status_risco` cru.
    - **Separação de estado:** o card distingue `Stop Atual`, `Stop Alvo`, `Próx` e `Aplicando Stop Flash`, evitando misturar stop já aplicado com stop recomendado pelo Flash.
    - **Leitura do Flash:** slots passam a exibir `Flash`, ROI do stop atual e próximo gatilho da Escadinha/Moonbag com base no payload oficial do backend.

*   **V110.807: FLASH STATE ON SLOT CARDS [JUN 07]**
    - **Telemetria do Flash no Cockpit:** cards de slots ativos passam a renderizar `projection.flash.last_action`, `projection.recommended_stop`, `projection.active_level` e próximo nível da escadinha.
    - **Rótulo de alvo corrigido:** o antigo rótulo genérico `Target` vira `Emancipação 150%`, deixando claro que o slot ainda está na primeira jornada antes de virar Moonbag.
    - **Backend como SSOT:** o frontend permanece render-only para estado operacional; cálculos locais são limitados a formatação visual e fallback seguro.

*   **V110.806: CAPTAIN RUNTIME RESET & ANTI-CONCENTRATION PAPER FIX [JUN 07]**
    - **Diagnóstico Railway:** Logs mostraram que o Capitão não estava parado; ele processava sinais, mas `LINKUSDT` foi bloqueado por `ANTI-CONCENTRATION` após reset porque `daily_symbol_trades` ficava na RAM.
    - **Reset Nuclear Completo:** `/api/system/nuclear-reset` e o reset do Admin passam a limpar `captain_agent.active_tocaias`, `processing_lock`, `cooldown_registry`, `daily_symbol_trades`, `slot_vacancy_tracker`, `bankroll_manager.pending_slots` e `recent_openings`.
    - **PAPER Anti-Concentration Fix:** a trava de 3 trades/dia agora reconhece corretamente `OKX_EXECUTION_MODE == "PAPER"` em vez de depender da flag inexistente `PAPER_MODE`.
    - **Diagnóstico Runtime:** nova rota protegida `/api/system/captain-runtime` expõe contadores de tocaias, locks, cooldowns, histórico diário, posições paper e modo de execução.
    - **OKX Leverage Info:** `OKXRest.get_leverage_info()` foi adicionado para remover warnings de contrato e manter fallback explícito de `50x`.
    - **Validação:** `compileall` passou em Capitão, rotas system/admin, OKX REST e SignalGenerator; `tests/test_order_projection_service.py` passou com 3/3 testes.

*   **V110.805: RADAR CONTRACT INTELLIGENCE & CAPTAIN CONTRACT GATE [JUN 07]**
    - **Contrato OKX no Radar:** `_sync_radar_rtdb()` passa a enriquecer sinais ativos com `contract_info` quando o payload ainda não traz metadados de instrumento: `ctVal`, `lotSize/qtyStep`, `minQty`, `tickSize`, `maxLeverage`, preço de referência, margem mínima e impacto por contrato.
    - **Relatório do Sinal com Matemática do Preço:** `TriumphModal.js` exibe o bloco `Contrato OKX & Matemática do Preço`, mostrando como o par converte variação real de preço em ROI alavancado e qual precisão o Flash/Capitão terão para stops e alvos.
    - **Captain Contract Gate:** `CaptainAgent` avalia a qualidade do contrato antes do quality gate final, penalizando ou bloqueando sinais cujo contrato seja ruim para banca pequena, `50x`, tick size ou margem mínima. O resultado volta no `fleet_intel.contract_quality`.
    - **Fonte Única do Fluxo:** o mesmo metadado de contrato passa a acompanhar `Radar → Capitão → Flash`, evitando decisões sem contexto de preço real do par.
    - **Validação:** `compileall` passou em `captain.py` e `signal_generator.py`; validação frontend confirmou chaves balanceadas, com alerta heurístico legado do script.

*   **V110.804: CAPTAIN QUALITY GATE & COCKPIT STOP-LINE STABILITY [JUN 07]**
    - **Capitão com leitura real de slots:** `CaptainAgent` deixa de consultar o método inexistente `get_user_slots()` e passa a usar `database_service.get_active_slots()`, contando como ocupado somente slot com `symbol`, `entry_price` e `qty` válidos.
    - **Sem bypass artificial no PAPER:** o modo simulado não força mais `approved=True` nem infla a confiança para 88%. Sinais bloqueados pelo Fleet/quality gate permanecem bloqueados também em PAPER, preservando qualidade antes de ocupar slots.
    - **Quality Gate mais seletivo:** threshold operacional do Capitão sobe para 45% com dois ou mais slots livres e 50% quando a ocupação aumenta, reduzindo entradas medianas vindas do Radar.
    - **Slots vazios fiéis na UI:** `cockpit.html` deixa de marcar slots vazios como `BLITZ 30M` por ID fixo; cards sem ordem exibem `SLOT N` e o contador mostra a ocupação real (`N/4 ACTIVE`).
    - **Linhas de stop estáveis no gráfico:** o Cockpit passa a assinar a combinação de símbolo, entrada, stop, alvo, lado e `projection.levels` antes de recriar price lines, evitando que atualizações de candles/pulso apaguem e redesenhem os stops continuamente.
    - **Validação:** `compileall` passou em `captain.py`, `trading.py` e `order_projection_service.py`; `tests/test_order_projection_service.py` passou com 3/3 testes.

*   **V110.803: BACKEND SSOT DE STOPS, PROJEÇÃO DE ORDEM & FLASH PRINCIPAL [JUN 06]**
    - **Order Projection Service:** Criação de `backend/services/order_projection_service.py` como fonte única de verdade para ROI, preço de stop, fases da ordem, linhas de gráfico, `tickSize`, `qtyStep`, `ctVal`, margem e PnL estimado.
    - **Fluxo Único da Ordem:** A ordem passa por `SLOT → ESCADINHA → EMANCIPAÇÃO → MOONBAG → CEIFEIRO` sem perder identidade (`genesis_id`, `order_id`, `leverage`, `entry_margin`, `slot_type` e metadados de contrato).
    - **Flash como Autoridade Operacional:** `FlashAgent` passa a consumir a projeção oficial e vira o principal escritor de progressão de stops e emancipação. `SlotOperatorAgent` permanece como observador/failsafe, sem recalcular escadinha própria.
    - **Moonbag Enriquecida:** A tabela `moonbags` passa a preservar `leverage`, `entry_margin`, `initial_stop`, `target_price`, `genesis_id`, `slot_type`, estratégia, `contract_meta`, `flash_last_action` e `flash_last_stop_roi`.
    - **Frontend Render-Only:** `cockpit.html` passa a renderizar `projection.levels` vindos do backend no gráfico e no gutter, deixando os cálculos locais como fallback temporário. A ação do Flash também é exibida nos cards de Moonbag.
    - **Rotas Oficiais:** `/api/slots` e `/api/moonbags` expõem a projeção backend-first, incluindo `phase`, `active_level`, `recommended_stop`, `levels`, `contract` e `flash`.
    - **Validação:** Adicionado `tests/test_order_projection_service.py` cobrindo LONG, SHORT, tick size, emancipação em 150% e fase Moonbag.

*   **V110.802: CORREÇÃO DE ERROS CRÍTICOS DE CÁLCULO & OTIMIZAÇÃO DE SLOTS [JUN 05]**
    - **Correção da Fórmula de ROI**: Remoção do fator `* 100` extra na função `_calc_roi` do FlashAgent que estava causando perdas extremas (ex: -181% em vez de -1.81%). A fórmula correta agora é `price_diff * leverage` sem multiplicação por 100.
    - **Correção da Fórmula de Stop Loss**: Simplificação do cálculo de stop loss para `stop_roi / 100` sem distorção de leverage, garantindo fechamentos precisos e evitando erros de precificação.
    - **Otimização do Capitão**: Implementação de threshold dinâmico de confiança (35% quando slots vazios ≥ 2, 40% normal) para melhor preenchimento de slots e redução de ordens bloqueadas desnecessariamente.
    - **Correção UI de Moonbags**: Atualização do display de "ETERNAL SURF" para "MOONBAG ACTIVE", eliminando confusão entre expectativa visual e comportamento real do sistema.

*   **V110.801: CORREÇÃO DE CRITICAL STOP LOSS & FILTRO DE CONTRATENDÊNCIA [JUN 04]**
    - **Persistência de Sentinel no SQLite/Postgres**: Adicionada a coluna `sentinel_first_hit_at` nas tabelas `slots` e `moonbags` para garantir que o respiro diplomático não resulte em loops infinitos sob fallback de banco de dados local.
    - **Filtro de Contratendência Universal**: Ativado o filtro de contratendência no modo `PAPER` e endurecidas as travas gerais, bloqueando 100% de trades contra a tendência se a variação de 15m do BTC for >= 0.5%, com bypass restrito a scores de elite >= 98.

*   **V110.800: PARIDADE DE PORTFÓLIO EM SIMULAÇÃO & OVERRIDE DE BANCA [JUN 04]**
    - **Paridade do Portfolio Guardian no modo PAPER**: Ajustada a lógica de monitoramento de risco e encerramento de posições pelo Facão para refletir a simulação (PAPER) de forma robusta e persistir os resultados no banco local.
    - **Override de Banca Simulada em $20.00**: Garantido que o override do arquivo `.env` para `OKX_SIMULATED_BALANCE` force a banca base a respeitar este limite nas leituras e atualizações do banco local SQLite e RTDB.
    - **Migração SQLite Auto-Healing**: Adicionada compatibilidade na migração auto-healing do `database_service.py` para injetar o suporte a `configured_balance` de forma transparente também em ambiente SQLite local.

*   **V110.705: CALIBRAÇÃO DE MARGEM PARA BANCA PEQUENA & CONTRATENDÊNCIA ADAPTATIVA [JUN 03]**
    - **Margem Mínima para Bancas Pequenas**: Garantia de margem de no mínimo $3.00 USD por slot quando a banca estiver abaixo de $50.00 USD (em vez de usar 10% rígido que resultaria em valores nulos de contratos na OKX).
    - **Flexibilização de Contratendência**: Sinais qualificados em altcoins descorrelacionadas (`is_decorrelated`) ou com Score de Elite (>= 95) agora têm bypass ativo para operar em contratendência, mesmo em momentos de queda violenta do BTC (variação de 15m >= 0.8%).

*   **V110.704: LOCAL SERVER STABILITY, M-ADX, CAPITAL PRESERVATION & MOONBAG SYNC [JUN 03]**
    - **Sincronização de Moonbags no Postgres & UI**: Correção do fluxo de atualização e remoção de Moonbags. Quando o Firebase está inativo, as alterações e encerramentos de Moonbags agora refletem corretamente no PostgreSQL (através de `update_moonbag` e `remove_moonbag` em `database_service.py`).
    - **Transmissão WebSocket de Moonbags**: Implementado broadcast em tempo real da tabela `moonbags` a cada 5 segundos no loop principal do backend para manter a UI em sincronia imediata.
    - **Correção de Cache no Frontend**: Corrigido o hook `useMoonbagsRT` e a escuta WebSocket no `cockpit.html` para aceitar os eventos em tempo real e atualizar incondicionalmente pelo REST fallback, eliminando cards de Moonbags travados com PnL antigo ou exibidos incorretamente ("fantasmas").
    - **M-ADX Wilder Smoothing Fix**: Aumento do limite de klines requisitadas da OKX de 30 para `144` no cálculo do ADX do BTC, permitindo que a suavização de Wilder se estabilize e eliminando o travamento do indicador em 10.1.
    - **Modo de Preservação de Capital**: Bloqueio preventivo de todas as estratégias de tendência/rompimento (como BLITZ) quando o M-ADX do BTC estiver abaixo de `22.0` (Mercado Morto), liberando passe livre exclusivamente para sinais de reversão estrutural da estratégia **DVAP**.
    - **Postgres Schema Auto-Healing**: Adicionadas colunas necessárias como `vision_url` e tratamentos no `database_service.py` e `okx_rest.py` para auto-migração de bancos legados e fallback offline robusto.
    - **Prevenção de Duplicidades em Moonbags**: Implementação de UUIDs determinísticos baseados em `{symbol}_{opened_at}` no método de emancipação para evitar clones no banco de dados.
    - **Service Worker Asset Alignment**: Purga de dependências ausentes na pasta local `/vendor/` da lista de cache em `sw.js` para sanar erros de instalação.
    - **Self-Healing URL Router**: Implementação de roteamento automático de subpastas do Observatório e redirecionamento de assets relativos erráticos de volta para a raiz `/vendor/` e `/manifest.json`.
    - **Ascending OKX Klines & SMA100 Padding**: Ordenação correta das velas e técnica de padding simulado de 200+ candles para permitir o cálculo e renderização da linha amarela da SMA 100.
    - **Consenso Agressivo 60% & DVAP Mock Triggers**: Redução do threshold de entrada do Capitão local de 70% para 60% e mapeamento de `dvap_history` e `dvap_data` com marcas douradas e canais estruturais ativos.
    - **SPOT Tickers optimization**: Leitura centralizada de preços de todas as 42 moedas da OKX in lote em um único request REST para evitar limites de taxa de chamadas.

*   **V110.701: CEIFEIRO 1200% & ESCADINHA EXPANDIDA (PROFIT-LOCK) [MAY 31]**
    - **Escadinha Profit-Lock Expandida até 1200% ROI**: Expansão completa dos níveis de trailing stop do Ceifeiro (HarvesterAgent) para cobrir todo o espectro de 150% até 1200% ROI, espelhando fielmente os níveis do Ceifeiro nos cards da UI.
    - **Badges Dinâmicos do Ceifeiro**: Restauração do clique de foco no gráfico + badges visuais indicando o nível atual do Ceifeiro em cada card de Moonbag.
    - **Trajetória de Slots Unificada**: A rota visual dos slots agora reflete os alvos do Ceifeiro até 1200% ROI, preservando o preço de entrada original.
    - **Ceifeiro 1200% Test Suite**: Dois testes de validação completos (`test_ceifeiro.py`, `test_jornada_completa.py`) com **0 falhas**:
      - **test_ceifeiro.py**: Valida todos os níveis de trailing stop (WAVE, ROCKET, STAR, CROWN, SUPERNOVA, GOD_MODE, CHOKE_HOLD) + colheitas parciais (PRIMEIRA_COLHEITA 65%, GOLDEN_COLHEITA 85%, Safety Net 80%, Parabolic Climax 90%).
      - **test_jornada_completa.py**: Valida a jornada completa do slot (STOP INICIAL → Break-Even → Profit Bridge → Risk Zero → Profit Lock → EMANCIPAÇÃO) até moonbag (WAVE → ROCKET → STAR → CROWN → SUPERNOVA → GOD_MODE → CHOKE_HOLD → APEX 1200%).

*   **V110.700: MOONBAG UI REFINEMENT & CLIQUE DE FOCO [MAY 31]**
    - **Clique de Foco no Gráfico**: Restauração do comportamento de clique nos cards de Moonbag para focar o ativo no gráfico principal.
    - **Badges Dinâmicos do Ceifeiro**: Indicadores visuais em tempo real nos cards da Vault mostrando o nível atual do Ceifeiro (WAVE, ROCKET, STAR, CROWN, etc.).
    - **Layout Card Fix**: Correção de vazamento de layout no `MoonbagVaultItem` mudando para `flex-col` e arrumando campos Stop/Target zerados.

*   **V110.180: POSTGRES TYPE CONCILIATION & AUDIT RESILIENCE [MAY 31]**
    - **Postgres Datatype Mismatch Resolution**: Correção na tabela `slots` para alinhar o campo `opened_at` mapeado no SQLAlchemy como `Column(Float)` ao invés de `Column(DateTime)`, conciliando-o com o tipo `DOUBLE PRECISION` da coluna física no PostgreSQL do Railway. Isso eliminou o erro fatal `DatatypeMismatchError` que travava silenciosamente a persistência de novos slots.
    - **FleetAudit DateTime Fallback**: Correção do crash no motor de auditoria contínua (`FleetAudit`) em modo PAPER, tratando de forma segura o campo `promoted_at` das moonbags (que variava entre `datetime`, `float` ou `None`) para evitar exceções do tipo `TypeError` na comparação de tempo.
    - **Paper Slot Verification**: Teste cirúrgico ponta a ponta com a abertura bem-sucedida de ordens locais no Postgres compartilhado de produção no Railway (**ENAUSDT.P** no Slot 1 e **SOLUSDT** no Slot 2 com status **ATIVO**).

*   **V110.999: RADAR PERSISTENCE & DESKTOP VAULT SYNC [MAY 28]**
    - **Radar Pulse PostgreSQL Persistence**: Os sinais e decisões do Radar Pulse agora são salvos de forma robusta e transparente na tabela `radar_pulse` do banco de dados Postgres de produção para sobreviver a resets de RAM do contêiner Railway.
    - **Firebase Failover & Fallbacks**: Em caso de inatividade ou queda do SDK do Firebase, o backend redireciona a leitura de pulso de radar, banca e histórico (`trade_history`) diretamente para o Postgres in-real-time, eliminando o eterno "Scanning Slot..." na UI.
    - **Unified Desktop/Mobile Vault UI**: Alinhamento visual do histórico da Vault no cockpit Desktop com o layout Mobile (cards ricos com badges, selo de prova do Agente Visão, genesys ID e TriumphModal de briefing de triunfo por clique).
    - **SignalGenerator Scope Fix**: Correção de escopo de variável local de `okx_ws_public_service` que causava eterno status "Scanning Slot" em produção.
    - **Telegram /banca Command & Guardian Soul Shield**: Comando `/banca` no bot de Telegram integrado com leitura em tempo real e blindagem de persona com o `GUARDIAN_PROMPT.md` ativado sob a flag `HERMES_GUARDIAN=1` no Railway, junto com permissões corretas do Dockerfile.

*   **V110.800: N8N HYBRID MACRO-ORCHESTRATOR & NATIVE TELEGRAM [MAY 26]**
    - **N8N DAG Orchestration**: Desacoplamento do motor de loop infinito centralizado (main.py) em prol de uma orquestração reativa (DAG) via n8n. O n8n passa a acionar o `SignalGenerator` (Radar), `Captain` e o `ExecutionProtocol` em um ciclo rigoroso de 5 minutos, garantindo total previsibilidade.
    - **4 Independent Slots Flow**: O fluxo do n8n foi redesenhado para ter 4 caminhos paralelos, mapeados fisicamente para as vagas de slot (1, 2, 3 e 4). Cada slot é processado e liberado de forma totalmente paralela e imune a gargalos assíncronos do Python.
    - **HTTP Telegram Push**: Integração de alertas nativos disparados via requisições HTTP REST diretamente do n8n (Node Telegram) para envio de relatórios de orquestração e abertura de ordens, complementando a telemetria do Hermes.
    - **Clean Slate Protocol**: Purga massiva de `.db` legados, logs velhos (40MB+) e scripts `.bat`/`.py` de build local que atulhavam a raiz do projeto, consolidando a infraestrutura 100% cloud.

*   **V110.850: OKX MASTER BYPASS & ANTI-FACÃO (MOONBAG SHIELD) [MAY 25]**
    - **Captain Master Bypass**: O Capitão (Agente de Execução) agora possui um bypass nativo em `_process_single_signal`. Se `OKX_API_KEY_MASTER` estiver no `.env`, o motor descarta a busca vazia do multitenant da Bybit e força a execução cirúrgica global diretamente na conta Master (mock tenant "master").
    - **Guardian Anti-Facão**: O `portfolio_guardian.py` (Knife-Drop) agora faz cross-check em tempo real com os Slots Emancipados (Moonbags) via `firebase_service.get_moonbags()`. Posições marcadas como emancipada são ocultadas do cálculo de ROI unificado e blindadas contra encerramento abrupto, corrigindo o erro de encerramento precoce de ordens bem-sucedidas.

*   **V110.830: INTEGRATION SAAS V5.5.0 & OKX PORTFOLIO GUARDIAN [MAY 22]**
    - **OKX Suite Migration**: Transição completa da conta Master da Bybit para o **OKX (Portfolio Margin Mode)**. Conexão WebSocket privada resiliente em `okx_ws.py` com watchdog de silêncio de 45s e autenticação HMAC-SHA256 robusta no `okx_service.py`.
    - **Portfolio Guardian & Knife-Drop**: Máquina de estados atômica unificada monitorando o ROI consolidado da conta Master. Ativação automática em 70% ROI, acompanhamento de pico e fechamento concorrente em lote ultra-rápido via `/api/v5/trade/batch-orders` (Algoritmo **Knife-Drop** / "O Facão") se houver recuo de 15% a partir do pico, emitindo sinal de pânico global.
    - **Hermes Broker (MQTT/gRPC)**: Servidor gRPC HTTP/2 assíncrono na porta `50051` provendo tenancy em tempo real. Cliente MQTT conectado de forma resiliente ao broker nuvem HiveMQ (`broker.hivemq.com`) para despacho leve de sinais de cohorts com QoS 2.
    - **Anti-Slippage Engine**: Algoritmo *Greedy Snake Sharding* distribuindo dinamicamente as contas dos usuários em 4 Cohorts balanceados e despacho escalonado com Random Jitter de 0 a 350ms para pulverizar as ordens no book da exchange.
    - **Fortress Auth Bypass ('123')**: Payload flexível em `backend/routes/auth.py` suportando requisições JSON e x-www-form-urlencoded. Bypass inteligente seguro: se o Firebase estiver desativado ou local offline e a senha for `"123"`, a autenticação é instantaneamente aprovada com JWT sob o usuário administrador `"Sovereign"`.
    - **Aesthetics Gemini & Auto-CORS**: Consistência estética ultra-premium baseada no Google Gemini (glassmorphism, auras azuis/violetas neon desfocadas, fonte Outfit e tela cheia de fusão neural com partículas Orbi e Grafo D3). Script de auto-resolução de rede em tempo de execução no frontend (eliminando URLs estáticas e curando CORS).

*   **V110.650: DECENTRALIZED SLOT OPERATORS (ACTOR MODEL) [MAY 11]**
    - **Slot Independence**: Migração total da arquitetura monolítica para 4 instâncias independentes de `SlotOperatorAgent`. Cada slot agora gerencia seu próprio ciclo de vida (Gênesis, Escadinha e Arquivamento).
    - **Self-Auditing Native**: Substituição do legado `FlowSentinel` por lógica de auto-auditoria embutida diretamente em cada operador de slot, garantindo integridade descentralizada.
    - **Captain Dispatcher**: Refatoração do `CaptainAgent` para atuar como um despachante de sinais puro, delegando a execução para o primeiro agente de slot disponível via AIOS Kernel.
    - **Atomic Locking**: Implementação de `asyncio.Lock()` no `SovereignService` para garantir atomicidade em atualizações de banca e estado de slots em ambientes altamente concorrentes.
    - **Operational Parity**: Remoção de loops centralizados no backend, reduzindo latência de execução e aumentando a precisão do Trailing Stop (Escadinha).


*   **V110.644: VAULT HISTORY GENESIS EXPOSED [MAY 09]**
    - **Vision Compliance Auto-Open**: O laudo visual do Agente Visão (Compliance Visão) agora é exibido por padrão no modal de "Briefing de Triunfo", sem necessidade de expansão manual, expondo o print e o raciocínio instantaneamente.
    - **Tactical Data Reorganization**: Reestruturação da seção "Fatos da Missão" no histórico da Vault para exibir o DNA Gênese, Lado (LONG/SHORT), e Preço de Entrada logo acima do Preço de Saída, mantendo os dados de execução perfeitamente visíveis.
    - **Operational Cleanup**: Remanejamento do campo "Protocolo" (ex: SNIPER) para a coluna "Operacional", consolidando os dados puramente táticos.

*   **V110.643: PADRONIZAÇÃO BLITZ FACTORY (UI/UX PURITY) [MAY 08]**
    - **UI Terminology Purge**: Removidas todas as referências ao legado "SWING" da interface (Cockpit, Observatório e Radar).
    - **Dynamic Demand Radar**: O cabeçalho do Radar agora reporta dinamicamente a busca por slots BLITZ (ex: "VISÃO BUSCANDO 3 BLITZ"), sincronizado com a disponibilidade real dos 4 slots.
    - **Backend Demand Sync**: Sincronização da lógica de demanda no `SignalGenerator` para focar exclusivamente no preenchimento dos 4 slots sob a doutrina Blitz.
    - **Observatory Renaming**: Rebatismo do "Swing Pulse" para "Macro Pulse" no Observatório, alinhando a análise técnica HTF com a nova nomenclatura.

*   **V110.642: FÁBRICA DE MOONBAGS (100% BLITZ PIPELINE) [MAY 08]**
    - **Architecture Shift**: Abandoned the Hybrid Dual-Swing/Dual-Blitz model. The system now operates 4 simultaneous tactical slots under the `BLITZ_30M` doctrine.
    - **Escadinha de Elite**: The Blitz strategy was unified with the Elite Trailing Ladder. Emancipation is now triggered universally for Blitz slots upon reaching 150% ROI.
    - **Blitz Bypass**: Lateral market constraints (ADX < 20) were removed globally, allowing the Captain to ruthlessly hunt micro-structures in any market regime.

*   **V110.641: DESKTOP CHART FIDELITY FIX [MAY 08]**
    - **Marcador de Direção Corrigido:** O marcador de entrada no gráfico Desktop agora exibe corretamente `arrowUp` para Longs e `arrowDown` para Shorts. Anteriormente estava hardcoded como `arrowUp` para ambas as direções, fazendo ordens Short aparecerem como Long no gráfico.
    - **Escadinha de Stops Aware de Alavancagem:** Os níveis T1–T5 da escadinha agora usam a alavancagem real do slot (`activeSlot.leverage`) para calcular os preços-alvo, substituindo o divisor hardcoded `/5000` por `roi / (leverage * 100)`. Aplicado em `syncGutter()` e `updatePriceLines()`.
    - **Sincronização Reativa do Gutter:** Adicionado `useEffect` dedicado com dependência `[slots, focusedAsset]` para garantir que os badges do gutter lateral sejam recalculados imediatamente quando um slot é aberto ou fechado, sem aguardar a atualização do histórico de velas.

*   **V110.511: VISUAL PARITY & SHORT ESCADINHA FIX [MAY 12]**
    - **Short Deadlock Resolution**: Expansão do suporte no `ExecutionProtocol` para normalizar lados `short` e `sell`, permitindo que o trailing stop (Escadinha) funcione em posições de venda.
    - **Visual Parity (UI/UX)**: Sincronização da detecção de `isLong` e cálculo de `leverage` dinâmica no Observatory e Cockpit. Os alvos agora são desenhados com precisão absoluta para ambas as direções.
    - **Log Normalization**: Unificação de prefixos de alvo nos logs do `SignalGenerator` para evitar confusão de inversão em posições Short.
    - **Master Map v9.0**: Consolidação do diagrama técnico para refletir a purga total do legado "Swing" e foco 100% em 4 slots Blitz.

*   **V110.512: WHALE-TRACKER FIX & AGGRESSIVE CONSENSUS [MAY 08]**
    - **WhaleTracker Resilience:** Correção de falha crítica de indexação (`KeyError: 0`) que impedia a leitura de fluxo institucional.
    - **Agressive Fleet Consensus (60%):** Redução do threshold de aprovação final de 70% para 60% durante regimes `ROARING` ou sinais `Blitz`, acelerando a entrada em setups de alta convicção.
    - **Score Audit Telemetry:** Injeção de logs detalhados (`💎 [SCORE-AUDIT]`) para rastrear a contribuição individual de cada agente no score unificado.

*   **V110.515: ELITE BYPASS & ROARING REGIME ADAPTATION [MAY 08]**
    - **Radar-Throttle Elite Bypass:** Permissão para sinais com Score >= 95 ignorarem a trava de ADX < 20 no `SignalGenerator`. Isso garante que confluências técnicas fortes não sejam desperdiçadas em ativos com baixa volatilidade nominal.
    - **Adaptive Lateral Bypass:** Redução do threshold de bypass de bloqueio lateral do Captain de 95 para 90 quando o regime do BTC for `ROARING` (ADX > 30).
    - **Market Direction Resilience:** Melhora na detecção de oportunidades durante lateralizações de alta força (BTC forte mas estável).

*   **V110.639: DOUBLE-GATE VISION FUNNEL [MAY 07]**
    - **Portão 1 (Elite Radar):** Filtro de entrada no Capitão que só permite o processamento de sinais com Radar Score >= 90.
    - **Portão 2 (Elite Consensus):** Chamada do Agente Visão condicionada a um Unified Score >= 70 (consenso técnico).
    - **Zero Waste:** Eliminação de prints redundantes e economia drástica de cota de IA.

*   **V110.638: VISION QUOTA RESILIENCE [MAY 07]**
    - **Vision Cooldown (5m):** Implementação de resfriamento por ativo após veto visual para evitar spam de prints/IA.
    - **Hybrid Vision Cascade:** Ativação do fallback automático para OpenRouter (Gemini Flash/GPT-4o mini) quando a cota nativa do Google atinge o limite.
    - **Vision Failsafe Bypass:** Permissão de entrada técnica para sinais de extrema confiança (95+) se a IA estiver offline.
    - **Native Backoff Visibility:** Exposição do tempo de cooldown da API nativa para o Dashboard.

*   **V110.521: BACKEND BOOT HOTFIX [MAY 07]**
    - **Syntax Stability:** Correção de erro de indentação no `sovereign_service.py`.

*   **V110.520: VAULT FIDELITY & REGIME STABILITY [MAY 07]**
    - **Vault Intelligence Recovery:** Correção de bug crítico de importação circular no `database_service.py`. Implementação de lógica de "deep recovery" que restaura `fleet_intel`, `vision_url` e relatórios do Oracle diretamente da Gênese se o payload de fechamento estiver incompleto.
    - **Dynamic Regime Shield:** Refatoração da detecção de mercado (ALTA/BAIXA/LATERAL). Thresholds dinâmicos baseados no ADX (>30) reduzem a zona morta de 0.10% para 0.05%, garantindo que tendências fortes sejam rotuladas corretamente.
    - **History Search Engine:** Ativação total de filtros de busca por símbolo, data inicial e data final no backend, permitindo auditoria granular via UI.
    - **UI Label Normalization:** Sincronização de chaves de regime entre Backend (ALTA/BAIXA) e Frontend (UP/DOWN) para eliminar falhas de estilização e exibição.
    - **GSD Diagnostics Protocol:** Criação do `DIAGNOSTICS.md` como ledger técnico de estabilização sistemática.

*   **V110.630: SWING CONFLUENCE IGNITION [MAY 06]**
    - **HTF/LTF Confluence:** Implementação do filtro de autorização de Swing baseado no alinhamento de SMA (8/21) no gráfico de 2H.
    - **ABCD Pattern Optimization:** Redução do `pivot_strength` para 2 e melhoria na busca exaustiva, garantindo que os padrões harmônicos sejam visíveis no gráfico de 30M.
    - **UI Swing Pulse:** Novo card de telemetria e marcadores de "Ignition" no gráfico de 2H para confirmar o alinhamento de tendência.
    - **Lateral Bypass:** Permissão seletiva para ordens de Swing furarem o bloqueio de mercado lateral se houver confluência estrutural no 2H.

*   **V110.621: HEAT ENGINE IGNITION [MAY 06]**
    - **Elite Tier 2 Auto-Promotion:** Força a promoção de todos os ativos da Elite Matrix para o Tier 2 (Tape Reading) no boot. Isso garante que o **Global Heat Index (FLOW)** tenha dados de fluxo instantaneamente.
    - **Velocity averaging fix:** Garantia de que a telemetria de fluxo nunca fique zerada enquanto houver ativos na matriz especialista.

*   **V110.620: UI OPTIMIZATION & FLOW INTELLIGENCE [MAY 06]**
    - **UI Space Mastery:** Redução drástica da régua de preços (160 -> 90) e do gutter de badges (100px -> 80px), eliminando o vácuo lateral e maximizando a área de visualização técnica.
    - **Heat Index Activation:** Implementação do cálculo real de variação de preço no `SieveAgent`. O sistema agora identifica momentum em tempo real para alimentar o índice **FLOW** (Global Heat Index).
    - **V5.8 Observatory Parity:** Sincronização da versão visual e ajustes de layout para suporte a múltiplos decimais em régua estreita.

*   **V110.518: SNIPER SIEVE & HEAT MONITOR v5.5.0 🧬🔥 [MAY 06]**
    - **Sniper Sieve Architecture:** Implementação do funil de inteligência de 3 camadas (**T1 Scanner, T2 Tape Reading, T3 Elite**). O sistema agora monitora 200 pares e promove os melhores para o radar visual.
    - **Market Heat Maps:** Integração de medidores de calor (Velocity/ERSI) na lista lateral do Observatório, permitindo identificar picos de ignição e fluxo de capital instantaneamente.
    - **Global Heat Index:** Nova telemetria macro que calcula a média de volatilidade do ecossistema para identificar regimes de mercado explosivos.
    - **Sovereign UI Synchronization:** Unificação total do protocolo WebSocket. O Observatório agora sincroniza HUD (BTC/Heat) e lista de ativos via `radar_pulse` e `btc_command_center`.
    - **Resilient Boot Protocol:** Blindagem do kernel AIOS contra timeouts de banco de dados (Postgres/Redis), garantindo que a telemetria de mercado nunca seja interrompida por falhas de infraestrutura.

*   **V110.510: SNIPER STABILIZATION & AUDIT SHIELD [MAY 05]**
    - **Centralized Telemetry (Bússola):** Unificação do loop de mercado na `main.py`. O `BybitWS` agora atua estritamente como provedor de dados, eliminando o jitter e oscilações na UI.
    - **Audit Shield (Vault/Visão):** Implementação da persistência obrigatória de `vision_url` e `genesis_id` no histórico do Postgres.
    - **Reaper Metadata Injection:** Injeção automática de provas visuais nos trades encerrados via sincronização (Reaper), garantindo auditoria 100% das ordens.
    - **Harmonized Direction SSOT:** Alinhamento total entre a direção do Bitcoin na Bússola e no Cockpit via `Pulse Shield`.
    - **Regra 14 (Pulse Shield Hysteresis):** Implementação de zona morta e trava de estabilidade (3 ciclos/30s) para cálculo de direção, eliminando definitivamente o "flickering" na UI.

*   **V110.506: SNIPER AGGRESSION BOOST & NUCLEAR RESET [MAY 01]**
    - **Agressividade Sniper (75):** Redução do threshold de entrada de 85 para 75 para capturar momentum em Altcoins durante tendência de alta do BTC.
    - **Nuclear Ghost Reset Protocol:** Estabelecimento do PostgreSQL (Railway) como Fonte Única de Verdade (SSOT). O Firebase/RTDB passa a ser tratado estritamente como um Espelho de Transmissão para a UI.
    - **Consensus KeyError Fix:** Correção de falha crítica no CaptainAgent ao processar ativos fora da matriz especialista (ex: BTC).

*   **V110.500: VISION ELITE 5.8 [MAY 01]**
    - **RSI Overbought/Oversold Filter:** Integrou leitura extrema de RSI como filtro Elite.
    - **Moving Average Momentum:** Adicionou confluência direcional de médias móveis ao Vision.
    - **Trap Zone Rejection:** Inclusão de rejeição técnica em zonas de suporte/resistência cruciais.

*   **V110.403: INDUSTRIAL PROCESS VIGILANCE [APR 30]**
    - **Demand-Aware Scan:** O Bibliotecário sincroniza o scan visual com a disponibilidade real de slots. Se não houver vaga para Blitz, ele ignora sinais M30 para poupar IA.
    - **Confidence Threshold Shield:** Elevação do rigor para ativação visual (Score >= 90 no Bibliotecário), reservando a IA apenas para sinais de alta probabilidade.
    - **Vision Analysis Cache (TTL 15m):** Implementação de cache de resultados por ativo para evitar re-análises redundantes do mesmo cenário gráfico.
    - **Operational Standby HUD:** Injeção de status de demanda e standby no Dashboard para transparência total do processo industrial.

*   **V110.402: VISION CASCADE STABILIZATION [APR 30]**
    - **Hybrid Vision Cascade:** Migração para modelos funcionais de visão (Llama 3.2 Vision 11B e Gemini 2.0 Flash Exp), resolvendo erros de "400 Bad Request" (embedding models).
    - **Quota Backoff Guard:** Implementação de bloqueio de 1 hora para o Gemini Nativo após estouro de quota gratuita, garantindo estabilidade e fluidez do backend.
    - **AI Status Refinement:** Sincronização do status da cascata com a UI para visibilidade total do estado das APIs (Cooling vs Active).

*   **V110.401: VISION OPTIMIZATION & AI RECOVERY [APR 30]**
    - **Score-Selective Vision Gate:** Implementação de threshold de Score (95) para ativação do Agente Visão, reduzindo em >70% o consumo de API e acelerando a entrada em sinais secundários.
    - **Gemma 3 Multimodal Cascade:** Atualização dos IDs de IA para a família Gemma 3 (Free) no OpenRouter, resolvendo erros de "Model Not Found" e restaurando a inteligência visual.
    - **Bypass Safety Protocol:** Novo fluxo de aprovação automática para sinais abaixo do threshold, mantendo a fluidez sem comprometer a segurança da Elite.

*   **V110.370: RADAR INTELLIGENCE & SLOT FILTERING [APR 30]**
    - **Dynamic Demand Signaling:** Implementação de mensagens contextuais no Radar ("Visão buscando SWING"), indicando a intenção ativa do agente conforme a demanda de alocação.
    - **Contextual Signal Filtering:** O Radar agora filtra sinais em tempo real, exibindo apenas as oportunidades compatíveis com slots vazios (Blitz vs Swing).
    - **Standby Mode Logic:** O sistema entra automaticamente em modo de "Standby" quando todos os slots estão ocupados, reduzindo o processamento de sinais inúteis.
    - **Flow Sentinel Visual Tracking (V110.371):** Refatoração da linha vertical de "Scanning" para atuar como um monitor dinâmico do agente de integridade (Verde: Online, Vermelho: Offline) e correção da precisão dos marcadores de entrada via `opened_at` timestamp.

*   **V110.360: SYSTEM INTEGRITY & UI NORMALIZATION [APR 29]**
    - **Orphan Trade Recovery:** Implementação de registro explícito no `trade_history` para ordens detectadas via sincronização de exchange (órfãs), resolvendo o descompasso entre banca e histórico.
    - **Frontend Side Normalization:** Refatoração global de componentes (`SlotCard`, `GridChartItem`) para suportar case-insensitivity em propriedades de `side` (BUY/LONG), corrigindo erros de projeção de alvos em ativos como TRXUSDT.
    - **Bybit API Wrapper Hardening:** Atualização do método `get_closed_pnl` para suportar consultas globais (sem símbolo obrigatório), permitindo auditorias de histórico mais abrangentes.


*   **V5.6: VISION INTELLIGENCE & MASTER CONTEXT [APR 28]**
    - **Proprietary S3 Engine:** Migração total do TradingView Widget para o motor nativo Lightweight Charts, garantindo soberania visual e fim dos erros de CSP.
    - **Triple-Pane Architecture:** Implementação de 3 painéis sincronizados (Preço, Volume Flow e RSI 14) para análise técnica profunda.
    - **Global BTC HUD:** Integração de telemetria macro (ADX, CVD, Dominância, Decorrelação) em barra fixa no topo do Observatório.
    - **Ghost Strategy Markers:** Sistema de anotação histórica para treinamento e validação do Agente Visão.
    - **Autonomous Vision Capture:** Refatoração do `ScreenshotService` para operar 100% sobre o Hub Proprietário.

*   **V4.0: SPECIALIST MATRIX & EAGLE VISION PRO [APR 26]**
    - **Specialist Brain (40 Pairs):** Implementação de matriz fixa no `librarian.py` para 40 ativos de elite. Injeção de DNA com buffers de respiro (8-25%) e atrasos de RF baseados em volatilidade.
    - **Eagle Vision PRO (Desktop UI):** Refinamento ultra-premium da sessão de gráficos com animação de *Scanning Line*, HUD de telemetria interna (RSI/ADX), Floating Tooltip OHLCV e Badges de "Tocaia Ativa".
    - **Sniper Patience (Violinada Hunter):** Novo protocolo no `AmbushAgent` que aguarda absorção no gráfico de 1m (pavios/rejeição) antes de disparar a ordem.
    - **Intelligent Breakeven (ADX-Aware):** Gatilhos de Risk-Free dinâmicos. Tendência forte (ADX > 40) trava em 20% ROI; Lateralização (ADX < 22) aguarda 40% ROI para evitar stop por ruído.
    - **Standard Green (#22c55e):** Unificação da cor verde em todo o ecossistema, eliminando tons "limão" e placeholders brancos no histórico.
    - **Official Repo Sync:** Migração final do pipeline de deploy para `1C-7.0`.

*   **V110.256: SOVEREIGN IDENTIFIER & SYNTAX RECOVERY [APR 25]**
    - **Syntax Error Resolution:** Correção de fechamentos prematuros de hooks no `cockpit.html` (especialmente `useSlotsRT` e `useBancaRT`) que causavam falha de carregamento da UI.
    - **Identifier De-confliction:** Renomeação global de `rtdb` para `sovereign_rtdb` no frontend para evitar erros de redeclaração (`Identifier already declared`) causados pelo Babel-standalone em scripts inline.
    - **Hook Consolidation:** Limpeza de duplicatas e unificação da lógica de WebSocket/REST Fallback em todos os hooks de tempo real.
    - **Librarian Integration Fix:** Correção da referência de hook na `Page10D` para apontar corretamente para `useLibrarianRT`.

*   **V110.255: SOVEREIGN SYNC & RECOVERY [APR 25]**
    - **WebSocket Pulse Restoration:** Integração do evento `sovereign-packet` no Cockpit UI, resolvendo a estagnação da telemetria e permitindo atualizações instantâneas de slots e banca.
    - **Decorrelation SSOT:** Unificação da telemetria de decorrelação com o `SignalGenerator` como fonte primária, eliminando conflitos de escala (0-1 vs 0-100) e placeholders `...%`.
    - **Paper Price Recovery:** Implementação de loop de sincronização robusto no `bankroll.py` para restaurar `entry_price` do motor de simulação para o banco de dados em caso de perda de persistência.
    - **Context Persistence:** Adição de cache para `market_context` no `SovereignService` para garantir estabilidade da UI durante a inicialização.

*   **V110.251: PAPER MODE ENFORCEMENT & TZ STABILITY [APR 25]**
    - **Paper Mode Injection:** Ativação forçada via variáveis de ambiente Railway (`OKX_EXECUTION_MODE=PAPER`) para garantir isolamento total e saldo de $100.00.
    - **Timezone Fix:** Normalização de todos os campos `DateTime` para naive (sem offset) no Postgres, eliminando erros de persistência no `VaultCycle`.
    - **Leverage 50x Standard:** Unificação da alavancagem de 50x em todos os slots (Blitz e Swing) para acelerar o crescimento da banca simulada.
    - **Database Repair:** Sincronização de IDs de banca (ID 1 e 'status') e correção de esquema de colunas dinâmicas no Postgres.
    - **Official Repo Sync:** Migração definitiva do fluxo de deploy para o repositório `1C-7.0`.

*   **V110.210: FLOW INTEGRITY & PERSISTENCE [APR 25]**
    - **Sentinel Agent:** Implementação do `FlowSentinel` para monitoramento post-mortem de trades, detectando gaps entre estados de memória e persistência.
    - **Boot Persistence Sync:** Carregamento automático de slots e estado Paper do Postgres no boot, garantindo que o robô retome exatamente onde parou.
    - **SystemState Engine:** Nova camada de persistência para blobs de estado do sistema, eliminando inconsistências após reinicializações.
    - **End-to-End Validation:** Garantia absoluta de que nenhum trade seja perdido entre a transição Slot -> Histórico.

*   **V110.209: PWA OPTIMIZATION & VAULT RESTORATION [APR 25]**
    - **Vault History Activation:** Implementação dos métodos de recuperação de histórico no `SovereignService`, conectando a UI ao banco de dados Postgres para visualização de trades arquivadas.
    - **URL Unification:** Redirecionamento de `/cockpit.html` para `/`, eliminando conflitos de acesso e estabelecendo a raiz como ponto único de comando.
    - **PWA Re-activation:** Restauração do Service Worker com detecção automática de atualizações e limpeza de scripts de desregistração legados.
    - **Smart Caching:** Implementação de estratégias Network-First para lógica e Cache-First para bibliotecas/assets.
    - **Offline Fallback:** Integração da página `offline.html` para resiliência de conectividade.

*   **V110.208: SELF-HEALING & BLACK BOX PERSISTENCE [APR 24]**
    - **Auto-Migration:** Implementação de migração automática de esquema no boot para corrigir divergências de colunas no Postgres.
    - **Black Box Protocol:** Backup de emergência em JSON (`emergency_trades.json`) para garantir 100% de persistência caso o banco falhe.

*   **V110.207: BRANDING RESTORATION & CACHE SHIELD [APR 24]**
    - **Logo Restoration:** Reintegração do logo oficial `logo10DTrasp.png` com transparência nativa.
    - **Cache-Busting V4:** Implementação de sufixos de versão nas imagens para forçar atualização em todos os navegadores.

*   **V110.203: DATA INTEGRITY & ATOMIC ARCHIVAL [APR 24]**
    - **Atomic free_slot:** Refatoração do método de liberação de slots para arquivar obrigatoriamente trades no histórico antes da limpeza.
    - **Zero Data Loss:** Garantia de que ordens encerradas por Auditoria ou Reset de Fábrica sejam preservadas no Vault.

*   **V110.202: BOOT PERSISTENCE & SYNC RELIABILITY [APR 24]**
    - **Forced Boot Sync:** Remoção da lógica de pular sincronia de slots no `main.py`; o robô agora recupera o estado do banco no início.
    - **Persistence Shield:** Proteção contra perda de ordens durante deploys ou reinicializações do servidor Railway.

*   **V110.201: BRANDING SIMPLIFICATION & OPEN ACCESS [APR 24]**
    - **System 10D UI:** Simplificação visual da tela de login para um estilo minimalista.
    - **Access Key:** Configuração da chave padrão `123` para facilitar o acesso livre do administrador.

*   **V110.200: BLINDAGEM PHASE & SOVEREIGN AUTH [APR 24]**
    - **Fortress Auth:** Sistema de login soberano com autenticação JWT/Token no backend e frontend.
    - **Guardian Agent:** Implementação do agente de custódia para manutenção de integridade e segurança.
    - **Scrubbing:** Limpeza de >150 arquivos legados, reduzindo a dívida técnica e poluição do backend.

*   **V110.870: MIGRATION COMPLETE TO OKX & DASHBOARD BLINDING [MAY 26]**
    - **OKX Frontend Integration:** Migração de 100% dos canais públicos de WebSockets e APIs de cotação externa da Bybit no frontend para a **OKX** (`wss://ws.okx.com:8443/ws/v5/public` e `https://www.okx.com/api/v5/market/candles`).
    - **PnL Fallback System:** Implementação de fallback inteligente e robusto no cockpit: se o WebSocket da exchange falhar no navegador, a UI consome de forma instantânea o PnL real e os dados calculados de forma cirúrgica pelo nosso backend.
    - **Visual Hardening:** Adequação de 100% dos painéis, nomenclaturas de Health Check e modal de decolagem de "Bybit" para "OKX", erradicando qualquer resíduo legado.

*   **V110.199: PRODUCTION DOMAIN FINALIZATION [APR 24]**
    - **CORS Hardening:** Inclusão de variantes `www` e domínios de produção no backend para eliminar bloqueios de segurança.
    - **Full Domain Parity:** Sincronização de regras de acesso para `1crypten.space`.

*   **V110.198: DOMAIN & SSL HARDENING [APR 24]**
    - **WSS Protocol Fix:** Inteligência de detecção de protocolo no `cockpit.html` para suportar `wss://` automaticamente em domínios HTTPS.
    - **Custom Domain Ready:** Ajustes de roteamento para garantir conectividade em `1crypten.space`.

*   **V110.197: RUNTIME STABILITY & SCOPE HARDENING [APR 24]**
    - **Execution Fix:** Resolvido `NameError: is_spring_strike` no `BankrollManager` via pré-declaração de variáveis de controle.
    - **Database Sync Fix:** Resolvido `TypeError` de múltiplos valores para o argumento `id` em atualizações de banca e slots.

*   **V110.196: DATABASE HARDENING & RATE LIMIT SHIELD [APR 24]**
    - **SQL Schema Sync:** Modelo `Slot` no Postgres atualizado para suportar 100% dos campos de telemetria e inteligência (margin, leverage, fleet_intel).
    - **CoinGecko Shield:** Implementação de `asyncio.Lock` no `MacroAnalyst` para evitar erros 429 durante picos de análise de sinais.
    - **Nuclear Reset:** Disponibilizado script `nuclear_schema_reset.py` para sincronização forçada de ambiente.

*   **V110.195: ORPHAN GENESIS PROTOCOL [APR 24]**
    - **Genesis Recovery:** Ordens re-adotadas da exchange (órfãs) agora geram automaticamente um `genesis_id` para identificação no Cockpit.
    - **ID Persistence:** Garantia de que o `genesis_id` e o `order_id` sejam preservados durante os ciclos de sincronização real-time do Bankroll.

*   **V110.194: CAPTAIN SCOPE STABILIZATION [APR 24]**
    - **Captain Unbound Fix:** Correção de falha fatal (UnboundLocalError) ao processar sinais SNIPER/Elite; variáveis de escopo (`is_decorrelated`, `is_spring_vanguard`) agora inicializadas corretamente.
    - **Vanguard Stability:** Garantia de que sinais Vanguard passem pelas travas de tendência H4 sem quebras de execução.

*   **V110.193: GHOST-LOCK PURGE & SYMBOL HARDENING [APR 24]**
    - **Ghost-Lock Resolution:** Implementação do protocolo de Database Wipe para limpar estados corrompidos de slots "4/4" sem ordens reais.
    - **Symbol Purgue:** Remoção completa de `PEPEUSDT` (substituído por `1000PEPEUSDT`) em todas as camadas de configuração para evitar erros de subscrição no WebSocket.
    - **Scan Resumption:** Otimização do loop de escaneamento para retomar imediatamente após a limpeza de estado.

*   **V110.192: SOVEREIGN STABILIZATION & RADAR SYNC [APR 24]**
    - **Radar Sync Fix:** Correção da dessincronização de payload no frontend; o Radar agora recebe o objeto completo `{signals, decisions, market_context}`.
    - **Bybit WS Hardening:** Remoção definitiva de ativos com símbolos inválidos (ex: `PEPEUSDT.P`) que causavam o crash cíclico do WebSocket.
    - **ML Feedback Loop Restoration:** Implementação do método `get_vault_history` no `SovereignService`, permitindo que o Librarian processe o pós-mortem de ML.
    - **Memory & Lifecycle Safety:** Eliminação de `UnboundLocalError` no gerador de sinais e `KeyError` no gerenciamento de conexões WebSocket.

*   **V110.181: SOVEREIGN ENGINE & WS RECOVERY [APR 24]**
    - **Sovereign Engine Deployment:** Ativação do motor de sincronização WebSocket centralizado no frontend.
    - **Universal Bridge Sync:** Correção de sincronização em tempo real para indicadores críticos (BTC Price, Equity) via `cockpit.html`.
    - **Placeholder Purge:** Eliminação definitiva dos estados "---" no Cockpit HUD.
    - **Backend-Frontend Handshake:** Estabilização do fluxo de pacotes `system_state` e `banca_status` via `/ws/cockpit`.

*   **V110.176: SOVEREIGN REFINEMENT — BUG FIX & VAULT MIGRATION [APR 24]**
    - **Vault Postgres Migration:** Migração completa da lógica de ciclos e retiradas do Firestore para tabelas relacionais no Postgres.
    - **AttributeError Purge:** Limpeza total de referências ao `rtdb` e `db` do Firebase em todo o backend.
    - **Sovereign Interface Expansion:** Implementação de métodos de compatibilidade (`get_radar_pulse`, `get_chat_status`, etc.) no `SovereignService`.

*   **V110.175: RAILWAY SOVEREIGN — EMANCIPAÇÃO TOTAL 🚂 [APR 24]**
    - **SovereignService Deployment:** Introdução do `SovereignService` como o orquestrador central de persistência e comunicação, eliminando 100% dos resíduos do SDK do Firebase.
    - **Postgres Primary SSOT:** O PostgreSQL do Railway torna-se a fonte primária de verdade para saldos, slots, histórico e Genesis IDs, gerenciado localmente.
    - **Native WebSocket Broadcast:** Transmissão de sinais, pulso e estados de slot via WebSocket nativo (`/ws/cockpit`), garantindo latência ultra-baixa para o Cockpit UI.
    - **Fast Oracle Boot:** Otimização do tempo de estabilização do Oráculo para 30s, permitindo reinicializações ágeis e resilientes.

*   **V110.174: SELECTIVE INTELLIGENCE UPGRADE — VANGUARD [APR 24]**
    - **Asset Trend Guard**: Implementação de trava obrigatória para alinhar trades com a tendência H4 em ativos de volatilidade EXTREME.
    - **Spring Directionality**---

## 🏗️ ARQUITETURA DE SISTEMA (V110.823)

### 1. Camada de Redirecionamento e Servimento de Estáticos (FastAPI)
- **Catch-All Resiliente:** Processamento inteligente no FastAPI que limpa hashes e query-params do path físico antes de verificar arquivos no container, garantindo que Service Workers, ícones da PWA e scripts estáticos em `/vendor` nunca retornem 404.
- **Unified Port (8085):** O app principal monta o diretório de estáticos em `/static-frontend`, serve o Observatório em `/observatory` e expõe a Fortress Auth na mesma porta, unificando a experiência desktop e mobile sem proxies de CORS.

### 2. Camada de Comunicação Reativa (WebSockets)
- **ws_cockpit:** Ponte de transmissão duplex local/nuvem. Envia um snapshot de estado imediato no `onopen` para evitar telas pretas e sincroniza os 4 slots, cotação do BTC e pulso do radar instantaneamente.

### 3. Camada de Execução (Actor Model)
- **OrderProjectionService:** fonte única de verdade para ROI, stop price, fase operacional, linhas do gráfico, `tickSize`, `ctVal`, margem e PnL estimado. O frontend não recalcula alvos quando `projection.levels` existe.
- **⚡ FlashAgent (V1.2):** motor principal de Escadinha, Emancipação e Moonbags. Monitora **todos os slots + moonbags a cada 1 segundo** e consome `OrderProjectionService` para decidir. A regra de melhoria/violação de stop é única para LONG/SHORT e coberta por testes de invariantes:
  - **Slots Táticos:** Escadinha oficial (30%→6%, 50%→25%, 70%→45%, 110%→80%, 150%→110% + Moonbag)
  - **Emancipação:** ao bater 150% ROI, promove a mesma ordem para Moonbag preservando identidade e metadados
  - **Moonbags:** trailing progressivo (200%→150%, 300%→220%, 400%→280%, 500%→350%, 600%→420%, 700%→500%, 750%→600%, 800%→650%, 1000%→800%, 1200%→1000%, depois `ULTRA_*` a cada 400% com stop 250% ROI abaixo do alvo)
  - **Cache:** slots e moonbags em cache com refresh a cada 3s para reduzir queries no banco
  - **Stops de lucro:** confirma??o com pre?o REST fresco da OKX quando o WebSocket/cache n?o confirma viola??o, e fechamento s?ncrono por `FLASH_PROFIT_SL`.
- **4 × SlotOperatorAgent:** instâncias independentes por slot, agora como observadores/failsafe de slot. Não são mais escritores primários de escadinha ou emancipação; esta autoridade pertence ao Flash.
- **CaptainAgent:** despachante puro de sinais com quality gate backend-first. Lê slots reais via `get_active_slots()`, considera ocupados apenas slots com ordem válida, usa thresholds 45%/50% conforme ocupação, não permite que o modo PAPER aprove sinais bloqueados artificialmente, aplica `contract_quality` para penalizar/bloquear contratos ruins e expõe/resetta travas voláteis (`active_tocaias`, `processing_lock`, `cooldown_registry`, `daily_symbol_trades`) no fluxo administrativo.
- **Guardião da Banca:** autoridade preventiva acima do Capitão. Avalia saúde da banca, drawdown, lucro protegido, exposição por slots/moonbags, histórico por símbolo e suspensões de pares antes de liberar uma nova ordem. O score mínimo da banca usa o Radar Score (`score`/`score_radar`) como métrica principal; `unified_confidence` fica como contexto de auditoria. Em `ACUMULACAO_PROTEGIDA`, ele eleva o score mínimo e mantém 4/4 slots disponíveis; limita slots apenas em `CAUTELOSO`, `DEFESA` ou `PRESERVACAO_TOTAL`. Expõe relatório em PT-BR por `/api/bankroll/guardian-report`.
- **Harvester (Ceifeiro Infinito):** níveis WAVE→APEX e continuação `ULTRA_*` pós-1200%, mantendo colheitas parciais e trailing sem teto fixo.
- **Portfolio Guardian:** atomic state machine, Knife-Drop em -15% do peak ROI (gatilho 70%), Moonbag Shield (emancipadas imunes ao Facão).
- **SignalGenerator (Radar):** Sieve 3-camadas (T1 Scanner → T2 Tape Reading → T3 Elite 40 Matrix) + Vision Cascade (Gemma 3 / Gemini Flash fallback).
- **Oracle:** SSOT de regime de mercado (ALTA/BAIXA/LATERAL com threshold ADX>30), validação e FleetAudit pós-trade.
- **Anti-Slippage Engine:** Greedy Snake Sharding em 4 cohorts balanceados com Random Jitter 0-350ms para pulverizar ordens no book.

### 4. Motor de Trading (Sniper + Escadinha + Moonbag)
- **Ciclo:** Flash monitora em alta frequência; Captain abre slots; SlotOperator observa; backend calcula e frontend renderiza.
- **Fórmula oficial de ROI:** `((current - entry) / entry) * leverage * 100` para LONG e `((entry - current) / entry) * leverage * 100` para SHORT.
- **Fórmula oficial de preço do stop:** `entry * (1 + stop_roi / (leverage * 100))` para LONG e `entry * (1 - stop_roi / (leverage * 100))` para SHORT, sempre arredondada por `tickSize` OKX.
- **Escadinha oficial:** 30%→6%, 50%→25%, 70%→45%, 110%→80%, 150%→110% + emancipação.
- **Moonbag oficial:** hard-lock mínimo de emancipação em `+110%` ROI, depois 200%→150%, 300%→220%, 400%→280%, 500%→350%, 600%→420%, 700%→500%, 750%→600%, 800%→650%, 1000%→800%, 1200%→1000%; acima disso, níveis `ULTRA_*` continuam a cada 400% ROI com stop 250% abaixo do alvo rompido.
- **Contratos OKX:** `ctVal` não altera o preço do stop; ele é usado para notional, margem, quantidade de contratos e PnL USD.
- **Margem Dinâmica para Banca Pequena:** Força margem mínima de $3.00 USD por slot quando a banca for inferior a $50.00 USD para viabilizar execução de contratos OKX.
- **Saúde da Banca:** `BankrollGuardian` classifica o ciclo em `ACUMULACAO`, `ACUMULACAO_PROTEGIDA`, `CAUTELOSO`, `DEFESA` ou `PRESERVACAO_TOTAL`. A equity operacional vem de `base_balance + PnL realizado + PnL aberto dos slots + PnL aberto das moonbags`. Em lucro forte, protege o pico da banca e aumenta o score mínimo mantendo 4 slots; em cautela/defesa/preservação, reduz ou pausa novas entradas.
- **Suspensão por Par:** perdas recentes em `trade_history` geram quarentena temporária do símbolo. Duas perdas consecutivas elevam a suspensão para até 24h.

### 5. Auth & Failsafe
- **Fortress Auth:** JWT + bypass admin `123` (papel "Sovereign").
- **PAPER Mode automático:** detectado se chaves OKX ausentes — banca $100 injetada e modo de simulação ativado.
- **GUARDIAN_PROMPT.md:** blindagem de persona do bot Telegram sob flag `HERMES_GUARDIAN=1`.

### 6. Sistema de Autenticação, Cadastro e Painel ADM (V110.802)
- **Centralização em `/login`:** Toda a autenticação é gerenciada de forma limpa no arquivo dedicado [login.html](file:///c:/Users/spcom/Desktop/1C-7.0/frontend/login.html), adotando 100% o design minimalista **FortressLogin** (campo único de `CHAVE DE ACESSO`, botão preto/branco e logo 1C circular).
- **Cadastro Dinâmico ("Solicitar Acesso"):** Integrado sutilmente no mesmo card central. Quando clicado, alterna dinamicamente no frontend para coletar *Novo Usuário*, *Email* e *Senha*.
- **Controle de Acesso (Painel ADM):** Acessível no menu lateral do Cockpit (rota `#/adm` mapeada para a tela `AdminUsersPage` no [cockpit.html](file:///c:/Users/spcom/Desktop/1C-7.0/frontend/cockpit.html)). Permite ao administrador aprovar (liberar), bloquear ou excluir usuários de forma granular com IDs persistentes.
- **Fluxo de Logout Limpo:** O logout no Cockpit limpa incondicionalmente todos os tokens (`auth_token`, `sniper_token`, `refresh_token`, `user`), forçando o redirecionamento seguro para `/login` e prevenindo logins automáticos por tokens órfãos.
- **Resiliência Anti-Cache:** O arquivo raiz `index.html` atua como desregistrador forçado de Service Workers antigos no navegador do usuário e faz o redirecionamento imediato para `/login`, quebrando loops infinitos de cache em produção.

## 🗄️ CAMADA DE DADOS HÍBRIDA & ESQUEMAS (V110.823)

O sistema opera em uma arquitetura de dados híbrida e resiliente, utilizando espelhamento e auto-healing nas inicializações:

### 1. PostgreSQL (Mestre / SSOT no Railway)
Utilizado em produção como Fonte Única de Verdade (SSOT) para toda a lógica de negócios e status financeiro do robô.
*   **`banca_status`**: Armazena o saldo atual, o risco real alocado, o número de slots ocupados e a banca simulada configurada.
    *   *Colunas chave*: `saldo_total` (Float), `configured_balance` (Float), `risco_real_percent` (Float), `status` (String).
*   **`slots`**: Gerencia o estado de alocação de cada uma das 4 instâncias de `SlotOperatorAgent`.
    *   *Colunas chave*: `id` (Integer, 1-4), `symbol` (String), `side` (String), `qty` (Float), `entry_price` (Float), `entry_margin` (Float), `initial_stop` (Float), `current_stop` (Float), `target_price` (Float), `leverage` (Float), `status_risco` (String), `sentinel_first_hit_at` (Float), `vision_url` (String).
*   **`trade_history`**: Ledger definitivo de auditoria e arquivamento de ordens concluídas.
    *   *Colunas chave*: `order_id` (String), `genesis_id` (String), `symbol` (String), `side` (String), `pnl` (Float), `pnl_percent` (Float), `timestamp` (DateTime), `vision_url` (String), `data` (JSONB).
*   **`moonbags`**: Continuação da mesma ordem após emancipação em 150% ROI, com trailing profit controlado pelo Flash/Ceifeiro.
    *   *Colunas chave*: `uuid` (String, `{symbol}_{opened_at}`), `symbol` (String), `side` (String), `qty` (Float), `entry_price` (Float), `entry_margin` (Float), `initial_stop` (Float), `current_stop` (Float), `target_price` (Float), `leverage` (Float), `order_id` (String), `genesis_id` (String), `slot_type` (String), `strategy` (String), `strategy_label` (String), `opened_at` (Float), `contract_meta` (JSONB), `flash_last_action` (String), `flash_last_stop_roi` (Float), `pnl_percent` (Float), `sentinel_first_hit_at` (Float).
*   **`radar_pulse`**: Cache reativo de confluências e sinais do mercado técnico.

### 2. SQLite Local (`auth.db`)
Banco de dados autônomo local e isolado para controle de acesso, auditoria administrativa e armazenamento de credenciais criptografadas.
*   **`users`**: Cadastro de operadores e administradores.
    *   *Colunas*: `id` (Integer), `username` (String), `email` (String), `password_hash` (String), `role` (String, `admin` ou `user`), `is_active` (Boolean).
*   **`user_okx_tokens`**: Tokens de API OKX criptografados simetricamente de forma atômica por usuário.
*   **`audit_log`**: Histórico forense de acessos e ações tomadas no painel administrativo `/adm`.
*   **`user_sessions`**: Controle de sessões ativas e hashes de Refresh Tokens para segurança JWT.

---

## 🎨 MODULARIZAÇÃO DO FRONTEND (V110.823)

Para sanar a complexidade do monolítico de 9.100 linhas originais no frontend, a aplicação foi segmentada em componentes reativos autocontidos compilados JIT (Babel standalone):
1.  **Orquestrador central (`frontend/app.js`)**: Gerencia o roteador (`ReactRouterDOM`), alertas `Toast`, escuta reativa WebSockets `/ws/cockpit` e renderização base do cockpit.
2.  **Diretório de Componentes (`frontend/components/`)**:
    *   `TriumphModal.js`: Modal rico com telemetria forense, print e laudo de conformidade do Agente Visão.
    *   `SettingsPage.js`: Ajustes de tema, reset do simulador e chaves OKX de usuários.
    *   `AdminUsersPage.js`: Painel ADM exclusivo para controle de acesso e liberação de usuários ativos.
    *   `TakeoffModal.js` & `DeepAnalysisModal.js`: checklist e auditoria dos ativos.
3.  **Estilo Unificado (`frontend/css/cockpit.css`)**: Centraliza todas as regras visuais, auras Gemini neon e animações.
4.  **Renderização de Stops Backend-First:** `cockpit.html` consome `projection.levels` de `/api/slots` e `/api/moonbags` para desenhar o Mapa Flash completo no gráfico, da escadinha até a moonbag. Cálculos locais de escadinha/moonbag permanecem apenas como fallback se uma ordem legada chegar sem `projection`. As price lines usam assinatura de ordem/projeção para evitar flicker durante refresh de candles, pulso ou WebSocket.
5.  **Contrato OKX no Relatório do Radar:** `TriumphModal.js` mostra `ctVal`, `tickSize`, `lotSize/qtyStep`, `minQty`, `maxLeverage`, preço de referência, margem mínima e a fórmula de ROI alavancado para cada sinal ativo.
6.  **Slot Cards Operacionais (V110.814):** cards de ordem ativa exibem `Entry`, `Stop Atual`, `Emancipação 150%`, `Flash`, `Stop Atual` em ROI, `Stop Alvo` com nome/ROI do próximo nível, próximo gatilho real da escadinha/moonbag e `Stop Flash Sugerido` apenas quando `recommended_stop` melhora o stop atual. Ícones legados soltos foram removidos; o badge tático segue `projection.active_level`/`projection.flash`.
7.  **Banca com Guardião (V110.815):** Desktop e Mobile consomem `BankrollGuardian` por `/api/bankroll/guardian-report` e exibem saúde, modo, score mínimo, lucro protegido, devolução permitida e pares suspensos junto do patrimônio/equity. O patrimônio líquido usa `guardianReport.equity` quando disponível; cards e totais de slots/moonbags usam `projection.pnl_usd` como fonte oficial de PnL em dólar. O hook de moonbags preserva `projection` REST quando o RTDB chega sem enriquecimento. O relatório também expõe `stored_equity`, `calculated_equity`, `realized_pnl`, `open_slots_pnl`, `open_moonbags_pnl` e `protected_floor` para auditoria.

---

*Documento atualizado em: 2026-06-08 (V110.823) Sincronizado*
*Este documento reflete o backend como fonte única de verdade para stops, projeções, contratos OKX, quality gate do Capitão, Guardião da Banca, Radar Contract Intelligence, reset de runtime do Capitão, telemetria Flash nos cards, inteligência da banca e renderização estável do Cockpit.*
