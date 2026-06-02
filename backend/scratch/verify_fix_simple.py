import os

def verify():
    file_path = r'services/agents/captain.py'
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    checks = [
        ('Capitão ignorando ANTI-TRAP', "ANTI-TRAP Bypass"),
        ('Ignorando Risco Macro Alto', "Macro Risk Bypass"),
        ('Ignorando Sentimento de Varejo', "Sentiment Bypass"),
        ('Ignorando Divergência de Baleias', "Whale Divergence Bypass"),
        ('Vision AI OFFLINE', "Vision Offline Bypass")
    ]
    
    all_ok = True
    for phrase, label in checks:
        if phrase in content:
            # Check if it's still inside an 'if okx_rest_service.execution_mode == "PAPER":'
            # (Note: Some phrases like 'Vision AI OFFLINE' might exist in logs but we removed the conditional)
            # A better check is to see if 'execution_mode == "PAPER"' exists near them.
            print(f"❌ {label} potentially still exists.")
            all_ok = False
        else:
            print(f"✅ {label} removed.")
            
    if all_ok:
        print("\n🎉 ALL BYPASSES REMOVED SUCCESSFULLY!")

if __name__ == "__main__":
    verify()
