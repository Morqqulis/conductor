# Conductor commit gate — Cursor adapter (beforeShellExecution hook).
# Same protocol as the Claude Code layer (runtime/hooks/pre-commit-gate.ps1) and the
# git-native layer (runtime/git-hooks/): a `git commit` requires a fresh (<=30 min)
# single-use marker at `git rev-parse --git-path conductor-verified`; --no-verify in any
# accepted spelling and core.hooksPath overrides are denied outright. When the git-native
# gate is installed in the repo, this hook only checks (post-commit consumes); otherwise
# it consumes the marker itself. Fail-open by design: an internal error allows the command
# (a broken gate must not brick the whole terminal - this hook fires on EVERY shell
# command), but failures are reported to stderr. Cursor contract (cursor.com/docs/hooks):
# stdin JSON with snake_case fields incl. command/cwd; stdout {"permission":...,
# "agent_message":..., "user_message":...}; exit 0 means "use the JSON output".
function Out-Decision([string]$permission, [string]$agentMsg, [string]$userMsg) {
    $o = [ordered]@{ permission = $permission }
    if ($agentMsg) { $o['agent_message'] = $agentMsg }
    if ($userMsg) { $o['user_message'] = $userMsg }
    [Console]::Out.Write(($o | ConvertTo-Json -Compress))
}
try {
    # Explicit UTF-8 both directions: a headless PowerShell defaults to the OEM codepage
    # and corrupts non-ASCII repo paths (e.g. Cyrillic dirs) in stdin and git output.
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $raw = (New-Object System.IO.StreamReader([Console]::OpenStandardInput(), (New-Object System.Text.UTF8Encoding($false)))).ReadToEnd()
    if (-not $raw) { Out-Decision 'allow'; exit 0 }
    $evt = $raw | ConvertFrom-Json
    $cmd = $evt.command
    if (-not $cmd) { Out-Decision 'allow'; exit 0 }

    # Strip quoted segments (flags inside commit messages must not deny; `git commit`
    # inside quoted text must not consume), then evaluate each shell segment on its own.
    $scan = ($cmd -replace '"[^"]*"', ' ') -replace "'[^']*'", ' '
    $deny = $null
    $realCommit = $false
    foreach ($seg in [regex]::Split($scan, '[;&|\r\n]')) {
        if ($seg -notmatch '(^|[\s(\\/])git(\.exe)?(\s+\S+)*?\s+commit(\s|$|\))') { continue }
        if ($seg -match '(^|\s)--dry-run(\s|$|\))') { continue }   # runs no hooks, commits nothing
        $realCommit = $true
        if ($seg -match '(^|\s)(--no-ver\w*|-[a-zA-Z]*n[a-zA-Z]*)(\s|$|\))') {
            $deny = 'Conductor commit gate: --no-verify (in any spelling, including bundled short flags like -nm) is forbidden - it bypasses the git-native gate. Commit without the flag; a failing pre-commit hook is a signal to fix, not to skip. User override in the current conversation lifts this rule.'
            break
        }
        if ($seg -match '(?i)core\.hookspath|--config-env') {
            $deny = 'Conductor commit gate: overriding core.hooksPath on a commit command is forbidden - it disables the git-native gate. Commit without the override. User override in the current conversation lifts this rule.'
            break
        }
    }
    if ($deny) { Out-Decision 'deny' $deny 'Conductor gate blocked this commit command.'; exit 0 }
    if (-not $realCommit) { Out-Decision 'allow'; exit 0 }

    $cwd = $evt.cwd
    if (-not $cwd -and $evt.workspace_roots) { $cwd = @($evt.workspace_roots)[0] }
    if (-not $cwd) { Out-Decision 'allow'; exit 0 }
    $marker = git -C $cwd rev-parse --path-format=absolute --git-path conductor-verified 2>$null
    if (-not $marker) {
        [Console]::Error.WriteLine("conductor cursor gate: marker path not resolvable from cwd '$cwd' (fail-open)")
        Out-Decision 'allow'
        exit 0
    }
    $ok = $false
    if (Test-Path $marker) {
        $age = (Get-Date).ToUniversalTime() - (Get-Item $marker).LastWriteTimeUtc
        if ($age.TotalMinutes -lt 30) { $ok = $true }
    }
    if ($ok) {
        # With the git-native gate installed, post-commit consumes at the true commit
        # point; without it this hook is the single consumer (one marker per command).
        $gateHookPath = git -C $cwd rev-parse --path-format=absolute --git-path hooks/pre-commit 2>$null
        $gateInstalled = $gateHookPath -and (Test-Path $gateHookPath) -and ((Get-Content $gateHookPath -Raw) -match 'conductor gate')
        if (-not $gateInstalled) {
            Remove-Item $marker -Force -ErrorAction SilentlyContinue
        }
        Out-Decision 'allow'
        exit 0
    }
    $reason = "Conductor commit gate: no fresh verification marker. Run the proving command (read its full output), then create the single-use marker in a SEPARATE command and retry the commit. PowerShell: New-Item -Force -ItemType File `"$marker`" | Out-Null ; bash: touch `"$marker`". User override in the current conversation lifts this gate (create the marker and say so)."
    Out-Decision 'deny' $reason 'Conductor gate: commit without a fresh verification marker.'
    exit 0
} catch {
    [Console]::Error.WriteLine("conductor cursor gate error (fail-open): $($_.Exception.Message)")
    Out-Decision 'allow'
    exit 0
}
