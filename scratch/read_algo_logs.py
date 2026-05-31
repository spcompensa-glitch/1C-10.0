import os

log_path = r"C:\Users\spcom\.gemini\antigravity\brain\ea8facf1-9d68-4251-9739-817d358db708\.system_generated\tasks\task-1036.log"

def main():
    if not os.path.exists(log_path):
        print("Log não encontrado.")
        return
        
    print("=== PROCURANDO ATUALIZACOES DE SLOTS NOS LOGS ===")
    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
        
    found = 0
    # Procurar ocorrências de SlotOperator ou de Banca Update nas últimas 1000 linhas
    start_idx = max(0, len(lines) - 1000)
    for idx in range(start_idx, len(lines)):
        line = lines[idx]
        if "SLOTOPERATOR" in line.upper() or "BANCA UPDATE" in line.upper():
            print(f"Linha {idx+1}: {line.strip()}")
            found += 1
            
    print(f"Total encontrado: {found} ocorrências.")

if __name__ == "__main__":
    main()
