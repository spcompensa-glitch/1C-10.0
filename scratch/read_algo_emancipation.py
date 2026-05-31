import os

log_path = r"C:\Users\spcom\.gemini\antigravity\brain\ea8facf1-9d68-4251-9739-817d358db708\.system_generated\tasks\task-1036.log"

def main():
    if not os.path.exists(log_path):
        print("Log não encontrado.")
        return
        
    print("=== DETALHES DE EMANCIPACAO DE ALGO ===")
    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
        
    # Imprimir linhas de 1940 a 2090
    for idx in range(1940, 2090):
        if idx < len(lines):
            print(f"Linha {idx+1}: {lines[idx].strip()}")

if __name__ == "__main__":
    main()
