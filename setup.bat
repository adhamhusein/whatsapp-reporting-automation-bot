@echo off
SETLOCAL

echo.
echo ================================
echo Global Python Package Setup
echo ================================
echo.

REM -----------------------------
REM Check if Python is installed
REM -----------------------------
python --version >nul 2>&1
IF ERRORLEVEL 1 (
    echo Python is not installed or not added to PATH!
    pause
    exit /b 1
)
echo Python detected.

REM -----------------------------
REM Check pip installation
REM -----------------------------
echo.
echo [1/3] Checking pip...
python -m pip --version >nul 2>&1
IF ERRORLEVEL 1 (
    echo Pip not found. Installing pip...
    python -m ensurepip --quiet
    IF ERRORLEVEL 1 (
        echo Failed to install pip!
        pause
        exit /b 1
    )
    python -m pip install --quiet --upgrade pip
    IF ERRORLEVEL 1 (
        echo Failed to upgrade pip!
        pause
        exit /b 1
    )
    echo Pip installed successfully.
) ELSE (
    echo Pip is already installed.
)

REM -----------------------------
REM Install required packages
REM -----------------------------
IF EXIST "requirements.txt" (
    echo.
    echo [2/3] Installing/updating required packages...
    python -m pip install --upgrade -r requirements.txt
    IF ERRORLEVEL 1 (
        echo Failed to install some packages!
        pause
        exit /b 1
    )
    echo Packages installed/updated successfully.
) ELSE (
    echo No requirements.txt found. Skipping package installation.
)

echo.
echo [3/3] Setup complete. All packages are up to date.

REM -----------------------------
REM Wait 3 seconds before exit
REM -----------------------------
timeout /t 3 /nobreak >nul
exit /b 0
