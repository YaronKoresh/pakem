@echo off

cd %~dp0..

call pip install -e ".[dev,extra]"
call poe hook

pause
exit /B 0
