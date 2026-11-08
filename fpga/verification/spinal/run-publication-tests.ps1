$ErrorActionPreference='Stop'
$root=(Resolve-Path "$PSScriptRoot\..\..").Path
$out=Join-Path $root 'build/tb_publication.vvp'
& iverilog -g2012 -s tb_publication -o $out "$root/hardware/spinal_standard/avalon_frame_fence.v" "$root/hardware/spinal_standard/gpu2_sidecar.v" "$PSScriptRoot/tb_publication.sv"
if($LASTEXITCODE) { throw 'Publication test compile failed' }
& vvp $out | Tee-Object -FilePath "$root/reports/spinal-fence-tests.log"
if($LASTEXITCODE) { throw 'Publication test failed' }
