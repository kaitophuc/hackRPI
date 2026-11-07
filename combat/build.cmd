@echo off
setlocal
set "FG_ROOT=%~dp0"
set "FG_CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if not exist "%FG_CSC%" set "FG_CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe"
if not exist "%FG_CSC%" (echo .NET Framework compiler not found. See README.md.& exit /b 1)
if not exist "%FG_ROOT%dist" mkdir "%FG_ROOT%dist"
"%FG_CSC%" /nologo /target:exe /platform:anycpu /optimize+ /define:DESKTOP /r:System.dll /r:System.Core.dll /r:System.Drawing.dll /r:System.Windows.Forms.dll /r:System.Runtime.Serialization.dll /out:"%FG_ROOT%dist\FlightingSimulatorGame.exe" "%FG_ROOT%src\*.cs"
if errorlevel 1 exit /b 1
echo Built dist\FlightingSimulatorGame.exe
if /i "%~1"=="test" "%FG_ROOT%dist\FlightingSimulatorGame.exe" --self-test
exit /b %errorlevel%
