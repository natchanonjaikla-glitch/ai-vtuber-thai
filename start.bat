@echo off
REM เปิด AI VTuber ด้วย Python ใน .venv เสมอ — ดับเบิลคลิกไฟล์นี้ได้เลย
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo [!] ไม่พบ .venv - สร้างก่อนด้วย:
    echo     python -m venv .venv
    echo     .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)
".venv\Scripts\python.exe" run.py %*
pause
