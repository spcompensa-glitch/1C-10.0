$dir = "C:\Users\spcom\Desktop\1C-7.0"
$env:PYTHONPATH = "$dir\backend"
$env:OKX_EXECUTION_MODE = "PAPER"
$log = "$dir\server_stdout.log"
$err = "$dir\server_stderr.log"
Set-Location $dir
python -u backend\main.py *>>"$log" 2>>"$err"