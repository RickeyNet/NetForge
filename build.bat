@echo off
echo === Building NetForge ===
echo.

:: Activate virtual environment
call venv\Scripts\activate.bat

:: Install build dependencies if needed
pip install pyinstaller jinja2 --quiet

:: Extract version from NetForge.py
for /f "tokens=2 delims==" %%v in ('findstr /R "^VERSION" NetForge.py') do (
    set "VER=%%~v"
)
set "VER=%VER: =%"
set "VER=%VER:"=%"
echo Version: %VER%

:: Run PyInstaller with the spec file
pyinstaller NetForge.spec --noconfirm --clean

echo.
if exist "dist\NetForge.exe" (
    move "dist\NetForge.exe" "dist\NetForge_v%VER%.exe" >nul
    echo BUILD SUCCEEDED
    echo Output: dist\NetForge_v%VER%.exe
) else if exist "dist\NetForge\NetForge.exe" (
    move "dist\NetForge\NetForge.exe" "dist\NetForge\NetForge_v%VER%.exe" >nul
    echo BUILD SUCCEEDED
    echo Output: dist\NetForge\NetForge_v%VER%.exe
) else (
    echo BUILD FAILED — check output above for errors
)
pause
