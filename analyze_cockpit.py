#!/usr/bin/env python3

def analyze_cockpit():
    try:
        with open('frontend/cockpit.html', 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        open_braces = 0
        close_braces = 0
        try_stack = []
        problems = []
        
        for i, line in enumerate(lines):
            open_count = line.count('{')
            close_count = line.count('}')
            open_braces += open_count
            close_braces += close_count
            
            if 'try {' in line:
                try_stack.append(i + 1)  # +1 para linha humana
            
            elif 'catch (' in line:
                if try_stack:
                    try_stack.pop()
                else:
                    problems.append(f'Linha {i+1}: Catch sem try correspondente')
            
            elif 'finally {' in line:
                if try_stack:
                    try_stack.pop()
                else:
                    problems.append(f'Linha {i+1}: Finally sem try correspondente')
        
        # Verificar try statements não fechados
        for line_num in try_stack:
            problems.append(f'Linha {line_num}: Try não fechado')
        
        print(f'Total de chaves abertas: {open_braces}')
        print(f'Total de chaves fechadas: {close_braces}')
        print(f'Diferença: {open_braces - close_braces}')
        
        if problems:
            print('\nProblemas encontrados:')
            for problem in problems:
                print(problem)
        else:
            print('\nNenhum problema encontrado')
            
    except Exception as e:
        print(f'Erro: {e}')

if __name__ == '__main__':
    analyze_cockpit()