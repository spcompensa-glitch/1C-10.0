# -*- coding: utf-8 -*-
"""Apply V111.3 TREND_FOCUS changes to bankroll.py"""

with open('backend/services/bankroll.py', 'r', encoding='utf-8') as f:
    content = f.read()

changes = 0

# Edit: can_open_new_slot() - replace is_ranging_mode block
old = (
    "            elif is_ranging_mode:\n"
    "                max_total_slots = self.max_slots_lateral   # 20 pares \u2014 DECOR_HUNTER\n"
    "                max_at_risk_slots = self.max_slots_lateral\n"
    "                logger.info(f\"\U0001f6e1\ufe0f [V111.0] DECOR_HUNTER Mode: Max Slots={max_total_slots} | Margin=$2.00/par | LiveEquity=${balance:.2f}\")\n"
    "            else:\n"
    "                max_total_slots = self.max_slots_trending  # 40 pares \u2014 ELITE_40_MATRIX\n"
    "                max_at_risk_slots = self.max_slots_trending\n"
    "                logger.info(f\"\U0001f6e1\ufe0f [V111.0] ELITE_40_MATRIX Mode: Max Slots={max_total_slots} | Margin=$1.00/par | LiveEquity=${balance:.2f}\")"
)
new = (
    "            elif is_ranging_mode:\n"
    "                # [V111.3 TREND_FOCUS] Mercado LATERAL - nao abrir nada\n"
    "                logger.info(f\"[V111.3 TREND_FOCUS] Mercado LATERAL (ADX < 25). Sistema pausado. LiveEquity=${balance:.2f}\")\n"
    "                return None\n"
    "            else:\n"
    "                max_total_slots = 20  # [V111.3] Hard limit de 20 slots em tendencia\n"
    "                max_at_risk_slots = 20\n"
    "                logger.info(f\"\U0001f6e1\ufe0f [V111.3] ELITE_40_MATRIX Mode: Max Slots={max_total_slots} | 40% Banca | LiveEquity=${balance:.2f}\")"
)

if old in content:
    content = content.replace(old, new, 1)
    changes += 1
    print('OK bankroll Edit: can_open_new_slot()')
else:
    print('FAIL bankroll Edit: can_open_new_slot()')
    # Try with -- instead of em dash
    alt_old = old.replace('\u2014', '--')
    if alt_old in content:
        content = content.replace(alt_old, new, 1)
        changes += 1
        print('OK bankroll Edit (alt): can_open_new_slot()')
    else:
        # Find the pattern location
        idx = content.find('elif is_ranging_mode:')
        if idx >= 0:
            # Show the 5 lines after
            print(f'Found at {idx}')
            end = min(len(content), idx + 400)
            print(repr(content[idx:end]))

with open('backend/services/bankroll.py', 'w', encoding='utf-8') as f:
    f.write(content)
print(f'Total bankroll changes: {changes}')
