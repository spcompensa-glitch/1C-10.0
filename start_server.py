#!/usr/bin/env python3
"""Helper to start local_server.py and capture errors."""
import subprocess, sys, os, time

server_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_server.py")
log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server_debug.log")

with open(log_path, "w") as log:
    proc = subprocess.Popen(
        [sys.executable, server_path],
        stdout=log,
        stderr=log,
    )
    print(f"Server starting with PID: {proc.pid}")
    
    # Wait and check
    for i in range(10):
        time.sleep(1)
        # Check if process still alive
        if proc.poll() is not None:
            print(f"Server exited early with code {proc.returncode}")
            break
        # Check if port is listening
        try:
            import urllib.request
            r = urllib.request.urlopen("http://localhost:8085/health", timeout=2)
            print(f"Health check OK after {i+1}s - server is LIVE!")
            break
        except:
            pass
    
    # Print last lines of log
    with open(log_path) as f:
        lines = f.readlines()
        print(f"Log has {len(lines)} lines")
        if lines:
            print("Last 15 lines:")
            for line in lines[-15:]:
                print(line.rstrip())
