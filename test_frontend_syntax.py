#!/usr/bin/env python3
"""
Script para testar a sintaxe básica do frontend HTML
"""
import re
import json

def test_html_syntax():
    """Testa se a sintaxe HTML está correta"""
    try:
        with open('frontend/cockpit.html', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Verificar se todos os React.useEffect foram substituídos
        react_effects = content.count('React.useEffect')
        react_states = content.count('React.useState')
        react_refs = content.count('React.useRef')
        react_memos = content.count('React.useMemo')
        react_fragments = content.count('React.Fragment')
        
        print("🔍 Testando sintaxe do frontend...")
        print(f"   - React.useEffect restantes: {react_effects}")
        print(f"   - React.useState restantes: {react_states}")
        print(f"   - React.useRef restantes: {react_refs}")
        print(f"   - React.useMemo restantes: {react_memos}")
        print(f"   - React.Fragment restantes: {react_fragments}")
        
        if react_effects == 0 and react_states == 0 and react_refs == 0 and react_memos == 0 and react_fragments == 0:
            print("✅ Todos os React Hooks foram corrigidos!")
        else:
            print("❌ Ainda há React Hooks não corrigidos")
            
        # Verificar se o HYPER 1200% está correto
        if 'HYPER (1200%)' in content:
            print("✅ HYPER (1200%) encontrado no HTML")
            
        # Verificar se o problema de sintaxe foi resolvido
        # Procurar por padrões que possam causar erro de sintaxe
        error_patterns = [
            r'levels\.forEach.*lvl.*=>.*\{[^}]*\}\s*\}',  # Verificar se forEach está correto
        ]
        
        errors_found = 0
        for pattern in error_patterns:
            matches = re.findall(pattern, content, re.DOTALL)
            if matches:
                print(f"⚠️ Padrão suspeito encontrado: {pattern}")
                errors_found += 1
        
        if errors_found == 0:
            print("✅ Nenhum padrão suspeito de sintaxe encontrado")
            
        print("🎉 Teste de sintaxe concluído!")
        
    except Exception as e:
        print(f"❌ Erro ao testar sintaxe: {e}")

if __name__ == "__main__":
    test_html_syntax()