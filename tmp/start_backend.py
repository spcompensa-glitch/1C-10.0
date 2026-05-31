import subprocess, sys, os, time

log_path = 'backend/backend_v110_176.log'
log_file = open(log_path, 'w', buffering=1)

python_path = 'C:/Users/spcom/AppData/Local/Programs/Python/Python313/python.exe'
project_dir = os.path.abspath('.')

p = subprocess.Popen(
    [python_path, 'backend/main.py'],
    stdout=log_file,
    stderr=subprocess.STDOUT,
    cwd=project_dir
)
print(f'Backend iniciado com PID: {p.pid}')
print(f'Python: {python_path}')
print(f'Log: {log_path}')
