import re

file_path = r"c:\Users\spcom\Desktop\1C-7.0\frontend\cockpit.html"

def main():
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
        
    lines = content.splitlines()
    print(f"Total de linhas no cockpit.html: {len(lines)}")
    
    # Procurar por excecoes ou onde "Inline Babel script:2697" possa ser relevante
    # Linha 2697 no script inline do cockpit
    # Vamos imprimir da linha 2680 a 2710
    print("=== TRECHO DA LINHA 2680 a 2710 ===")
    for idx in range(2670, 2720):
        if idx < len(lines):
            print(f"{idx+1}: {lines[idx]}")

if __name__ == "__main__":
    main()
