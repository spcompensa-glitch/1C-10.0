import os

def read_last_lines():
    log_path = "backend/backend_v110_173.log"
    if not os.path.exists(log_path):
        print(f"Log not found: {log_path}")
        return
    
    print(f"Reading last 200 lines of {log_path}...")
    with open(log_path, "rb") as f:
        # Seek to the end minus a guess at the length of 200 lines
        try:
            f.seek(-40000, os.SEEK_END)
        except IOError:
            # File is smaller than 40KB
            pass
        
        lines = f.readlines()
        last_200 = lines[-200:]
        for line in last_200:
            try:
                print(line.decode("utf-8").strip())
            except Exception:
                print(line.strip())

if __name__ == "__main__":
    read_last_lines()
