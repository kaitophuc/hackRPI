param([string]$QuartusRoot='D:\Quartus\quartus')
$ErrorActionPreference='Stop'
$root=(Resolve-Path "$PSScriptRoot\..\..").Path
# Reuse a successful Analysis & Synthesis result only when HDL/generated system
# and synthesis settings have not changed. For any such change use build.ps1.
if (-not (Test-Path "$PSScriptRoot\output_files\Spinal_Standard_GPU.map.rpt")) {
    throw 'No synthesis report; run build.ps1 first'
}
$log="$root\reports\spinal-hardware\quartus-refit-seed2.log"
Set-Content -LiteralPath $log -Encoding Unicode -Value 'Fitter-only retry: unchanged synthesized RTL, Standard Fit, seed 2.'
Push-Location $PSScriptRoot
try {
    foreach ($tool in @('quartus_fit','quartus_asm','quartus_sta')) {
        $savedPreference=$ErrorActionPreference
        try {
            $ErrorActionPreference='Continue'
            & "$QuartusRoot\bin64\$tool.exe" Spinal_Standard_GPU -c Spinal_Standard_GPU 2>&1 |
                Tee-Object -FilePath $log -Append
            $status=$LASTEXITCODE
        } finally { $ErrorActionPreference=$savedPreference }
        if ($status -ne 0) { throw "$tool failed with exit $status" }
    }
    & "$root\hardware\verify-pins.ps1" -PinFile "$PSScriptRoot\output_files\Spinal_Standard_GPU.pin"
} finally { Pop-Location }
# Successful tool exit does not prove timing closure. Review all timing corners.
