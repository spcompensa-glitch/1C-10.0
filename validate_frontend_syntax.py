#!/usr/bin/env python3
"""
Script para validar a sintaxe do frontend
"""
import re
import json

def validate_frontend():
    """Valida a sintaxe do frontend"""
    try:
        with open('frontend/cockpit.html', 'r', encoding='utf-8') as f:
            content = f.read()
        
        print("🔍 Validação da sintaxe do frontend...")
        
        # 1. Verificar React Hooks
        react_hooks = ['useState', 'useEffect', 'useRef', 'useMemo']
        for hook in react_hooks:
            count = content.count(f'{hook}(')
            print(f"   - {hook}: {count} ocorrências")
        
        # 2. Verificar templates não fechados
        open_templates = content.count('${')
        close_templates = content.count('}')
        print(f"   - Templates abertos: {open_templates}")
        print(f"   - Templates fechados: {close_templates}")
        print(f"   - Diferença: {open_templates - close_templates}")
        
        # 3. Verificar se HYPER 1200% está correto
        if 'HYPER (1200%)' in content:
            print("   ✅ HYPER (1200%) encontrado")
        else:
            print("   ❌ HYPER (1200%) não encontrado")
        
        # 4. Verificar chaves balanceadas
        open_braces = content.count('{')
        close_braces = content.count('}')
        print(f"   - Chaves abertas: {open_braces}")
        print(f"   - Chaves fechadas: {close_braces}")
        print(f"   - Diferença: {open_braces - close_braces}")
        
        # 5. Verificar se há scripts Babel
        babel_scripts = content.count('type="text/babel"')
        print(f"   - Scripts Babel: {babel_scripts}")
        
        # 6. Verificar se há problemas com strings não fechadas
        quote_issues = 0
        for char in ['"', "'"]:
            open_quotes = content.count(char)
            if open_quotes % 2 != 0:
                quote_issues += 1
                print(f"   ⚠️ Aspas {char} não balanceadas: {open_quotes}")
        
        # 7. Resumo
        if open_braces == close_braces and open_templates == close_templates and quote_issues == 0:
            print("   ✅ Sintaxe parecia correta!")
        else:
            print("   ❌ Possíveis problemas de sintaxe detectados")
            
        print("🎉 Validação concluída!")
        
    except Exception as e:
        print(f"❌ Erro: {e}")

if __name__ == "__main__":
    validate_frontend()