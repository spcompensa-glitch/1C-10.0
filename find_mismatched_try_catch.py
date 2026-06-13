#!/usr/bin/env python3
"""
Script para encontrar try/catch desalinhados
"""
with open('frontend/cockpit.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Encontrar todos os try e catch
try_positions = []
catch_positions = []

lines = content.split('\n')
for i, line in enumerate(lines):
    if 'try {' in line:
        try_positions.append(i + 1)  # +1 para contagem de linha humana
    if '} catch(' in line or '} catch (' in line or '} catch(e)' in line or '} catch (e)' in line:
        catch_positions.append(i + 1)

print(f"Total de try: {len(try_positions)}")
print(f"Total de catch: {len(catch_positions)}")
print(f"Try positions: {try_positions}")
print(f"Catch positions: {catch_positions}")

# Verificar se há diferença
if len(try_positions) != len(catch_positions):
    print(f"⚠️ Diferença: {len(try_positions)} try vs {len(catch_positions)} catch")
    
    # Procurar catch sem try correspondente
    for catch_pos in catch_positions:
        found_corresponding_try = False
        for try_pos in try_positions:
            if try_pos < catch_pos:
                found_corresponding_try = True
                break
        if not found_corresponding_try:
            print(f"⚠️ Catch na linha {catch_pos} pode não ter try correspondente")
            
            # Mostrar contexto
            start_line = max(0, catch_pos - 5)
            end_line = min(len(lines), catch_pos + 5)
            print(f"Contexto da linha {catch_pos}:")
            for j in range(start_line, end_line):
                marker = ">>>" if j + 1 == catch_pos else "   "
                print(f"{marker} {j+1}: {lines[j].strip()}")
            print("-" * 50)