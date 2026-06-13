#!/usr/bin/env python3
"""
Script para encontrar try órfão
"""
with open('frontend/cockpit.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

try_positions = []
catch_positions = []

for i, line in enumerate(lines):
    if 'try {' in line:
        try_positions.append(i + 1)
    if '} catch(' in line or '} catch (' in line or '} catch(e)' in line or '} catch (e)' in line:
        catch_positions.append(i + 1)

# Encontrar try sem catch correspondente
orphan_tries = []
for try_pos in try_positions:
    has_catch = False
    for catch_pos in catch_positions:
        if catch_pos > try_pos:
            has_catch = True
            break
    if not has_catch:
        orphan_tries.append(try_pos)

print(f"Try órfãos encontrados: {orphan_tries}")

for try_pos in orphan_tries:
    print(f"\nContexto do try órfão na linha {try_pos}:")
    start_line = max(0, try_pos - 10)
    end_line = min(len(lines), try_pos + 10)
    
    for j in range(start_line, end_line):
        marker = ">>>" if j + 1 == try_pos else "   "
        print(f"{marker} {j+1}: {lines[j].strip()}")