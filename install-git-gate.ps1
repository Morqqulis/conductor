# Installs the Conductor git-native commit gate (pre-commit checks the verification
# marker, post-commit consumes it after a successful commit) from runtime/git-hooks/.
# Modes:
#   -Repo <path>    one repository (default: current directory)
#   -Sweep <root>   every git repository found under <root> (depth 4; node_modules,
#                   .venv, vendor and dot-cache dirs skipped)
# Idempotent: existing conductor hooks are updated in place; a foreign hook of the same
# name is backed up to <name>.pre-conductor and chained after the gate. Hooks land in the
# repo's COMMON hooks directory (correct for linked worktrees). Repositories with
# core.hooksPath are skipped with a message (a hook manager owns hooks there).
param(
    [string]$Repo = (Get-Location).Path,
    [string]$Sweep
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

$sources = @{}
foreach ($name in @('post-commit', 'post-merge', 'pre-merge-commit', 'pre-commit')) {
    $src = Join-Path $PSScriptRoot "runtime\git-hooks\$name"
    if (-not (Test-Path $src)) { throw "hook source not found: $src - run this script from the conductor repo root" }
    $content = ([IO.File]::ReadAllText($src)) -replace "`r`n", "`n"   # sh requires LF endings
    if ($content -notmatch 'conductor gate') { throw "source hook $name lacks the 'conductor gate' sentinel - refusing to install unrecognized content" }
    $sources[$name] = $content
}
$sh = 'C:\Program Files\Git\bin\sh.exe'
if (-not (Test-Path $sh)) { $sh = 'sh' }

function Install-GateInto([string]$target) {
    $root = git -C $target rev-parse --show-toplevel 2>$null
    if (-not $root) { Write-Host "SKIP  $target : not a git repository"; return $false }
    if (-not (Test-Path $root)) { Write-Host "SKIP  $target : git returned a nonexistent root ('$root') - console encoding issue"; return $false }
    $hooksPath = git -C $target config --get core.hooksPath
    if ($hooksPath) { Write-Host "SKIP  $root : core.hooksPath='$hooksPath' (hook manager owns hooks; add the marker check there manually)"; return $false }
    $commonDir = git -C $target rev-parse --git-common-dir
    if (-not [IO.Path]::IsPathRooted($commonDir)) { $commonDir = Join-Path $root $commonDir }
    $hooksDir = Join-Path $commonDir 'hooks'
    New-Item -ItemType Directory -Force $hooksDir | Out-Null
    # post-commit first: a partial install must never enable the check without its consumer
    foreach ($name in @('post-commit', 'post-merge', 'pre-merge-commit', 'pre-commit')) {
        $dest = Join-Path $hooksDir $name
        if (Test-Path $dest) {
            $existing = [IO.File]::ReadAllText($dest)
            if ($existing -notmatch 'conductor gate') {
                $backup = "$dest.pre-conductor"
                if (Test-Path $backup) { Write-Host "SKIP  $root : foreign $name and $name.pre-conductor both exist - resolve manually"; return $false }
                Move-Item $dest $backup
                Write-Host "      $root : foreign $name backed up and chained"
            }
        }
        [IO.File]::WriteAllText($dest, $sources[$name], (New-Object System.Text.UTF8Encoding($false)))
        if (-not $IsWindows) { chmod +x $dest }
        & $sh -n $dest
        if ($LASTEXITCODE -ne 0) { Write-Host "FAIL  $root : $name failed the sh syntax check"; return $false }
    }
    Write-Host "OK    $root"
    return $true
}

if ($Sweep) {
    if (-not (Test-Path $Sweep)) { throw "sweep root does not exist: $Sweep" }
    $exclude = '\\node_modules\\|\\\.venv\\|\\vendor\\|\\\.cache\\|\\\.git\\'
    $gitMarkers = Get-ChildItem -Path $Sweep -Recurse -Depth 4 -Force -Filter '.git' -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch $exclude }
    $repos = @($gitMarkers | ForEach-Object { Split-Path $_.FullName } | Sort-Object -Unique)
    Write-Output "sweep: $($repos.Count) repositories found under $Sweep"
    $ok = 0
    foreach ($r in $repos) { if (Install-GateInto $r) { $ok++ } }
    Write-Output "sweep result: $ok/$($repos.Count) gated"
} else {
    if (-not (Install-GateInto $Repo)) { exit 1 }
    Write-Output "conductor git gate installed for $Repo"
}
