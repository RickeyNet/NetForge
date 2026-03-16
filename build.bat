@echo off
echo === Building NetForge ===
echo.

:: Install build dependencies if needed
pip install pyinstaller jinja2 --quiet

:: Run PyInstaller with the spec file
pyinstaller NetForge.spec --noconfirm --clean

echo.
if exist "dist\NetForge\NetForge.exe" (
    echo BUILD SUCCEEDED
    echo Output: dist\NetForge\
    echo Run:    dist\NetForge\NetForge.exe
) else (
    echo BUILD FAILED — check output above for errors
)
pause
