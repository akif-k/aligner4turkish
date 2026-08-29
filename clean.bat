@echo off
REM output\ klasorunun icerigini ve calisirken olusan gecici dosyalari
REM (orn. __pycache__) siler. input\ klasorune (girdi) ve klasorlerin
REM kendisine dokunmaz. models\ klasorune de DOKUNMAZ (yeniden indirmek
REM pahalidir).
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
cd /d "%SCRIPT_DIR%"

set "YES=0"
if /i "%~1"=="-y" set "YES=1"
if /i "%~1"=="--yes" set "YES=1"
if not "%~1"=="" if "%YES%"=="0" (
    echo Bilinmeyen secenek: %~1
    echo Kullanim: %~nx0 [-y^|--yes]
    exit /b 1
)

echo Silinecek:
echo   - %SCRIPT_DIR%\output\*
echo   - __pycache__ klasorleri (proje icinde)

if "%YES%"=="0" (
    set /p "REPLY=Devam edilsin mi? [e/H] "
    if /i not "!REPLY!"=="e" if /i not "!REPLY!"=="evet" if /i not "!REPLY!"=="y" if /i not "!REPLY!"=="yes" (
        echo Iptal edildi.
        exit /b 0
    )
)

for %%D in (output) do (
    if not exist "%%D" mkdir "%%D"
    del /q "%%D\*" >nul 2>nul
    for /d %%S in ("%%D\*") do rd /s /q "%%S"
)

for /d /r %%P in (__pycache__) do (
    if exist "%%P" rd /s /q "%%P"
)

echo Temizlendi.
