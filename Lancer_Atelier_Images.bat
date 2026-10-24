@echo off
cd /d "%~dp0"
"%~dp0python_embeded\python.exe" -s "%~dp0atelier_images\server.py"
if errorlevel 1 pause
