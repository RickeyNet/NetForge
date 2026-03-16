@echo off
echo === Building NetForge ===
echo.

:: Activate virtual environment
call venv\Scripts\activate.bat

:: Install build dependencies if needed
pip install pyinstaller jinja2 --quiet

:: Run PyInstaller with the spec file
pyinstaller NetForge.spec --noconfirm --clean

echo.
if exist "dist\NetForge.exe" (
    echo BUILD SUCCEEDED
    echo Output: dist\NetForge.exe
) else if exist "dist\NetForge\NetForge.exe" (
    echo BUILD SUCCEEDED
    echo Output: dist\NetForge\NetForge.exe
) else (
    echo BUILD FAILED — check output above for errors
)
pause
