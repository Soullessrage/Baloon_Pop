@echo off
setlocal
cd /d "%~dp0"

where pyw >nul 2>nul
if not errorlevel 1 goto use_py_launcher

where pythonw >nul 2>nul
if not errorlevel 1 goto use_pythonw

echo Python 3.10 or newer with Tkinter was not found. Install Python and include Tcl/Tk support.
echo Then double-click this launcher again.
pause
exit /b 1

:use_py_launcher
py -3 -c "import sys, tkinter; raise SystemExit(sys.version_info < (3, 10))" >nul 2>nul
if errorlevel 1 goto missing_tkinter
start "" pyw -3 "%~dp0app\main.py"
exit /b 0

:use_pythonw
python -c "import sys, tkinter; raise SystemExit(sys.version_info < (3, 10))" >nul 2>nul
if errorlevel 1 goto missing_tkinter
start "" pythonw "%~dp0app\main.py"
exit /b 0

:missing_tkinter
echo Python 3.10 or newer with Tkinter was not found. Install Python and include Tcl/Tk support.
pause
exit /b 1