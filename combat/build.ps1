param([switch]$Test)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $compiler)) { $compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe' }
if (-not (Test-Path -LiteralPath $compiler)) { throw 'Install .NET Framework 4.x or use the portable .NET project described in docs/ARM.md.' }
$dist = Join-Path $projectRoot 'dist'
New-Item -ItemType Directory -Path $dist -Force | Out-Null
$sources = @(Get-ChildItem -LiteralPath (Join-Path $projectRoot 'src') -Filter '*.cs' | ForEach-Object { $_.FullName })
$exe = Join-Path $dist 'FlightingSimulatorGame.exe'
& $compiler /nologo /target:exe /platform:anycpu /optimize+ /define:DESKTOP /r:System.dll /r:System.Core.dll /r:System.Drawing.dll /r:System.Windows.Forms.dll /r:System.Runtime.Serialization.dll ("/out:" + $exe) @sources
if ($LASTEXITCODE -ne 0) { throw 'Compilation failed' }
Write-Output "Built $exe"
if ($Test) { & $exe --self-test; if ($LASTEXITCODE -ne 0) { throw 'Self tests failed' } }
