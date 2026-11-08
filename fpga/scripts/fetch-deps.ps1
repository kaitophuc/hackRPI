param([switch]$AllCandidates)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$lock = Get-Content -Raw -LiteralPath (Join-Path $root 'dependencies.lock.json') | ConvertFrom-Json
New-Item -ItemType Directory -Force (Join-Path $root 'third_party') | Out-Null
foreach ($repo in $lock.repositories) {
    if (-not $AllCandidates -and $repo.name -notin @('SpinalVoodoo','RasterIX')) { continue }
    $dest = Join-Path $root ('third_party/' + $repo.name)
    if (-not (Test-Path -LiteralPath $dest)) {
        & git clone $repo.url $dest
        if ($LASTEXITCODE) { throw "Clone failed: $($repo.name)" }
    }
    $safe = 'safe.directory=' + ($dest -replace '\\','/')
    $changes = & git -c $safe -C $dest status --porcelain
    if ($LASTEXITCODE) { throw 'Cannot inspect dependency worktree' }
    if ($changes) { throw "Dependency contains local changes; preserve them before checkout: $dest" }
    & git -c $safe -C $dest cat-file -e ($repo.commit + '^{commit}')
    if ($LASTEXITCODE) {
        & git -c $safe -C $dest fetch origin $repo.commit
        if ($LASTEXITCODE) { throw 'Fetch failed' }
    }
    & git -c $safe -C $dest checkout --detach $repo.commit
    if ($LASTEXITCODE) { throw 'Checkout failed' }
    foreach ($submodule in $repo.submodules) {
        & git -c $safe -C $dest submodule update --init -- $submodule
        if ($LASTEXITCODE) { throw 'Submodule initialization failed' }
    }
    $actual = & git -c $safe -C $dest rev-parse HEAD
    if ($actual -ne $repo.commit) { throw 'Dependency revision mismatch' }
    Write-Output "$($repo.name): $actual"
}
