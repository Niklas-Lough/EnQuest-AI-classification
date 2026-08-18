@echo off

:: Hardcode or dynamically set the correct Python path and job path
set PYTHON_PATH=%HOME%\python3122x64\python.exe
set JOB_PATH=%HOME%\site\wwwroot\App_Data\jobs\triggered\EnQuest-BBSS-Classification-Webjob\EnQuest_BBSS_Classification_WebJob

:: Optional: Add Scripts directory to PATH
set PATH=%PATH%;%PYTHON_PATH%\Scripts

:: Install dependencies (optional, only if needed each run)
%PYTHON_PATH% -m pip install -r "%JOB_PATH%\requirements.txt"

:: Run the Python script
call "%PYTHON_PATH%" "%JOB_PATH%\enquest_main.py"
