param([string]$PinFile = "$PSScriptRoot\de10_standard\output_files\DE10_Standard_GHRD.pin")
$ErrorActionPreference = 'Stop'
$reference = Get-Content -Raw "$PSScriptRoot\de10_standard\hps-ddr-reference-pins.json" | ConvertFrom-Json
$actual = @{}
foreach ($line in Get-Content -LiteralPath $PinFile) {
    if ($line -match '^\s*(HPS_DDR3_[^\s:]+)\s*:\s*(\S+)') { $actual[$matches[1]] = $matches[2] }
}
$count = 0
foreach ($pin in $reference.pins.PSObject.Properties) {
    if ($actual[$pin.Name] -ne $pin.Value) {
        throw "HPS DDR pin mismatch: $($pin.Name) expected $($pin.Value), actual $($actual[$pin.Name])"
    }
    $count++
}
if ($count -ne 72 -or $actual.Count -ne 72) { throw "Expected all 72 HPS DDR pins, got reference=$count actual=$($actual.Count)" }
Write-Output "PASS: all $count HPS DDR pins match the local Standard GHRD compiled reference."
