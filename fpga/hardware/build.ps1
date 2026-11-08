param([string]$QuartusRoot = 'D:\Quartus\quartus')
$ErrorActionPreference = 'Stop'
$hardwareRoot = $PSScriptRoot
$projectRoot = Join-Path $hardwareRoot 'de10_standard'
$component = (Join-Path $hardwareRoot 'framebuffer_pattern_hw.tcl').Replace('\','/')
Push-Location $projectRoot
try {
    & "$QuartusRoot\sopc_builder\bin\qsys-generate.exe" soc_system.qsys --synthesis=VERILOG "--search-path=$component,`$"
    if ($LASTEXITCODE -ne 0) { throw 'Platform Designer generation failed; inspect soc_system/soc_system_generation.rpt. HPS sequencer requires WSL access.' }
    & "$QuartusRoot\bin64\quartus_sh.exe" --flow compile DE10_Standard_GHRD
    if ($LASTEXITCODE -ne 0) { throw 'Quartus compilation failed; inspect output_files reports.' }
    & "$hardwareRoot\verify-pins.ps1"
} finally { Pop-Location }
