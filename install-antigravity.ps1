# Installs the Conductor Antigravity adapter into a workspace: rule digest
# (.agents/rules/conductor-core.md - set to Always On in the Antigravity rules UI),
# PreToolUse commit-gate hook (.agents/hooks.json, matcher run_command) and its script.
# Idempotent: the conductor entry in an existing hooks.json is replaced, foreign entries
# preserved (file backed up first). Pair with install-git-gate.ps1 - the tool hook is the
# model-facing layer, the git hooks are the enforcement layer.
param(
    [string]$Repo = (Get-Location).Path
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

$srcRule = Join-Path $PSScriptRoot 'adapters\antigravity\conductor-core.md'
$srcGate = Join-Path $PSScriptRoot 'adapters\antigravity\gate.ps1'
foreach ($f in @($srcRule, $srcGate)) {
    if (-not (Test-Path $f)) { throw "adapter source not found: $f - run this script from the conductor repo root" }
}
if (-not (Test-Path $Repo)) { throw "target directory does not exist: $Repo" }
$Repo = (Resolve-Path $Repo).Path

$agentsDir = Join-Path $Repo '.agents'
$rulesDir = Join-Path $agentsDir 'rules'
$gateDir = Join-Path $agentsDir 'conductor'
New-Item -ItemType Directory -Force $rulesDir | Out-Null
New-Item -ItemType Directory -Force $gateDir | Out-Null

Copy-Item $srcRule (Join-Path $rulesDir 'conductor-core.md') -Force
Copy-Item $srcGate (Join-Path $gateDir 'gate.ps1') -Force
Write-Output "rule installed:  $rulesDir\conductor-core.md  (set it to Always On in Antigravity: Customizations -> Rules)"
Write-Output "gate installed:  $gateDir\gate.ps1"

$shell = if (Get-Command pwsh -ErrorAction SilentlyContinue) { 'pwsh' } else { 'powershell' }
$gateAbs = Join-Path $gateDir 'gate.ps1'
$hookCommand = "$shell -NoProfile -ExecutionPolicy Bypass -File `"$gateAbs`""
$conductorBlock = [pscustomobject]@{
    PreToolUse = @(
        [pscustomobject]@{
            matcher = 'run_command'
            hooks = @([pscustomobject]@{ type = 'command'; command = $hookCommand; timeout = 30 })
        }
    )
}

$hooksJsonPath = Join-Path $agentsDir 'hooks.json'
if (Test-Path $hooksJsonPath) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    Copy-Item $hooksJsonPath "$hooksJsonPath.bak-$stamp" -Force
    $cfg = Get-Content $hooksJsonPath -Raw | ConvertFrom-Json
    if ($cfg.PSObject.Properties.Name -contains 'conductor-commit-gate') {
        $cfg.PSObject.Properties.Remove('conductor-commit-gate')
    }
    $cfg | Add-Member -NotePropertyName 'conductor-commit-gate' -NotePropertyValue $conductorBlock
    $cfg | ConvertTo-Json -Depth 20 | Set-Content $hooksJsonPath -Encoding utf8
    Write-Output "hooks merged:    $hooksJsonPath (backup: hooks.json.bak-$stamp; foreign entries preserved)"
} else {
    $cfg = [pscustomobject]@{ 'conductor-commit-gate' = $conductorBlock }
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
Write-Output 'Done. Restart the Antigravity agent session in this workspace to pick up hooks.json.'
