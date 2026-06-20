# -*- coding: utf-8 -*-
"""Apply V111.3 TREND_FOCUS changes to captain.py, bankroll.py, and cockpit.html"""

import sys
sys.stdout.reconfigure(encoding='utf-8')

def edit_captain_py():
    path = 'backend/services/agents/captain.py'
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    changes = 0
    
    # === EDIT 1: Lines 522-530 - _get_fleet_consensus() ===
    old = (
        '            max_allowed_slots = 20 if is_ranging_mode else 40\n'
        '            free_slots = max_allowed_slots - occupied_count\n'
        '            required_confidence = 20.0 if free_slots >= 2 else 30.0\n'
        '\n'
        '            if unified_score < required_confidence:\n'
        '                approved = False\n'
        '                reasons.append(f"LOW_FLEET_CONFIDENCE: {unified_score:.1f}% < {required_confidence:.1f}% (Slots Livres: {free_slots})")\n'
        '                logger.warning(f"\U0001f6e1\U0001f6e1 [V110.100] {symbol} {side} BLOCKED by Low Confidence ({unified_score:.1f}%, Slots: {free_slots})")\n'
        '            else:\n'
        '                if free_slots >= 2:\n'
        '                    logger.info(f"\U0001f4aa [CAPTAIN-BOOST] {symbol} aprovado com {unified_score:.1f}% (Slots vazios: {free_slots})")'
    )
    new = (
        '            # [V111.3 TREND_FOCUS] Em LATERAL nao abrir nada. Em TENDENCIA, max 20 slots.\n'
        '            if is_ranging_mode:\n'
        '                approved = False\n'
        '                reasons.append("MERCADO_LATERAL_PAUSADO: ADX < 25. Sistema aguardando tendencia.")\n'
        '                logger.warning(f"[V111.3 TREND_FOCUS] {symbol} {side} BLOQUEADO - Mercado Lateral (ADX < 25). Apenas operamos em tendencia.")\n'
        '            else:\n'
        '                max_allowed_slots = 20  # [V111.3] Hard limit de 20 slots em tendencia\n'
        '                free_slots = max_allowed_slots - occupied_count\n'
        '                required_confidence = 20.0 if free_slots >= 2 else 30.0\n'
        '\n'
        '                if unified_score < required_confidence:\n'
        '                    approved = False\n'
        '                    reasons.append(f"LOW_FLEET_CONFIDENCE: {unified_score:.1f}% < {required_confidence:.1f}% (Slots Livres: {free_slots})")\n'
        '                    logger.warning(f"\U0001f6e1\U0001f6e1 [V110.100] {symbol} {side} BLOCKED by Low Confidence ({unified_score:.1f}%, Slots: {free_slots})")\n'
        '                else:\n'
        '                    if free_slots >= 2:\n'
        '                        logger.info(f"\U0001f4aa [CAPTAIN-BOOST] {symbol} aprovado com {unified_score:.1f}% (Slots vazios: {free_slots})")'
    )
    if old in content:
        content = content.replace(old, new, 1)
        changes += 1
        print('OK Edit 1: _get_fleet_consensus()')
    else:
        print('FAIL Edit 1: _get_fleet_consensus()')
    
    # === EDIT 2: Lines 680-692 - monitor_signals() ===
    old = (
        '                # Dynamic max slots based on regime\n'
        '                if balance < 10.0 and okx_rest_service.execution_mode != "PAPER":\n'
        '                    max_total_slots = 2\n'
        '                else:\n'
        '                    is_ranging_mode = True\n'
        '                    try:\n'
        '                        from services.okx_ws_public import okx_ws_public_service\n'
        '                        adx = getattr(okx_ws_public_service, \'btc_adx\', 0)\n'
        '                        is_ranging_mode = (adx < 25)\n'
        '                    except Exception:\n'
        '                        pass\n'
        '                    from config import settings as loop_settings\n'
        '                    max_total_slots = loop_settings.MAX_SLOTS_LATERAL if is_ranging_mode else loop_settings.MAX_SLOTS_TRENDING\n'
        '                \n'
        '                # [V110.116] Heartbeat Log'
    )
    new = (
        '                # [V111.3 TREND_FOCUS] Em LATERAL pausa tudo. Em TENDENCIA, max 20 slots.\n'
        '                is_ranging_mode = True\n'
        '                try:\n'
        '                    from services.okx_ws_public import okx_ws_public_service\n'
        '                    adx = getattr(okx_ws_public_service, \'btc_adx\', 0)\n'
        '                    is_ranging_mode = (adx < 25)\n'
        '                except Exception:\n'
        '                    pass\n'
        '\n'
        '                # [V111.3] Se mercado LATERAL, pausa processamento de sinais\n'
        '                if is_ranging_mode:\n'
        '                    if not hasattr(self, "_last_lateral_log") or (time.time() - self._last_lateral_log) > 60:\n'
        '                        logger.info(f"[V111.3 TREND_FOCUS] Mercado LATERAL (ADX < 25). Sistema pausado aguardando tendencia.")\n'
        '                        self._last_lateral_log = time.time()\n'
        '                    await asyncio.sleep(10)\n'
        '                    continue\n'
        '\n'
        '                if balance < 10.0 and okx_rest_service.execution_mode != "PAPER":\n'
        '                    max_total_slots = 2\n'
        '                else:\n'
        '                    max_total_slots = 20  # [V111.3] Hard limit de 20 slots em tendencia\n'
        '\n'
        '                # [V110.116] Heartbeat Log'
    )
    if old in content:
        content = content.replace(old, new, 1)
        changes += 1
        print('OK Edit 2: monitor_signals()')
    else:
        print('FAIL Edit 2: monitor_signals()')
        idx = content.find('# Dynamic max slots based on regime')
        if idx >= 0:
            print(f'  Found at position {idx}')
            # Show context
            start = max(0, idx - 10)
            end = min(len(content), idx + 500)
            print(repr(content[start:end]))
    
    # === EDIT 3: Lines 812-825 - _blitz_scan_loop() ===
    old = (
        '                # Dynamic max slots based on regime\n'
        '                balance = await bankroll_manager.get_live_operating_equity()\n'
        '                if balance < 10.0 and okx_rest_service.execution_mode != "PAPER":\n'
        '                    max_total_slots = 2\n'
        '                else:\n'
        '                    is_ranging_mode = True\n'
        '                    try:\n'
        '                        from services.okx_ws_public import okx_ws_public_service\n'
        '                        adx = getattr(okx_ws_public_service, \'btc_adx\', 0)\n'
        '                        is_ranging_mode = (adx < 25)\n'
        '                    except Exception:\n'
        '                        pass\n'
        '                    from config import settings as loop_settings\n'
        '                    max_total_slots = loop_settings.MAX_SLOTS_LATERAL if is_ranging_mode else loop_settings.MAX_SLOTS_TRENDING'
    )
    new = (
        '                # [V111.3 TREND_FOCUS] Em LATERAL pausa tudo. Em TENDENCIA, max 20 slots.\n'
        '                is_ranging_mode = True\n'
        '                try:\n'
        '                    from services.okx_ws_public import okx_ws_public_service\n'
        '                    adx = getattr(okx_ws_public_service, \'btc_adx\', 0)\n'
        '                    is_ranging_mode = (adx < 25)\n'
        '                except Exception:\n'
        '                    pass\n'
        '\n'
        '                # [V111.3] Se mercado LATERAL, bloqueia scan\n'
        '                if is_ranging_mode:\n'
        '                    logger.debug("[BLITZ-LOOP] Mercado LATERAL. Scan pausado.")\n'
        '                    await asyncio.sleep(BLITZ_SCAN_INTERVAL)\n'
        '                    continue\n'
        '\n'
        '                balance = await bankroll_manager.get_live_operating_equity()\n'
        '                if balance < 10.0 and okx_rest_service.execution_mode != "PAPER":\n'
        '                    max_total_slots = 2\n'
        '                else:\n'
        '                    max_total_slots = 20  # [V111.3] Hard limit de 20 slots em tendencia'
    )
    if old in content:
        content = content.replace(old, new, 1)
        changes += 1
        print('OK Edit 3: _blitz_scan_loop()')
    else:
        print('FAIL Edit 3: _blitz_scan_loop()')
    
    # === EDIT 4: Lines 1098-1103 - _run_user_execution_logic() max_allowed_slots ===
    old = (
        '            # Detecta regime de mercado dinamicamente para calibrar limite de slots\n'
        '            is_ranging_mode = True\n'
        '            try:\n'
        '                from services.okx_ws_public import okx_ws_public_service\n'
        '                adx = getattr(okx_ws_public_service, \'btc_adx\', 0)\n'
        '                is_ranging_mode = (adx < 25)\n'
        '            except Exception:\n'
        '                pass\n'
        '            max_allowed_slots = 20 if is_ranging_mode else 40'
    )
    new = (
        '            # [V111.3 TREND_FOCUS] Em LATERAL bloqueia execucao. Em TENDENCIA, max 20 slots.\n'
        '            is_ranging_mode = True\n'
        '            try:\n'
        '                from services.okx_ws_public import okx_ws_public_service\n'
        '                adx = getattr(okx_ws_public_service, \'btc_adx\', 0)\n'
        '                is_ranging_mode = (adx < 25)\n'
        '            except Exception:\n'
        '                pass\n'
        '\n'
        '            # [V111.3] Se LATERAL, bloqueia execucao\n'
        '            if is_ranging_mode:\n'
        '                msg = f"[V111.3 TREND_FOCUS] {symbol} ({side}) bloqueado. Mercado LATERAL (ADX < 25). Sistema pausado."\n'
        '                logger.info(msg)\n'
        '                await firebase_service.log_event("TREND_FOCUS", msg, "INFO")\n'
        '                await firebase_service.update_signal_outcome(best_signal.get("id"), "TREND_FOCUS_LATERAL_BLOCK")\n'
        '                self.active_tocaias.discard(symbol)\n'
        '                return\n'
        '\n'
        '            max_allowed_slots = 20  # [V111.3] Hard limit de 20 slots em tendencia'
    )
    if old in content:
        content = content.replace(old, new, 1)
        changes += 1
        print('OK Edit 4: _run_user_execution_logic() max_allowed_slots')
    else:
        print('FAIL Edit 4: _run_user_execution_logic() max_allowed_slots')
        idx = content.find('# Detecta regime de mercado dinamicamente para calibrar limite de slots')
        if idx >= 0:
            print(f'  Found at position {idx}')
    
    # === EDIT 5: LATERAL_ONLY_DECOR filter ===
    old = (
        'elif is_market_ranging and strategy != "DECOR":\n'
        '                consensus["approved"] = False\n'
        '                consensus["reason"] = "LATERAL_ONLY_DECOR"\n'
        '                logger.info(f"\U0001f6ab [FLEET-GUARD] {symbol} ({strategy}) rejeitado em RANGING. Apenas a estrategia DECOR (desgrudados) e permitida em mercado lateral.")'
    )
    new = (
        'elif is_market_ranging:\n'
        '                consensus["approved"] = False\n'
        '                consensus["reason"] = "MERCADO_LATERAL_PAUSADO"\n'
        '                logger.info(f"[V111.3 TREND_FOCUS] {symbol} ({strategy}) rejeitado. Mercado LATERAL - sistema pausado aguardando tendencia.")\n'
        '            elif strategy == "DECOR":\n'
        '                consensus["approved"] = False\n'
        '                consensus["reason"] = "DECOR_SUSPENSO"\n'
        '                logger.info(f"[V111.3 TREND_FOCUS] {symbol} ({strategy}) rejeitado. Pares DECOR/desgrudados suspensos. So operamos pares seguindo BTC.")'
    )
    if old in content:
        content = content.replace(old, new, 1)
        changes += 1
        print('OK Edit 5: LATERAL_ONLY_DECOR filter')
    else:
        print('FAIL Edit 5: LATERAL_ONLY_DECOR filter')
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'\nTotal captain.py changes: {changes}/5')

edit_captain_py()
print('Done!')
