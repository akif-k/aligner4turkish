@echo off
setlocal
cd /d "%~dp0"

call "%USERPROFILE%\miniconda3\condabin\conda.bat" activate mms_aligner
if errorlevel 1 (
    echo [HATA] "mms_aligner" conda ortami etkinlestirilemedi. "conda env create -f environment.yml" ile olusturun.
    pause
    exit /b 1
)

python mmsaligner.py

pause
