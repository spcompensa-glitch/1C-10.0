# -*- coding: utf-8 -*-
"""Fix Edit 1 in captain.py using exact text patterns"""

with open('backend/services/agents/captain.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Exact text from lines 522-532
old = (
    '            max_allowed_slots = 20 if is_ranging_mode else 40\n'
    '            free_slots = max_allowed_slots - occupied_count\n'
    '            required_confidence = 20.0 if free_slots >= 2 else 30.0\n'
    '            \n'
    '            if unified_score < required_confidence:\n'
    '                approved = False\n'
    '                reasons.append(f"LOW_FLEET_CONFIDENCE: {unified_score:.1f}% < {required_confidence:.1f}% (Slots Livres: {free_slots})")\n'
    '                logger.warning(f"\U0001f6e1\ufe0f [V110.100] {symbol} {side} BLOCKED by Low Confidence ({unified_score:.1f}%, Slots: {free_slots})")\n'
    '            else:\n'
    '                if free_slots >= 2:\n'
    '                    logger.info(f"\U0001f4aa [CAPTAIN-BOOST] {symbol} aprovado com {unified_score:.1f}% (Slots vazios: {free_slots})")\n'
    '                \n'
)

if old in content:
    content = content.replace(old, '', 1)
    # Insert new block in place
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
        '                    logger.warning(f"\U0001f6e1\ufe0f [V110.100] {symbol} {side} BLOCKED by Low Confidence ({unified_score:.1f}%, Slots: {free_slots})")\n'
        '                else:\n'
        '                    if free_slots >= 2:\n'
        '                        logger.info(f"\U0001f4aa [CAPTAIN-BOOST] {symbol} aprovado com {unified_score:.1f}% (Slots vazios: {free_slots})")\n'
    )
    content = content.replace(old, new, 1)
    print('OK Edit 1 applied!')
else:
    print('FAIL Edit 1: Pattern not found!')
    # Try to find with different emoji encoding
    idx = content.find('max_allowed_slots = 20 if is_ranging_mode else 40')
    if idx >= 0:
        print(f'Found base pattern at position {idx}')
        # Show surrounding text
        print(repr(content[idx:idx+800]))

with open('backend/services/agents/captain.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')
