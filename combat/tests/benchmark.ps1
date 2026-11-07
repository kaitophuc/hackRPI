param([string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$combatRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $combatRoot 'captures\performance\current' }
& (Join-Path $combatRoot 'build.ps1')
if ($LASTEXITCODE -ne 0) { throw 'Game build failed' }
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $compiler)) { $compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe' }
$gameExe = Join-Path $combatRoot 'dist\FlightingSimulatorGame.exe'
$probeExe = Join-Path $combatRoot 'dist\PerformanceProbe.exe'
$probeSource = Join-Path $PSScriptRoot 'PerformanceProbe.cs'
& $compiler /nologo /r:System.Runtime.Serialization.dll ("/r:" + $gameExe) ("/out:" + $probeExe) $probeSource
if ($LASTEXITCODE -ne 0) { throw 'Benchmark compilation failed' }
& $probeExe $OutputDirectory
if ($LASTEXITCODE -ne 0) { throw 'Benchmark failed' }
