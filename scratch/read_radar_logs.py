import os

def check_radar():
    log_path = "backend/backend_v110_173.log"
    if not os.path.exists(log_path):
        print(f"Log not found: {log_path}")
        return
        
    print(f"Scanning {log_path} for trading signals and radar logs...")
    terms = ["[RADAR]", "[SIGNAL]", "[TOCAIA]", "SignalGenerator", "CaptainAgent", "monitor_signals", "SCAN", "BLITZ"]
    
    lines_found = []
    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if any(term in line for term in terms):
                lines_found.append(line.strip())
                
    print(f"Total lines found: {len(lines_found)}")
    # Print the last 100 lines
    last_100 = lines_found[-100:]
    for line in last_100:
        print(line)

if __name__ == "__main__":
    check_radar()
