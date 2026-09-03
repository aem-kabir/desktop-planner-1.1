@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

REM ============================================================
REM  build.bat - сборка DesktopPlanner.exe и Setup.exe в одну кнопку.
REM  Требования (установить один раз):
REM    1) Python 3.10+  https://www.python.org/downloads/  (отметить "Add to PATH")
REM    2) Inno Setup 7  https://jrsoftware.org/isdl.php#v7  (рекомендуется 64-битная редакция)
REM  Запускать этот файл из корня проекта (там, где лежит эта же папка app\).
REM ============================================================

echo.
echo === [1/5] Проверка Python ===
where python >nul 2>nul
if errorlevel 1 (
    echo ОШИБКА: Python не найден в PATH. Установите Python 3.10+ и повторите.
    pause
    exit /b 1
)
python --version

echo.
echo === [2/5] Создание виртуального окружения (venv) ===
if not exist ".venv" (
    python -m venv .venv
)
call .venv\Scripts\activate.bat

echo.
echo === [3/5] Установка зависимостей ===
python -m pip install --upgrade pip
pip install -r app\requirements-build.txt
if errorlevel 1 (
    echo ОШИБКА: не удалось установить зависимости.
    pause
    exit /b 1
)

echo.
echo === [4/5] Сборка .exe через PyInstaller ===
if not exist "app\assets\icon.ico" (
    echo ОШИБКА: не найден app\assets\icon.ico - сборка PyInstaller упадёт без иконки.
    pause
    exit /b 1
)

pyinstaller --noconfirm --clean ^
    --name "DesktopPlanner" ^
    --windowed ^
    --icon "app\assets\icon.ico" ^
    --add-data "app\assets;assets" ^
    --paths "app" ^
    "app\main.py"

if errorlevel 1 (
    echo ОШИБКА: PyInstaller завершился с ошибкой.
    pause
    exit /b 1
)

echo.
echo === [5/5] Сборка инсталлятора через Inno Setup ===
set ISCC=""
for %%P in (
    "%ProgramFiles%\Inno Setup 7\ISCC.exe"
    "%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe"
    "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
    "%ProgramFiles%\Inno Setup 6\ISCC.exe"
) do (
    if exist %%P (
        set ISCC=%%P
    )
)

if !ISCC!=="" (
    echo ПРЕДУПРЕЖДЕНИЕ: Inno Setup (ISCC.exe) не найден. Установите его с https://jrsoftware.org/isdl.php#v7
    echo .exe приложения собран в dist\DesktopPlanner\DesktopPlanner.exe, но Setup.exe не создан.
    pause
    exit /b 0
)

!ISCC! "installer\installer.iss"
if errorlevel 1 (
    echo ОШИБКА: Inno Setup завершился с ошибкой.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  ГОТОВО!
echo  Приложение:   dist\DesktopPlanner\DesktopPlanner.exe
echo  Инсталлятор:  dist_installer\DesktopPlanner_Setup.exe
echo ============================================================
pause
