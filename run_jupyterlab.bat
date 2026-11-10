@echo off

:: ==========================================
:: 2. Directory Setup
:: ==========================================

if not exist "D:\jupyterlab" mkdir "D:\jupyterlab"
cd /d "D:\jupyterlab"

call conda activate python312
jupyter lab