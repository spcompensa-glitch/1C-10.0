#!/usr/bin/env python3
"""
FIX: ALPHA SHIELD strategy not generating trades in sandbox.
3 fixes:
1. MOLA: use actual bb_width from market_regime instead of hardcoded 3.5
2. MOLA: add logging when triggered
3. LRT: map to ALPHA SHIELD instead of falling through to VELOCITY FLOW
"""
import os

filepath = os.path.join(os.path.dirname(__file__), '..', 'services', 'signal_generator.py')

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

changes = 0

# FIX 1: Replace hardcoded bb_width=3.5 with actual bb_width from market_regime
old1 = 'squeeze_res = await self.detect_squeeze(symbol, bb_width=3.5)'
new1 = (
    '# [FIX-ALPHA-SHIELD] Usar bb_width real do regime do ativo em vez de 3.5 hardcoded\n'
    '                        asset_bb_width = market_regime.get(\'bb_width\', 5.0)\n'
    '                        squeeze_res = await self.detect_squeeze(symbol, bb_width=asset_bb_width)'
)
if old1 in content:
    content = content.replace(old1, new1, 1)
    changes += 1
    print(f'[OK] Fix 1 applied: MOLA bb_width now uses actual asset bb_width')
else:
    print(f'[SKIP] Fix 1: pattern not found (may already be applied)')

# FIX 2: Add logging after MOLA squeeze check
old2 = 'is_mola_play = squeeze_res.get("is_squeeze", False)'
new2 = (
    'is_mola_play = squeeze_res.get("is_squeeze", False)\n'
    '                        if is_mola_play:\n'
    '                            logger.info(f"🌊 [MOLA STRATEGY TRIGGERED] {symbol} BB Width={asset_bb_width:.2f} < 1.2")'
)
if old2 in content and 'MOLA STRATEGY TRIGGERED' not in content:
    content = content.replace(old2, new2, 1)
    changes += 1
    print(f'[OK] Fix 2 applied: MOLA logging added')
else:
    print(f'[SKIP] Fix 2: pattern not found or already applied')

# FIX 3: Add LRT to ALPHA SHIELD mapping
old3 = 'if raw_class in ("DVAP", "MOLA", "FAS"):'
new3 = (
    '# [FIX-ALPHA-SHIELD] LRT agora classificado como ALPHA SHIELD (antes caia no else como VELOCITY FLOW)\n'
    '                    if raw_class in ("DVAP", "MOLA", "FAS", "LRT"):'
)
if old3 in content:
    content = content.replace(old3, new3, 1)
    changes += 1
    print(f'[OK] Fix 3 applied: LRT mapped to ALPHA SHIELD')
else:
    print(f'[SKIP] Fix 3: pattern not found (may already be applied)')

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print(f'\nTotal changes applied: {changes}/3')
print('Done.')
