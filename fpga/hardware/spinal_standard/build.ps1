param([string]$QuartusRoot='D:\Quartus\quartus', [switch]$SkipRtlGeneration)
$ErrorActionPreference='Stop'
$root=(Resolve-Path "$PSScriptRoot\..\..").Path
if (-not $SkipRtlGeneration) { & "$PSScriptRoot\generate-rtl.ps1" }
$component="$PSScriptRoot\gpu_spinal_standard_hw.tcl".Replace('\','/')
$projectForward=$PSScriptRoot.Replace('\','/')
New-Item -ItemType Directory -Force "$root\reports\spinal-hardware" | Out-Null
function Invoke-CheckedTool {
    param([string]$Tool, [string[]]$ToolArgs, [string]$Log='')
    $previous=$ErrorActionPreference
    try {
        $ErrorActionPreference='Continue' # Quartus also writes informational messages to stderr.
        if($Log) { & $Tool @ToolArgs 2>&1 | Tee-Object -FilePath $Log }
        else { & $Tool @ToolArgs }
        $status=$LASTEXITCODE
    } finally { $ErrorActionPreference=$previous }
    if($status -ne 0) { throw "Tool failed with exit $status : $Tool" }
}
Push-Location $PSScriptRoot
try {
    Invoke-CheckedTool -Tool "$QuartusRoot\sopc_builder\bin\qsys-script.exe" -ToolArgs @("--search-path=$component,`$", "--cmd=set standard_project_dir {$projectForward}", "--script=$PSScriptRoot\create-system.tcl")
    Invoke-CheckedTool -Tool "$QuartusRoot\sopc_builder\bin\qsys-generate.exe" -ToolArgs @('spinal_system.qsys','--synthesis=VERILOG',"--search-path=$component,`$") -Log "$root\reports\spinal-hardware\qsys-generation.log"
    Invoke-CheckedTool -Tool "$QuartusRoot\bin64\quartus_sh.exe" -ToolArgs @('--flow','compile','Spinal_Standard_GPU') -Log "$root\reports\spinal-hardware\quartus-build.log"
    & "$root\hardware\verify-pins.ps1" -PinFile "$PSScriptRoot\output_files\Spinal_Standard_GPU.pin"
} finally { Pop-Location }
# Deliberately no programming: root must review DDR ownership, tests and reports.
