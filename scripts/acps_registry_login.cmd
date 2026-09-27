@echo off
setlocal

for %%I in ("%~dp0..") do set "PROJECT_ROOT=%%~fI"
set "PYTHONPATH=%PROJECT_ROOT%\tmp\acps-community-v2.2.0\acps-cli"

"%PROJECT_ROOT%\.venv\Scripts\python.exe" -m acps_cli.main ^
  --config "%PROJECT_ROOT%\deploy\secrets\acps-cli.toml" ^
  auth login

endlocal
