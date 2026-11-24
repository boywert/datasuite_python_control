@echo off

setlocal enabledelayedexpansion

:: ==========================================
:: 1. Configuration
:: ==========================================
set "ENV_NAME=python314"
set "TARGET_MINOR=3.14"
set "TARGET_PIP=26.2.2"
set "REPO_DIR=datasuite_python_control"
set "REPO_URL=https://github.com/boywert/datasuite_python_control.git"

:: ==========================================
:: 2. Directory Setup
:: ==========================================

if not exist "D:\jupyterlab" mkdir "D:\jupyterlab"
cd /d "D:\jupyterlab"


:: ==========================================
:: 0. Check for Git Installation
:: ==========================================
echo Checking if Git is installed...
git --version >nul 2>&1

if %errorlevel% neq 0 (
    echo [WARNING] Git is not found on this system.
    echo Installing Git via Winget...
    
    winget install --id Git.Git -e --source winget >nul 2>&1
	if %errorlevel% neq 0 (
		curl -L -o git_install.exe https://github.com/git-for-windows/git/releases/download/v2.52.0.windows.1/Git-2.52.0-64-bit.exe
		.\git_install.exe /SILENT
		echo [IMPORTANT] Git has been installed. 
		echo Please CLOSE this window and run the script again to refresh your system PATH.
		pause
		exit
	) else (
		echo.
		echo [IMPORTANT] Git has been installed. 
		echo Please CLOSE this window and run the script again to refresh your system PATH.
		pause
		exit
	)
) else (
    echo [OK] Git is installed.
)


:: ==========================================
:: 2. Conda Environment Check & Smart Patch Update
:: ==========================================
echo Checking Conda environment '%ENV_NAME%'...
call conda activate base

set "ENV_FOUND=0"
for /f "tokens=1" %%e in ('conda env list ^| findstr /V "^#"') do (
    if "%%e"=="%ENV_NAME%" set "ENV_FOUND=1"
)

if "!ENV_FOUND!"=="1" (
    echo [OK] Environment '%ENV_NAME%' found.

    set "CUR_PY="
    for /f "tokens=2 delims= " %%v in ('conda run -n "%ENV_NAME%" python --version 2^>nul') do (
        set "CUR_PY=%%v"
    )

	set "LATEST_PY="
	for /f "usebackq delims=" %%v in (`powershell -NoProfile -Command "$out = conda search 'python=%TARGET_MINOR%.*' 2>$null; $vers = [regex]::Matches($out, '\b\d+\.\d+\.\d+\b') | ForEach-Object { [version]$_.Value } | Sort-Object -Descending | Select-Object -First 1; if ($vers) { $vers.ToString() }"`) do (
		set "LATEST_PY=%%v"
	)

    if defined CUR_PY if defined LATEST_PY (
        echo [INFO] Installed: !CUR_PY! ^| Newest available: !LATEST_PY!
        if "!CUR_PY!"=="!LATEST_PY!" (
            echo [OK] Already on the newest %TARGET_MINOR%.x patch. Skipping Python update.
        ) else (
            echo [INFO] Updating Python in '%ENV_NAME%' from !CUR_PY! to !LATEST_PY!...
            call conda install -n "%ENV_NAME%" "python=!LATEST_PY!" -y
        )
    ) else (
        echo [INFO] Updating Python in '%ENV_NAME%' to newest %TARGET_MINOR%.x patch...
        call conda install -n "%ENV_NAME%" "python=%TARGET_MINOR%.*" -y
    )
) else (
    echo [INFO] Environment '%ENV_NAME%' does not exist.
    echo Creating conda environment with newest %TARGET_MINOR%.x patch...
    call conda create -n "%ENV_NAME%" "python=%TARGET_MINOR%.*" -y
)

call conda deactivate
call conda activate "%ENV_NAME%"
echo [OK] Environment '%ENV_NAME%' activated.
python --version


:: --- Check & Upgrade pip if < TARGET_PIP ---
set "CUR_PIP="
for /f "tokens=2" %%p in ('python -m pip --version 2^>nul') do (
    set "CUR_PIP=%%p"
)

if defined CUR_PIP (
    echo [INFO] Installed pip: !CUR_PIP! ^(Minimum target: %TARGET_PIP%^)
    python -c "import sys; from packaging.version import Version; sys.exit(0 if Version(sys.argv[1]) >= Version(sys.argv[2]) else 1)" "!CUR_PIP!" "%TARGET_PIP%" 2>nul
    if errorlevel 1 (
        python -c "import sys; v1=[int(x) for x in sys.argv[1].split('.')[:3]]; v2=[int(x) for x in sys.argv[2].split('.')[:3]]; sys.exit(0 if v1 >= v2 else 1)" "!CUR_PIP!" "%TARGET_PIP%"
    )
    if errorlevel 1 (
        echo [INFO] Upgrading pip from !CUR_PIP! to ^>=%TARGET_PIP%...
        python -m pip install --upgrade "pip>=%TARGET_PIP%"
    ) else (
        echo [OK] pip !CUR_PIP! already meets ^>=%TARGET_PIP%. Skipping pip upgrade.
    )
) else (
    echo [WARN] pip not detected in '%ENV_NAME%'. Installing pip^>=%TARGET_PIP%...
    conda install -n "%ENV_NAME%" "pip>=%TARGET_PIP%" -y
)

:: ==========================================
:: 3. Git Logic (Clone vs Pull)
:: ==========================================
if exist "%REPO_DIR%" (
    echo [INFO] Repository folder found. Updating...
    cd /d "%REPO_DIR%"
    call git pull
) else (
    echo [INFO] Repository folder not found. Cloning...
    call git clone "%REPO_URL%"
    cd /d "%REPO_DIR%"
)
:: ==========================================
:: 4. Install Requirements
:: ==========================================


echo Current Directory: %CD%

if exist "requirements.txt" (
    echo Installing dependencies...
    call pip install -r requirements.txt 
) else (
    echo [WARNING] requirements.txt not found in %CD%
)



pause