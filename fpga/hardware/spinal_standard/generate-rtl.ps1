param([string]$Python = 'C:\Espressif\python_env\idf5.5_py3.11_env\Scripts\python.exe')
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path "$PSScriptRoot\..\..").Path
& "$PSScriptRoot\setup-toolchain.ps1"
& "$root\scripts\prepare-spinal.ps1" -Kind hardware
$env:JAVA_HOME = "$root\tools\spinal\jdk17\jdk-17.0.16+8"
$env:COURSIER_CACHE = "$root\tools\spinal\coursier-cache"
$env:COURSIER_REPOSITORIES = 'https://repo.maven.apache.org/maven2'
$env:SPINAL_STANDARD_RTL = "$PSScriptRoot\rtl"
New-Item -ItemType Directory -Force "$root\reports\spinal-hardware" | Out-Null
Push-Location "$root\build\spinal-hardware-src"
try {
    $savedPreference=$ErrorActionPreference
    $ErrorActionPreference='Continue' # Scala writes non-error compiler output to stderr.
    & "$root\tools\spinal\scala-cli-1.9.1\scala-cli.exe" run project.scala src "$PSScriptRoot\SpinalStandardGen.scala" --server=false --jvm system --main-class voodoo.de10.SpinalStandardGen 2>&1 |
        Tee-Object -FilePath "$root\reports\spinal-hardware\generation.log"
    $toolExit=$LASTEXITCODE
    $ErrorActionPreference=$savedPreference
    if ($toolExit -ne 0) { throw 'Spinal generation failed' }
} finally { Pop-Location }
& $Python "$PSScriptRoot\prepare-project.py"
if ($LASTEXITCODE -ne 0) { throw 'Standard wrapper/component generation failed' }
