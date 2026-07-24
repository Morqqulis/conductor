param(
    [switch]$SkipGlobalClaudeMd,
    [switch]$KeepSuperpowers
)
$ErrorActionPreference = 'Stop'
$repo = $PSScriptRoot
$claudeHome = Join-Path $env:USERPROFILE '.claude'
$conductorDir = Join-Path $claudeHome 'conductor'
$settingsPath = Join-Path $claudeHome 'settings.json'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'

Write-Output '=== Conductor installer ==='

# 1. Runtime tree -> ~/.claude/conductor
if (-not (Test-Path (Join-Path $repo 'runtime\core.md'))) { throw "run this script from the conductor repo root (runtime\core.md not found next to install.ps1)" }
New-Item -ItemType Directory -Force $conductorDir | Out-Null
Copy-Item (Join-Path $repo 'runtime\*') $conductorDir -Recurse -Force
# Retired marker-gate artifacts from older versions: remove from the live tree if present.
foreach ($stale in @('hooks\pre-commit-gate.ps1', 'git-hooks', 'git-template',
                     'adapters\cursor\gate.ps1', 'adapters\antigravity\gate.ps1')) {
    $p = Join-Path $conductorDir $stale
    if (Test-Path $p) { Remove-Item $p -Recurse -Force }
}
Write-Output "[1/5] runtime tree -> $conductorDir (retired gate artifacts cleaned)"

# 2. Hooks -> settings.json (backup, REPLACE any prior conductor entries, add fresh)
# Hook commands use FORWARD slashes: Claude Code runs hook commands through bash on Windows,
# and bash eats backslashes ('C:\Users\...' arrives as 'C:Users...'). pwsh accepts C:/... fine.
if (Test-Path $settingsPath) {
    Copy-Item $settingsPath "$settingsPath.bak-$stamp" -Force
    $settings = Get-Content $settingsPath -Raw | ConvertFrom-Json
} else {
    $settings = [pscustomobject]@{}
}
$shell = if (Get-Command pwsh -ErrorAction SilentlyContinue) { 'pwsh' } else { 'powershell' }
$conductorFwd = $conductorDir -replace '\\', '/'
$sessionCmd  = "$shell -NoProfile -ExecutionPolicy Bypass -File $conductorFwd/hooks/session-start.ps1"
$lessonsCmd  = "$shell -NoProfile -ExecutionPolicy Bypass -File $conductorFwd/hooks/lessons-inject.ps1"
$subagentCmd = "$shell -NoProfile -ExecutionPolicy Bypass -File $conductorFwd/hooks/subagent-start.ps1"
$promptCmd   = "$shell -NoProfile -ExecutionPolicy Bypass -File $conductorFwd/hooks/user-prompt.ps1"
if (-not ($settings.PSObject.Properties.Name -contains 'hooks')) {
    $settings | Add-Member -NotePropertyName hooks -NotePropertyValue ([pscustomobject]@{})
}
$sessionEntry  = [pscustomobject]@{ matcher = 'startup|resume|clear|compact'; hooks = @(
    [pscustomobject]@{ type = 'command'; command = $sessionCmd; timeout = 10 },
    [pscustomobject]@{ type = 'command'; command = $lessonsCmd; timeout = 10 }
) }
$subagentEntry = [pscustomobject]@{ hooks = @([pscustomobject]@{ type = 'command'; command = $subagentCmd; timeout = 10 }) }
$promptEntry   = [pscustomobject]@{ hooks = @([pscustomobject]@{ type = 'command'; command = $promptCmd; timeout = 10 }) }
foreach ($pair in @(@('SessionStart', $sessionEntry), @('SubagentStart', $subagentEntry), @('UserPromptSubmit', $promptEntry))) {
    $name = $pair[0]; $entry = $pair[1]
    $kept = @()
    if ($settings.hooks.PSObject.Properties.Name -contains $name) {
        $kept = @($settings.hooks.$name) | Where-Object { ($_ | ConvertTo-Json -Depth 20) -notmatch 'conductor' }
        $settings.hooks.PSObject.Properties.Remove($name)
    }
    $settings.hooks | Add-Member -NotePropertyName $name -NotePropertyValue (@($kept) + $entry)
}
# Retired commit-gate cleanup: strip any conductor PreToolUse entry left by older versions.
if ($settings.hooks.PSObject.Properties.Name -contains 'PreToolUse') {
    $keptPre = @($settings.hooks.PreToolUse) | Where-Object { ($_ | ConvertTo-Json -Depth 20) -notmatch 'conductor' }
    $settings.hooks.PSObject.Properties.Remove('PreToolUse')
    if (@($keptPre).Count -gt 0) {
        $settings.hooks | Add-Member -NotePropertyName PreToolUse -NotePropertyValue @($keptPre)
    }
}
$settings | ConvertTo-Json -Depth 20 | Set-Content $settingsPath -Encoding utf8
Write-Output "[2/5] hooks registered (forward-slash paths; backup: settings.json.bak-$stamp)"

# 3. Global CLAUDE.md
if ($SkipGlobalClaudeMd) {
    Write-Output '[3/5] global CLAUDE.md skipped (flag)'
} else {
    $globalMd = Join-Path $claudeHome 'CLAUDE.md'
    if (Test-Path $globalMd) { Copy-Item $globalMd "$globalMd.bak-$stamp" -Force }
    Copy-Item (Join-Path $repo 'deploy\global-CLAUDE.md') $globalMd -Force
    Write-Output "[3/5] global CLAUDE.md installed (backup: CLAUDE.md.bak-$stamp)"
}

# 4. Disable superpowers (double-mandate prevention)
if ($KeepSuperpowers) {
    Write-Output '[4/5] superpowers left enabled (flag) - WARNING: two process systems will conflict'
} else {
    $disabled = $false
    try {
        claude plugin disable superpowers@claude-plugins-official 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) { $disabled = $true }
    } catch {}
    if (-not $disabled) {
        try {
            $s = Get-Content $settingsPath -Raw | ConvertFrom-Json
            if ($s.PSObject.Properties.Name -contains 'enabledPlugins' -and
                $s.enabledPlugins.PSObject.Properties.Name -contains 'superpowers@claude-plugins-official') {
                $s.enabledPlugins.'superpowers@claude-plugins-official' = $false
                $s | ConvertTo-Json -Depth 20 | Set-Content $settingsPath -Encoding utf8
                $disabled = $true
            }
        } catch {}
    }
    if ($disabled) { Write-Output '[4/5] superpowers disabled' }
    else { Write-Output '[4/5] WARNING: could not disable superpowers automatically - run: claude plugin disable superpowers@claude-plugins-official' }
}

# 5. Smoke test: hook emits valid payload with sentinel, invoked the same way the harness does
$out = & $shell -NoProfile -ExecutionPolicy Bypass -File "$conductorFwd/hooks/session-start.ps1"
$ok = $false
try { $ok = (($out | ConvertFrom-Json).hookSpecificOutput.additionalContext -match 'CONDUCTOR-CORE-v1-7f3a') } catch {}
if ($ok) { Write-Output "[5/5] smoke test PASS (payload $($out.Length)/10000 chars)" }
else { throw '[5/5] smoke test FAILED - hook did not emit the core sentinel' }

Write-Output ''
Write-Output 'Done. Open a NEW Claude Code session - Conductor announces itself as: "Conductor: <type> | T<n>"'
