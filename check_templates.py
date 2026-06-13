#!/usr/bin/env python3
"""
Script para verificar templates não fechados
"""
import re

def check_templates():
    """Verifica templates não fechados"""
    try:
        with open('frontend/cockpit.html', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Encontrar templates não fechados
        open_templates = content.count('${')
        close_templates = content.count('}')
        
        print(f"Templates abertos: {open_templates}")
        print(f"Templates fechados: {close_templates}")
        print(f"Diferença: {open_templates - close_templates}")
        
        # Procurar por templates não fechados
        template_pattern = r'\$\{[^}]*$'
        lines = content.split('\n')
        
        for i, line in enumerate(lines):
            if re.search(template_pattern, line):
                print(f"Template não fechado na linha {i+1}: {line.strip()}")
                
    except Exception as e:
        print(f"❌ Erro: {e}")

if __name__ == "__main__":
    check_templates()