param([ValidateSet('hardware','native')][string]$Kind = 'hardware')
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$source = Join-Path $root 'third_party/SpinalVoodoo'
$lock = Get-Content -Raw (Join-Path $root 'dependencies.lock.json') | ConvertFrom-Json
$expected = ($lock.repositories | Where-Object name -eq 'SpinalVoodoo').commit
$safe = 'safe.directory=' + $source.Replace('\','/')
$actual = & git -c $safe -C $source rev-parse HEAD
if ($LASTEXITCODE -or $actual -ne $expected) { throw 'Fetch the pinned SpinalVoodoo revision first' }
$dest = Join-Path $root "build/spinal-$Kind-src"
$marker = Join-Path $dest '.platform-source.json'
if (Test-Path -LiteralPath $dest) {
    if (-not (Test-Path -LiteralPath $marker)) { throw "Existing tree has no ownership marker: $dest" }
    $existing = Get-Content -Raw $marker | ConvertFrom-Json
    if ($existing.commit -ne $expected) { throw "Prepared source revision differs: $dest" }
} else {
    New-Item -ItemType Directory -Force (Join-Path $root 'build') | Out-Null
    $archive = Join-Path $root "build/spinal-$Kind-source.tar"
    & git -c $safe -C $source archive --format=tar -o $archive $expected
    if ($LASTEXITCODE) { throw 'Source export failed' }
    New-Item -ItemType Directory $dest | Out-Null
    & tar -xf $archive -C $dest
    if ($LASTEXITCODE) { throw 'Source extraction failed' }
    @{commit=$expected; kind=$Kind; upstream='https://github.com/fayalalebrun/SpinalVoodoo'} |
        ConvertTo-Json | Set-Content -LiteralPath $marker -Encoding UTF8
}
$patchName = if ($Kind -eq 'hardware') { 'hardware-headless-fence.patch' } else { 'glide-headless.patch' }
$patch = Join-Path $root "patches/spinal/$patchName"
if (Test-Path -LiteralPath $patch) {
    $probePreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & git -C $dest apply --check $patch 2>$null
        $applyStatus = $LASTEXITCODE
    } finally { $ErrorActionPreference = $probePreference }
    if ($applyStatus -eq 0) {
        & git -C $dest apply $patch
        if ($LASTEXITCODE) { throw 'Patch application failed' }
    } else {
        try {
            $ErrorActionPreference = 'Continue'
            & git -C $dest apply --reverse --check $patch 2>$null
            $reverseStatus = $LASTEXITCODE
        } finally { $ErrorActionPreference = $probePreference }
        if ($reverseStatus) { throw "Patch neither applicable nor already present: $patch" }
    }
}
Write-Output "Prepared source: $dest ($expected)"
