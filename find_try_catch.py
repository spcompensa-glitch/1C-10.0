#!/usr/bin/env python3
"""
Script para encontrar try/catch problemáticos
"""
with open('frontend/cockpit.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Procurar por try/catch com problemas
for i, line in enumerate(lines):
    if 'catch(e)' in line or 'catch (e)' in line:
        # Verificar se há um try correspondente
        context = ''.join(lines[max(0, i-10):i+10])
        print(f"Linha {i+1}: {line.strip()}")
        print("Contexto:")
        for j in range(max(0, i-5), min(len(lines), i+5)):
            marker = ">>> " if j == i else "    "
            print(f"{marker}{j+1}: {lines[j].strip()}")
        print("-" * 50)