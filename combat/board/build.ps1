param([switch]$Test)
$ErrorActionPreference='Stop'
$combat=(Resolve-Path "$PSScriptRoot\..").Path
$compiler=Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
New-Item -ItemType Directory -Force "$combat\dist" | Out-Null
$sources=@(Get-ChildItem "$combat\src" -Filter '*.cs' | Where-Object Name -ne Desktop.cs | ForEach-Object FullName)
& $compiler /nologo /target:exe /platform:anycpu /optimize+ /r:System.dll /r:System.Core.dll /r:System.Runtime.Serialization.dll "/out:$combat\dist\Flighting.Headless.exe" @sources
if($LASTEXITCODE){throw 'Headless game compilation failed'}
if($Test){& "$combat\dist\Flighting.Headless.exe" --self-test;if($LASTEXITCODE){throw 'Headless self-tests failed'}}
