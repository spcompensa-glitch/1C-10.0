# -*- coding: utf-8 -*-
"""Apply V111.3 TREND_FOCUS UI changes to cockpit.html"""

with open('frontend/cockpit.html', 'r', encoding='utf-8') as f:
    content = f.read()

changes = 0

# Edit 1: Regime label at line 5966-5968 - change labels
old = (
    '                                            <span className="text-gray-500 uppercase tracking-wider">Regime:</span>\n'
    '                                            <span className={isRangingMode ? "text-cyan-400" : "text-violet-400"}>\n'
    '                                                {isRangingMode ? "LATERAL (20 PARES)" : "TEND\u00caNCIA (40 PARES)"}'
)
new = (
    '                                            <span className="text-gray-500 uppercase tracking-wider">Regime:</span>\n'
    '                                            <span className={isRangingMode ? "text-amber-400" : "text-violet-400"}>\n'
    '                                                {isRangingMode ? "LATERAL (SISTEMA PAUSADO)" : "TEND\u00caNCIA (20/40 PARES)"}'
)
if old in content:
    content = content.replace(old, new, 1)
    changes += 1
    print('OK UI Edit 1: Regime labels')
else:
    print('FAIL UI Edit 1: Regime labels')

# Edit 2: PositionsTable modeLabel at line 3694 - remove DECOR_HUNTER
old = (
    "            const modeLabel = isRangingMode ? 'DECOR_HUNTER' : 'ELITE_40_MATRIX';"
)
new = (
    "            const modeLabel = isRangingMode ? 'PAUSADO' : 'ELITE_40_MATRIX';"
)
if old in content:
    content = content.replace(old, new, 1)
    changes += 1
    print('OK UI Edit 2: Mode label')
else:
    print('FAIL UI Edit 2: Mode label')

# Edit 3: BancaWealthSection Current Session display
old = "Regime:\n                    {isRangingMode ? \"LATERAL (20 PARES)\" : \"TEND\u00caNCIA (40 PARES)\"}"
new = "Regime:\n                    {isRangingMode ? \"LATERAL (SISTEMA PAUSADO)\" : \"TEND\u00caNCIA (20/40 PARES)\"}"
if old in content:
    content = content.replace(old, new, 1)
    changes += 1
    print('OK UI Edit 3: BancaWealthSection label')
else:
    print('FAIL UI Edit 3: BancaWealthSection label')

# Edit 4: maxSlots in PositionsTable
old = (
    "            const maxSlots = isRangingMode ? 20 : 40;"
)
new = (
    "            const maxSlots = isRangingMode ? 0 : 20;"
)
if old in content:
    content = content.replace(old, new, 1)
    changes += 1
    print('OK UI Edit 4: maxSlots PositionsTable')
else:
    print('FAIL UI Edit 4: maxSlots PositionsTable')

# Edit 5: maxSlots at line 6515
# There are two instances, let me find them
count_6515 = content.count('const maxSlots = isRangingMode ? 20 : 40;')
if count_6515 >= 2:
    # Replace only the second one (line 6515 area)
    old = 'const maxSlots = isRangingMode ? 20 : 40;'
    new = 'const maxSlots = isRangingMode ? 0 : 20;'
    content = content.replace(old, new, 2)  # replace all instances
    changes += 1
    print(f'OK UI Edit 5: maxSlots ({count_6515} instances)')
elif count_6515 == 1:
    old = 'const maxSlots = isRangingMode ? 20 : 40;'
    new = 'const maxSlots = isRangingMode ? 0 : 20;'
    content = content.replace(old, new, 1)
    changes += 1
    print(f'OK UI Edit 5: maxSlots (1 instance)')
else:
    print(f'FAIL UI Edit 5: maxSlots not found ({count_6515})')

with open('frontend/cockpit.html', 'w', encoding='utf-8') as f:
    f.write(content)
print(f'\nTotal UI changes: {changes}')
