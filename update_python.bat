@echo off

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
:: 1. Conda Environment Setup
:: ==========================================
echo.
echo Checking Conda environment...
call conda activate
conda env list | findstr /C:"python312 " >nul

if %errorlevel%==0 (
    echo [OK] Environment 'python312' found.
    call conda activate python312
) else (
    echo [ERROR] Environment 'python312' does not exist!
    echo Creating conda environment: conda create -n python312 python=3.12.4 -y
	conda create -n python312 python=3.12.4
)

call conda deactivate
call conda activate python312
echo [OK] Environment 'python312' activated.

:: ==========================================
:: 3. Git Logic (Clone vs Pull)
:: ==========================================


if exist "python_control" (
    echo [INFO] Repository folder found. Updating...
    cd python_control
    call git pull
) else (
    echo [INFO] Repository folder not found. Cloning...
    call git clone https://github.com/boywert/datasuite_python_control.git
    cd datasuite_python_control
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