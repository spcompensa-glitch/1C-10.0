@echo off
cd /d "C:\Users\spcom\Desktop\1C-7.0"
start /B /MIN "" "C:\Users\spcom\AppData\Local\Programs\Python\Python313\python.exe" local_server.py
echo Server starting on port 8085...
timeout /t 3 /nobreak > nul
netstat -ano | findstr ":8085"
echo Done.
