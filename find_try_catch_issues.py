#!/usr/bin/env python3

def find_try_catch_issues():
    try:
        with open('frontend/cockpit.html', 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.split('\n')
        
        # Encontrar todos os try statements
        try_positions = []
        for i, line in enumerate(lines):
            if 'try {' in line:
                try_positions.append(i + 1)  # +1 para linha humana
        
        # Encontrar todos os catch statements
        catch_positions = []
        for i, line in enumerate(lines):
            if 'catch (' in line:
                catch_positions.append(i + 1)
        
        # Encontrar todos os finally statements
        finally_positions = []
        for i, line in enumerate(lines):
            if 'finally {' in line:
                finally_positions.append(i + 1)
        
        print(f'Total try statements: {len(try_positions)}')
        print(f'Total catch statements: {len(catch_positions)}')
        print(f'Total finally statements: {len(finally_positions)}')
        
        print('\nTry statements encontrados:')
        for pos in try_positions:
            print(f'Linha {pos}: {lines[pos-1].strip()}')
            # Verificar se tem catch/finally nos próximos 20 linhas
            found_catch = False
            for j in range(pos, min(pos + 20, len(lines))):
                if 'catch (' in lines[j] or 'finally {' in lines[j]:
                    found_catch = True
                    print(f'  -> Encontrado catch/finally na linha {j+1}')
                    break
            
            if not found_catch:
                print(f'  -> NENHUM CATCH/FINALLY ENCONTRADO!')
        
    except Exception as e:
        print(f'Erro: {e}')

if __name__ == '__main__':
    find_try_catch_issues()