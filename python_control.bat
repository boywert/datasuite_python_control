@echo off

:: ==========================================
:: 2. Directory Setup
:: ==========================================

if not exist "D:\jupyterlab" mkdir "D:\jupyterlab"
cd /d "D:\jupyterlab"

curl -L -o update_python.bat https://gitlab.vayulab.net/chaichalit.s/python_control/-/raw/main/update_python.bat?inline=false
call update_python.bat 
