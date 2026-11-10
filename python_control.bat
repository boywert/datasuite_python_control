@echo off

:: ==========================================
:: 2. Directory Setup
:: ==========================================

if not exist "D:\jupyterlab" mkdir "D:\jupyterlab"
cd /d "D:\jupyterlab"

curl -L -o update_python.bat https://raw.githubusercontent.com/boywert/datasuite_python_control/refs/heads/main/update_python.bat
call update_python.bat 
