@echo off

:: Hardcode or dynamically set the correct Python path and job path
set PYTHON_PATH=%HOME%\python3111x64\python.exe
set JOB_PATH=%HOME%\site\wwwroot\App_Data\jobs\triggered\BBSS-Classification-Webjob\BBSS_Classification_WebJob

:: Optional: Add Scripts directory to PATH
set PATH=%PATH%;%PYTHON_PATH%\Scripts

:: Install dependencies only once, not on every trigger -- this env is
:: shared/persistent under %HOME%, so a prior install survives across runs.
:: To pick up a requirements.txt change, delete the marker file below via
:: Kudu (or bump its name) so the next run reinstalls.
if not exist "%HOME%\bbss_classification_deps_installed.txt" (
    %PYTHON_PATH% -m pip install -r "%JOB_PATH%\requirements.txt"
    if errorlevel 1 exit /b 1
    echo installed > "%HOME%\bbss_classification_deps_installed.txt"
)

:: Run the Python script
call "%PYTHON_PATH%" "%JOB_PATH%\main.py"
