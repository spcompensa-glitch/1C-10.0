$pythonPath = "C:\Users\spcom\AppData\Local\Programs\Python\Python313\python.exe"
$serverPath = "C:\Users\spcom\Desktop\1C-7.0\local_server.py"
$logPath = "C:\Users\spcom\Desktop\1C-7.0\server_output.log"

Start-Process -FilePath $pythonPath -ArgumentList $serverPath -WindowStyle Hidden -RedirectStandardOutput $logPath -RedirectStandardError $logPath
Write-Host "Server starting on port 8085..."
Start-Sleep -Seconds 3
$proc = Get-Process -Name python -ErrorAction SilentlyContinue | Select-Object -First 1
if ($proc) {
    Write-Host "Python process running: PID $($proc.Id)"
} else {
    Write-Host "ERROR: No Python process found"
    if (Test-Path $logPath) {
        Write-Host "Log contents:"
        Get-Content $logPath
    }
}
$port = netstat -ano | findstr "8085" | findstr "LISTENING"
if ($port) {
    Write-Host "Server is LISTENING on port 8085!"
} else {
    Write-Host "Server is NOT listening on port 8085 yet"
}
