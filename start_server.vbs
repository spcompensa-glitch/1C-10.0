Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\spcom\Desktop\1C-7.0"
cmd = "cmd /c ""set PYTHONPATH=C:\Users\spcom\Desktop\1C-7.0\backend && set OKX_EXECUTION_MODE=PAPER && python -u backend\main.py >> server_stdout.log 2>> server_stderr.log"""
WshShell.Run cmd, 0, False