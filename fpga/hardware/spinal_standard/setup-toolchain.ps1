$ErrorActionPreference = 'Stop'
$root = (Resolve-Path "$PSScriptRoot\..\..").Path
$toolsRoot = Join-Path $root 'tools\spinal'
New-Item -ItemType Directory -Force $toolsRoot | Out-Null
$downloads = @(
    @{Name='scala-cli-1.9.1.zip'; Url='https://github.com/VirtusLab/scala-cli/releases/download/v1.9.1/scala-cli-x86_64-pc-win32.zip'; Sha256='DE26717A20A4103EFA8C3BA15591FB3E0BEAEEF4A4DD84B0E95E594322D860AB'},
    @{Name='temurin-jdk-17.0.16_8.zip'; Url='https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.16%2B8/OpenJDK17U-jdk_x64_windows_hotspot_17.0.16_8.zip'; Sha256='8C7CFFF78A55C56EBAF470ED6A89C6466B47D8274BDABDDA997D7507C20325C5'}
)
foreach ($download in $downloads) {
    $archive = Join-Path $toolsRoot $download.Name
    if (-not (Test-Path -LiteralPath $archive)) {
        Invoke-WebRequest -UseBasicParsing -Uri $download.Url -OutFile $archive
    }
    if ((Get-FileHash -LiteralPath $archive).Hash -ne $download.Sha256) {
        throw "Pinned toolchain checksum mismatch: $archive"
    }
}
$cli = Join-Path $toolsRoot 'scala-cli-1.9.1\scala-cli.exe'
$javaHome = Join-Path $toolsRoot 'jdk17\jdk-17.0.16+8'
if (-not (Test-Path -LiteralPath $cli)) {
    Expand-Archive -LiteralPath (Join-Path $toolsRoot 'scala-cli-1.9.1.zip') -DestinationPath (Join-Path $toolsRoot 'scala-cli-1.9.1')
}
if (-not (Test-Path -LiteralPath "$javaHome\bin\java.exe")) {
    Expand-Archive -LiteralPath (Join-Path $toolsRoot 'temurin-jdk-17.0.16_8.zip') -DestinationPath (Join-Path $toolsRoot 'jdk17')
}
$downloads | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $toolsRoot 'toolchain.lock.json')
Write-Output "Pinned Scala CLI: $cli"
Write-Output "Pinned JDK: $javaHome"
