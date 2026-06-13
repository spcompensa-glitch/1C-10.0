#!/usr/bin/env python3
"""
Script para encontrar funções não fechadas
"""
import re

def find_unclosed_functions():
    """Encontra funções que podem não estar fechadas corretamente"""
    try:
        with open('frontend/cockpit.html', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Encontrar padrões de funções
        function_patterns = [
            r'const \w+.*=.*\([^)]*\).*=>.*\{([^}]*)\}$',
            r'function \w+.*\([^)]*\).*\{([^}]*)\}$',
            r'\w+.*=.*function.*\{([^}]*)\}$',
        ]
        
        for pattern in function_patterns:
            matches = re.findall(pattern, content, re.MULTILINE | re.DOTALL)
            print(f"Padrão {pattern}: {len(matches)} matches")
            
        # Verificar se há funções muito grandes que podem não estar fechadas
        lines = content.split('\n')
        in_function = False
        function_start = 0
        brace_count = 0
        
        for i, line in enumerate(lines):
            if re.search(r'const \w+.*=.*=>|function \w+|.*=.*function.*\{', line):
                if brace_count == 0:
                    in_function = True
                    function_start = i
                    brace_count = line.count('{') - line.count('}')
            
            if in_function:
                brace_count += line.count('{') - line.count('}')
                
                if brace_count == 0 and i > function_start + 5:  # Função tem mais de 5 linhas
                    function_content = '\n'.join(lines[function_start:i+1])
                    if len(function_content) > 100:  # Funções grandes
                        print(f"Função grande encontrada (linha {function_start}-{i}):")
                        print(f"  {function_content[:100]}...")
        
        # Verificar se há templates não fechados
        template_count = content.count('${') - content.count('}')
        if template_count != 0:
            print(f"⚠️ Templates não fechados: {template_count}")
        
    except Exception as e:
        print(f"❌ Erro: {e}")

if __name__ == "__main__":
    find_unclosed_functions()