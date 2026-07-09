# Installs Conductor GLOBALLY for Cursor and Antigravity (Claude Code is already global
# via install.ps1). What it does:
#   1. Deploys the adapter gate scripts to ~/.claude/conductor/adapters/<tool>/gate.ps1
#      (stable absolute paths for global hook configs).
#   2. Cursor:      merges a beforeShellExecution entry into ~/.cursor/hooks.json.
#                   The global RULE cannot be a file - paste the digest once into
#                   Cursor Settings -> Rules (this script prints the source path).
#   3. Antigravity: merges the conductor-commit-gate block into ~/.gemini/config/hooks.json
#                   and installs the digest as ~/.gemini/AGENTS.md (global rules file;
#                   your personal ~/.gemini/GEMINI.md is NOT touched).
# The git-native layer stays per-repository BY DESIGN (a global core.hooksPath would
# silently disable repos' own hooks): run install-git-gate.ps1 -Repo <path> per project.
# Idempotent; every modified config is backed up with a timestamp first.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$shell = if (Get-Command pwsh -ErrorAction SilentlyContinue) { 'pwsh' } else { 'powershell' }

foreach ($f in @('adapters\cursor\gate.ps1', 'adapters\antigravity\gate.ps1', 'adapters\antigravity\conductor-core.md', 'adapters\cursor\conductor-core.mdc')) {
    if (-not (Test-Path (Join-Path $PSScriptRoot $f))) { throw "adapter source not found: $f - run from the conductor repo root" }
}

# 1. Deploy gate scripts to stable locations
$deployRoot = Join-Path $env:USERPROFILE '.claude\conductor\adapters'
foreach ($tool in @('cursor', 'antigravity')) {
    $dir = Join-Path $deployRoot $tool
    New-Item -ItemType Directory -Force $dir | Out-Null
    Copy-Item (Join-Path $PSScriptRoot "adapters\$tool\gate.ps1") (Join-Path $dir 'gate.ps1') -Force
}
Write-Output "[1/4] gate scripts deployed -> $deployRoot\{cursor,antigravity}\gate.ps1"

# 2. Cursor: global hooks.json
$cursorGate = Join-Path $deployRoot 'cursor\gate.ps1'
$cursorEntry = [pscustomobject]@{ command = "$shell -NoProfile -ExecutionPolicy Bypass -File `"$cursorGate`""; timeout = 10 }
$cursorHooks = Join-Path $env:USERPROFILE '.cursor\hooks.json'
New-Item -ItemType Directory -Force (Split-Path $cursorHooks) | Out-Null
if (Test-Path $cursorHooks) {
    Copy-Item $cursorHooks "$cursorHooks.bak-$stamp" -Force
    $cfg = Get-Content $cursorHooks -Raw | ConvertFrom-Json
    if (-not ($cfg.PSObject.Properties.Name -contains 'hooks')) { $cfg | Add-Member -NotePropertyName hooks -NotePropertyValue ([pscustomobject]@{}) }
    $kept = @()
    if ($cfg.hooks.PSObject.Properties.Name -contains 'beforeShellExecution') {
        $kept = @($cfg.hooks.beforeShellExecution) | Where-Object { ($_ | ConvertTo-Json -Depth 10) -notmatch 'conductor' }
        $cfg.hooks.PSObject.Properties.Remove('beforeShellExecution')
    }
    $cfg.hooks | Add-Member -NotePropertyName beforeShellExecution -NotePropertyValue (@($kept) + $cursorEntry)
    if (-not ($cfg.PSObject.Properties.Name -contains 'version')) { $cfg | Add-Member -NotePropertyName version -NotePropertyValue 1 }
} else {
    $cfg = [pscustomobject]@{ version = 1; hooks = [pscustomobject]@{ beforeShellExecution = @($cursorEntry) } }
}
$cfg | ConvertTo-Json -Depth 20 | Set-Content $cursorHooks -Encoding utf8
Write-Output "[2/4] Cursor global hook -> $cursorHooks"
Write-Output "      Cursor global RULE: paste the body of adapters\cursor\conductor-core.mdc"
Write-Output "      once into Cursor Settings -> Rules (no global rules file exists in Cursor)."

# 3. Antigravity: global hooks.json + global AGENTS.md digest
$agGate = Join-Path $deployRoot 'antigravity\gate.ps1'
$agBlock = [pscustomobject]@{
    PreToolUse = @(
        [pscustomobject]@{
            matcher = 'run_command'
            hooks = @([pscustomobject]@{ type = 'command'; command = "$shell -NoProfile -ExecutionPolicy Bypass -File `"$agGate`""; timeout = 30 })
        }
    )
}
$agHooks = Join-Path $env:USERPROFILE '.gemini\config\hooks.json'
New-Item -ItemType Directory -Force (Split-Path $agHooks) | Out-Null
if (Test-Path $agHooks) {
    Copy-Item $agHooks "$agHooks.bak-$stamp" -Force
    $cfg = Get-Content $agHooks -Raw | ConvertFrom-Json
    if ($cfg.PSObject.Properties.Name -contains 'conductor-commit-gate') { $cfg.PSObject.Properties.Remove('conductor-commit-gate') }
    $cfg | Add-Member -NotePropertyName 'conductor-commit-gate' -NotePropertyValue $agBlock
} else {
    $cfg = [pscustomobject]@{ 'conductor-commit-gate' = $agBlock }
}
$cfg | ConvertTo-Json -Depth 20 | Set-Content $agHooks -Encoding utf8
Write-Output "[3/4] Antigravity global hook -> $agHooks"

$digestSrc = Get-Content (Join-Path $PSScriptRoot 'adapters\antigravity\conductor-core.md') -Raw
$bodyStart = $digestSrc.IndexOf('## Iron laws')
if ($bodyStart -lt 0) { throw 'digest body marker "## Iron laws" not found in adapters\antigravity\conductor-core.md' }
$agentsMd = "# Conductor Core (global rules)`n`n" + $digestSrc.Substring($bodyStart)
$agentsPath = Join-Path $env:USERPROFILE '.gemini\AGENTS.md'
if (Test-Path $agentsPath) { Copy-Item $agentsPath "$agentsPath.bak-$stamp" -Force }
[IO.File]::WriteAllText($agentsPath, $agentsMd, (New-Object System.Text.UTF8Encoding($false)))
Write-Output "[4/4] Antigravity global rules -> $agentsPath (GEMINI.md untouched)"

Write-Output ''
Write-Output 'Done. Restart Cursor and Antigravity to pick up global hooks.'
Write-Output 'Git-native layer stays per-repo: install-git-gate.ps1 -Repo <path> for each project.'
