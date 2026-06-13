#!/usr/bin/env python3
"""
Script para verificar a estrutura do levels.forEach no HTML
"""
import re

def check_levels_foreach():
    """Verifica a estrutura do levels.forEach"""
    try:
        with open('frontend/cockpit.html', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Encontrar todas as ocorrências de levels.forEach
        levels_foreach_pattern = r'levels\.forEach\(lvl => \{([^}]*)\}\)'
        matches = re.findall(levels_foreach_pattern, content, re.DOTALL)
        
        print(f"🔍 Encontradas {len(matches)} ocorrências de levels.forEach")
        
        for i, match in enumerate(matches):
            print(f"\n📍 Ocorrência {i+1}:")
            print(f"   Conteúdo: {match[:200]}...")
            
            # Verificar se tem return correto
            if 'return;' in match:
                print("   ✅ Tem return;")
            else:
                print("   ⚠️ Não tem return;")
                
            # Verificar se tem appendChild correto
            if 'appendChild' in match:
                print("   ✅ Tem appendChild")
            else:
                print("   ⚠️ Não tem appendChild")
        
        # Verificar se há problemas de fechamento de chaves
        brace_count = content.count('{') - content.count('}')
        if brace_count != 0:
            print(f"⚠️ Desbalanceamento de chaves: {brace_count} chaves não fechadas")
        else:
            print("✅ Chaves balanceadas")
            
    except Exception as e:
        print(f"❌ Erro: {e}")

if __name__ == "__main__":
    check_levels_foreach()