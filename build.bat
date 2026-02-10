@echo off
echo Building Impetus...
pyinstaller impetus.spec --noconfirm
echo.
if exist dist\Impetus.exe (
    echo Build successful: dist\Impetus.exe
) else (
    echo Build failed!
)
pause
