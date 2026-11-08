param([string]$Python = 'python', [switch]$SkipCoreUnits)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Push-Location $root
try {
    New-Item -ItemType Directory -Force build, reports | Out-Null
    & iverilog -g2012 -s tb_framebuffer -o build/tb_framebuffer.vvp hardware/rtl/framebuffer_pattern.v tests/tb_framebuffer.sv
    if ($LASTEXITCODE) { throw 'Framebuffer compile failed' }
    & vvp build/tb_framebuffer.vvp
    if ($LASTEXITCODE) { throw 'Framebuffer simulation failed' }
    if (-not $SkipCoreUnits) {
        & iverilog -g2012 -I third_party/RasterIX/rtl/RasterIX -s tb_rasterix_units -o build/tb_rasterix_units.vvp third_party/RasterIX/rtl/RasterIX/Rasterizer.v third_party/RasterIX/rtl/RasterIX/TestFunc.v tests/tb_rasterix_units.sv
        if ($LASTEXITCODE) { throw 'RasterIX unit compile failed; run fetch-deps.ps1 first' }
        & vvp build/tb_rasterix_units.vvp
        if ($LASTEXITCODE) { throw 'RasterIX unit simulation failed' }
    }
    & $Python -m unittest discover -s tests -p 'test_*.py' -v
    if ($LASTEXITCODE) { throw 'Host/transport tests failed' }
} finally { Pop-Location }
