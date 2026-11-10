@echo off

call conda activate python312
echo [OK] Environment 'python312' activated.

python tunnel.py

pause