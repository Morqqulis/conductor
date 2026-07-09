# Installs the Conductor git-native commit gate into a repository: pre-commit (checks the
# verification marker) + post-commit (consumes it after a successful commit), from
# runtime/git-hooks/. Idempotent: existing conductor hooks are updated in place; a foreign
# hook of the same name is backed up to <name>.pre-conductor and chained after the gate.
# Hooks land in the repo's COMMON hooks directory (correct for linked worktrees).
# Refuses repositories where core.hooksPath is set (a hook manager owns hooks there).
param(
    [string]$Repo = (Get-Location).Path
)
$ErrorActionPreference = 'Stop'
# Decode git's output as UTF-8: under an OEM console codepage a non-ASCII repo path would
# corrupt and the hook would be silently installed into a freshly created garbage-named dir.
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

$root = git -C $Repo rev-parse --show-toplevel 2>$null
if (-not $root) { throw "not a git repository: $Repo" }
if (-not (Test-Path $root)) { throw "git returned a repo root that does not exist on disk ('$root') - console encoding is corrupting paths; run from a UTF-8 console" }

$hooksPath = git -C $Repo config --get core.hooksPath
if ($hooksPath) {
    throw "core.hooksPath is set to '$hooksPath' - a hook manager owns this repository's hooks. Add the marker check from runtime/git-hooks/pre-commit to that manager's pre-commit instead."
}

$commonDir = git -C $Repo rev-parse --git-common-dir
if (-not [IO.Path]::IsPathRooted($commonDir)) { $commonDir = Join-Path $root $commonDir }
if (-not (Test-Path $commonDir)) { throw "resolved git common dir does not exist: $commonDir" }
$hooksDir = Join-Path $commonDir 'hooks'
New-Item -ItemType Directory -Force $hooksDir | Out-Null

$sh = 'C:\Program Files\Git\bin\sh.exe'
if (-not (Test-Path $sh)) { $sh = 'sh' }

foreach ($name in @('pre-commit', 'post-commit')) {
    $source = Join-Path $PSScriptRoot "runtime\git-hooks\$name"
    if (-not (Test-Path $source)) { throw "hook source not found: $source - run this script from the conductor repo root" }
    $content = [IO.File]::ReadAllText($source)
    if ($content -notmatch 'conductor gate') { throw "source hook $name lacks the 'conductor gate' sentinel - refusing to install unrecognized content" }
    $content = $content -replace "`r`n", "`n"   # sh requires LF endings regardless of checkout conversion

    $target = Join-Path $hooksDir $name
    if (Test-Path $target) {
        $existing = [IO.File]::ReadAllText($target)
        if ($existing -match 'conductor gate') {
            Write-Output "$name : existing conductor gate found - updating in place"
        } else {
            $backup = "$target.pre-conductor"
            if (Test-Path $backup) { throw "both a foreign $name and $backup already exist - resolve manually before installing" }
            Move-Item $target $backup
            Write-Output "$name : foreign hook backed up to $name.pre-conductor - the gate will chain to it"
        }
    }
    [IO.File]::WriteAllText($target, $content, (New-Object System.Text.UTF8Encoding($false)))
    if (-not $IsWindows) { chmod +x $target }
    & $sh -n $target
    if ($LASTEXITCODE -ne 0) { throw "installed hook failed the sh syntax check: $target" }
    Write-Output "conductor git gate installed: $target"
}
