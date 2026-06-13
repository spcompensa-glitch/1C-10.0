#!/usr/bin/env python3
"""
Script para contar chaves no HTML
"""
with open('frontend/cockpit.html', 'r', encoding='utf-8') as f:
    content = f.read()

open_braces = content.count('{')
close_braces = content.count('}')

print(f"Chaves abertas: {open_braces}")
print(f"Chaves fechadas: {close_braces}")
print(f"Diferença: {open_braces - close_braces}")

if open_braces == close_braces:
    print("✅ Chaves balanceadas!")
else:
    print("❌ Chaves desbalanceadas!")