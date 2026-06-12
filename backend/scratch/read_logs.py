import sys
import os

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Let's find the latest backend log file by sorting the log files
log_files = [f for f in os.listdir('backend') if f.startswith('backend_v110_') and f.endswith('.log')]
if not log_files:
    print("No backend log files found in backend/")
    sys.exit(0)

# Sort by modification time
log_files.sort(key=lambda x: os.path.getmtime(os.path.join('backend', x)), reverse=True)
latest_log = os.path.join('backend', log_files[0])

print(f"Reading latest log file: {latest_log} ({os.path.getsize(latest_log)} bytes)\n")

with open(latest_log, 'rb') as f:
    f.seek(0, 2)
    size = f.tell()
    # Read last 30,000 bytes
    f.seek(max(0, size - 30000))
    content = f.read().decode('utf-8', 'ignore')
    print(content)
