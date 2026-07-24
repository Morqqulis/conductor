# Installs the Conductor Antigravity adapter into a workspace: rule digest
# (.agents/rules/conductor-core.md - set to Always On in the Antigravity rules UI).
# The commit-gate hook of older versions is retired (the marker gate certified nothing -
# agents satisfied it ritually): the conductor entry left in .agents/hooks.json and the
# .agents/conductor/gate.ps1 script are removed. Idempotent; configs backed up first.
param(
    [string]$Repo = (Get-Location).Path
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

$srcRule = Join-Path $PSScriptRoot 'adapters\antigravity\conductor-core.md'
if (-not (Test-Path $srcRule)) { throw "adapter source not found: $srcRule - run this script from the conductor repo root" }
if (-not (Test-Path $Repo)) { throw "target directory does not exist: $Repo" }
$Repo = (Resolve-Path $Repo).Path

$agentsDir = Join-Path $Repo '.agents'
$rulesDir = Join-Path $agentsDir 'rules'
New-Item -ItemType Directory -Force $rulesDir | Out-Null
Copy-Item $srcRule (Join-Path $rulesDir 'conductor-core.md') -Force
Write-Output "rule installed:  $rulesDir\conductor-core.md  (set it to Always On in Antigravity: Customizations -> Rules)"

# Retired commit-gate cleanup (older versions)
$gateScript = Join-Path $agentsDir 'conductor\gate.ps1'
if (Test-Path $gateScript) {
    Remove-Item (Join-Path $agentsDir 'conductor') -Recurse -Force
    Write-Output "retired gate script removed: $gateScript"
}
$hooksJsonPath = Join-Path $agentsDir 'hooks.json'
if (Test-Path $hooksJsonPath) {
    $cfg = Get-Content $hooksJsonPath -Raw | ConvertFrom-Json
    if ($cfg.PSObject.Properties.Name -contains 'conductor-commit-gate') {
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        Copy-Item $hooksJsonPath "$hooksJsonPath.bak-$stamp" -Force
        $cfg.PSObject.Properties.Remove('conductor-commit-gate')
        $cfg | ConvertTo-Json -Depth 20 | Set-Content $hooksJsonPath -Encoding utf8
        Write-Output "retired gate hook removed from $hooksJsonPath (backup: hooks.json.bak-$stamp)"
    }
}
Write-Output 'Done. Restart the Antigravity agent session in this workspace to pick up the rule.'
