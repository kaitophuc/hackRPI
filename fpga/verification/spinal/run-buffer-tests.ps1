$ErrorActionPreference='Stop'
$root=(Resolve-Path "$PSScriptRoot\..\..").Path
& "$root\scripts\prepare-spinal.ps1" -Kind hardware
$env:JAVA_HOME="$root\tools\spinal\jdk17\jdk-17.0.16+8"
$env:COURSIER_CACHE="$root\tools\spinal\coursier-cache"
$env:COURSIER_REPOSITORIES='https://repo.maven.apache.org/maven2'
$env:CPLUS_INCLUDE_PATH="$root\tools\spinal\boost-headers\boost_1_85_0"
$env:PATH='D:\Quartus\questa_fse\gcc-7.4.0-mingw64vc16\bin;C:\Users\assis\iverilog\bin;' + $env:PATH
Push-Location "$root\build\spinal-hardware-src"
try {
    $ErrorActionPreference='Continue' # Scala CLI also emits informational stderr.
    & "$root\tools\spinal\scala-cli-1.9.1\scala-cli.exe" test project.scala src $PSScriptRoot --server=false --jvm system --test-only 'platformverification.*' 2>&1 |
        Tee-Object -FilePath "$root\reports\spinal-buffer-tests.log"
    if ($LASTEXITCODE) { throw 'Framebuffer/bridge regression failed' }
} finally { Pop-Location }
