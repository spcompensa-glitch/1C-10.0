#!/usr/bin/env python3
"""
Script para encontrar a linha exata 4034
"""
with open('frontend/cockpit.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f"Total de linhas: {len(lines)}")
print(f"Linha 4034: {lines[4033].strip()}")  # Índice 4033 para linha 4034

# Procurar try/catch nas proximidades
for i in range(4020, 4050):
    if i < len(lines):
        line = lines[i].strip()
        if 'catch' in line:
            print(f"Linha {i+1}: {line}")