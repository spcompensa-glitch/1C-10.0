# -*- coding: utf-8 -*-
import os

def parse_log():
    log_path = r"C:\Users\spcom\.gemini\antigravity\brain\ea8facf1-9d68-4251-9739-817d358db708\.system_generated\tasks\task-1676.log"
    if not os.path.exists(log_path):
        print(f"❌ Log não encontrado no caminho: {log_path}")
        return
        
    print(f"📖 Lendo log em {log_path}...")
    
    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
        
    print(f"Total de {len(lines)} linhas lidas.")
    
    print("\n--- Linhas do SLOT-4 ou slot_operator_4 ---")
    count = 0
    for i, line in enumerate(lines):
        if "SLOT-4" in line or "slot_operator_4" in line or "Slot 4" in line:
            print(f"L{i+1}: {line.strip()}")
            count += 1
            if count > 150:
                print("... truncado ...")
                break

if __name__ == "__main__":
    parse_log()
