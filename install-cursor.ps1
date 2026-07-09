# Installs the Conductor Cursor adapter into a project: always-on rule (digest of core),
# beforeShellExecution commit-gate hook, and its script. Idempotent: conductor entries in
# an existing .cursor/hooks.json are replaced, foreign entries preserved (file backed up
# first). Pair with install-git-gate.ps1 - the shell hook is the model-facing layer, the
# git hooks are the enforcement layer.
param(
    [string]$Repo = (Get-Location).Path
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

$srcRule = Join-Path $PSScriptRoot 'adapters\cursor\conductor-core.mdc'
$srcGate = Join-Path $PSScriptRoot 'adapters\cursor\gate.ps1'
foreach ($f in @($srcRule, $srcGate)) {
    if (-not (Test-Path $f)) { throw "adapter source not found: $f - run this script from the conductor repo root" }
}
if (-not (Test-Path $Repo)) { throw "target directory does not exist: $Repo" }
$Repo = (Resolve-Path $Repo).Path

$cursorDir = Join-Path $Repo '.cursor'
$rulesDir = Join-Path $cursorDir 'rules'
$gateDir = Join-Path $cursorDir 'conductor'
New-Item -ItemType Directory -Force $rulesDir | Out-Null
New-Item -ItemType Directory -Force $gateDir | Out-Null

Copy-Item $srcRule (Join-Path $rulesDir 'conductor-core.mdc') -Force
Copy-Item $srcGate (Join-Path $gateDir 'gate.ps1') -Force
Write-Output "rule installed:  $rulesDir\conductor-core.mdc (alwaysApply)"
Write-Output "gate installed:  $gateDir\gate.ps1"

$shell = if (Get-Command pwsh -ErrorAction SilentlyContinue) { 'pwsh' } else { 'powershell' }
$hookCommand = "$shell -NoProfile -ExecutionPolicy Bypass -File .cursor/conductor/gate.ps1"
$conductorEntry = [pscustomobject]@{ command = $hookCommand; timeout = 10 }

$hooksJsonPath = Join-Path $cursorDir 'hooks.json'
if (Test-Path $hooksJsonPath) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    Copy-Item $hooksJsonPath "$hooksJsonPath.bak-$stamp" -Force
    $cfg = Get-Content $hooksJsonPath -Raw | ConvertFrom-Json
    if (-not ($cfg.PSObject.Properties.Name -contains 'hooks')) {
        $cfg | Add-Member -NotePropertyName hooks -NotePropertyValue ([pscustomobject]@{})
    }
    $kept = @()
    if ($cfg.hooks.PSObject.Properties.Name -contains 'beforeShellExecution') {
        $kept = @($cfg.hooks.beforeShellExecution) | Where-Object { ($_ | ConvertTo-Json -Depth 10) -notmatch 'conductor' }
        $cfg.hooks.PSObject.Properties.Remove('beforeShellExecution')
    }
    $cfg.hooks | Add-Member -NotePropertyName beforeShellExecution -NotePropertyValue (@($kept) + $conductorEntry)
    if (-not ($cfg.PSObject.Properties.Name -contains 'version')) {
        $cfg | Add-Member -NotePropertyName version -NotePropertyValue 1
    }
    $cfg | ConvertTo-Json -Depth 20 | Set-Content $hooksJsonPath -Encoding utf8
    Write-Output "hooks merged:    $hooksJsonPath (backup: hooks.json.bak-$stamp; foreign entries preserved)"
} else {
    $cfg = [pscustomobject]@{
        version = 1
        hooks = [pscustomobject]@{ beforeShellExecution = @($conductorEntry) }
    }
    $cfg | ConvertTo-Json -Depth 20 | Set-Content $hooksJsonPath -Encoding utf8
    Write-Output "hooks written:   $hooksJsonPath"
}

$gitGate = $null
if (git -C $Repo rev-parse --git-dir 2>$null) {
    $gitGateHook = git -C $Repo rev-parse --path-format=absolute --git-path hooks/pre-commit 2>$null
    if ($gitGateHook -and (Test-Path $gitGateHook) -and ((Get-Content $gitGateHook -Raw) -match 'conductor gate')) { $gitGate = $gitGateHook }
}
if ($gitGate) { Write-Output "git-native gate: present ($gitGate)" }
else { Write-Output "git-native gate: NOT installed - run install-git-gate.ps1 -Repo `"$Repo`" for the enforcement layer" }
Write-Output 'Done. Restart the Cursor agent session in this project to pick up hooks.json.'
