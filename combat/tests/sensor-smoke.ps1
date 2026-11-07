param([string]$SensorUrl = 'http://127.0.0.1:8765/', [switch]$Desktop)
$ErrorActionPreference = 'Stop'
$combatRoot = Split-Path -Parent $PSScriptRoot
& (Join-Path $combatRoot 'build.ps1')
if ($LASTEXITCODE -ne 0) { throw 'Game build failed' }
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $compiler)) { $compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe' }
$gameExe = Join-Path $combatRoot 'dist\FlightingSimulatorGame.exe'
$testExe = Join-Path $combatRoot 'dist\SensorBridgeSmoke.exe'
$testSource = Join-Path $PSScriptRoot 'SensorBridgeSmoke.cs'
& $compiler /nologo /target:exe ("/r:" + $gameExe) ("/out:" + $testExe) $testSource
if ($LASTEXITCODE -ne 0) { throw 'Sensor smoke test compilation failed' }
if ($Desktop) {
    $captureDirectory = Join-Path $combatRoot 'captures\validation'
    New-Item -ItemType Directory -Path $captureDirectory -Force | Out-Null
    & $testExe $SensorUrl (Join-Path $captureDirectory 'sensor-desktop.png')
} else {
    & $testExe $SensorUrl
}
if ($LASTEXITCODE -ne 0) { throw 'Sensor smoke test failed' }
