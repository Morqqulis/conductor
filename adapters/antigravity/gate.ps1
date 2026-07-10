# Conductor commit gate — Antigravity adapter (PreToolUse hook, matcher run_command).
# Same protocol as the Claude Code and Cursor layers and the git-native layer: a
# `git commit` requires a fresh (<=30 min) single-use marker at
# `git rev-parse --git-path conductor-verified`; --no-verify in any accepted spelling and
# core.hooksPath overrides are denied outright. When the git-native gate is installed in
# the repo, this hook only checks (post-commit consumes); otherwise it consumes the
# marker itself. Fail-open by design: an internal error allows the command, reported to
# stderr. Response schema is protobuf-backed (verified from agy.exe struct tags):
# {"allow_tool": bool, "deny_reason": string} — EXACTLY these fields, protobuf JSON
# parsing may reject unknown ones. Command text arrives at toolCall.args.CommandLine
# (fallbacks below cover schema variants seen in the binary). Exit 0 always, even on deny.
$dbgLog = Join-Path $env:LOCALAPPDATA 'conductor\antigravity-gate-debug.log'
try {
    New-Item -ItemType Directory -Force (Split-Path $dbgLog) | Out-Null
    if ((Test-Path $dbgLog) -and ((Get-Item $dbgLog).Length -gt 1MB)) { Clear-Content $dbgLog }   # cap: fires per matched tool call
    Add-Content -Path $dbgLog -Value "=== invoked $((Get-Date).ToUniversalTime().ToString('o')) ==="
} catch {}
# Auto-installs the git-native gate (pre-commit + post-commit from
# ~/.claude/conductor/git-hooks) into the repo on first commit contact - zero-friction
# rollout across all repositories, approved by the user 2026-07-10. post-commit goes in
# FIRST so a partial install can never enable the check without its marker consumer.
function Ensure-GitGate([string]$repoCwd) {
    try {
        $pre = git -C $repoCwd rev-parse --path-format=absolute --git-path hooks/pre-commit 2>$null
        if (-not $pre) { return $false }
        # Fast path checks ALL FOUR sentinels explicitly - a subset invariant was refuted
        # by a measured counter-probe (partial deletions/aborted heals break clever orders).
        $complete = $true
        foreach ($n in @('post-commit', 'post-merge', 'pre-merge-commit', 'pre-commit')) {
            $p = git -C $repoCwd rev-parse --path-format=absolute --git-path "hooks/$n" 2>$null
            if (-not ($p -and (Test-Path $p) -and ((Get-Content $p -Raw) -match 'conductor gate'))) { $complete = $false; break }
        }
        if ($complete) { return $true }
        if (git -C $repoCwd config --get core.hooksPath 2>$null) {
            [Console]::Error.WriteLine('conductor gate: core.hooksPath is set, auto-install skipped')
            return $false
        }
        $srcDir = Join-Path $env:USERPROFILE '.claude\conductor\git-hooks'
        foreach ($name in @('post-commit', 'post-merge', 'pre-merge-commit', 'pre-commit')) {
            $src = Join-Path $srcDir $name
            if (-not (Test-Path $src)) { return $false }
            $content = ([IO.File]::ReadAllText($src)) -replace "`r`n", "`n"
            if ($content -notmatch 'conductor gate') { return $false }
            $target = git -C $repoCwd rev-parse --path-format=absolute --git-path "hooks/$name" 2>$null
            if (-not $target) { return $false }
            New-Item -ItemType Directory -Force (Split-Path $target) | Out-Null
            if ((Test-Path $target) -and ((Get-Content $target -Raw) -notmatch 'conductor gate')) {
                if (Test-Path "$target.pre-conductor") {
                    [Console]::Error.WriteLine("conductor gate: $name backup already exists, auto-install skipped")
                    return $false
                }
                Move-Item $target "$target.pre-conductor"
            }
            [IO.File]::WriteAllText($target, $content, (New-Object System.Text.UTF8Encoding($false)))
            if ($IsLinux -or $IsMacOS) { & chmod +x $target 2>$null }
        }
        [Console]::Error.WriteLine("conductor gate: git hooks auto-installed for $repoCwd")
        return $true
    } catch {
        [Console]::Error.WriteLine("conductor gate: auto-install failed (fail-open): $($_.Exception.Message)")
        return $false
    }
}
function Out-Decision([bool]$allow, [string]$reason) {
    if ($allow) { [Console]::Out.Write('{"allow_tool":true}') }
    else {
        $o = @{ allow_tool = $false; deny_reason = $reason } | ConvertTo-Json -Compress
        [Console]::Out.Write($o)
    }
}
try {
    # Explicit UTF-8 both directions: a headless PowerShell defaults to the OEM codepage
    # and corrupts non-ASCII repo paths (e.g. Cyrillic dirs) in stdin and git output.
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $raw = (New-Object System.IO.StreamReader([Console]::OpenStandardInput(), (New-Object System.Text.UTF8Encoding($false)))).ReadToEnd()
    try { Add-Content -Path $dbgLog -Value "raw: $raw" } catch {}
    if (-not $raw) { Out-Decision $true; exit 0 }
    $evt = $raw | ConvertFrom-Json
    $cmd = $null
    foreach ($candidate in @(
        { $evt.toolCall.args.CommandLine },
        { $evt.toolCall.args.command_line },
        { $evt.tool_call.args.CommandLine },
        { $evt.tool_input.command },
        { $evt.args.CommandLine },
        { $evt.command }
    )) {
        try { $v = & $candidate } catch { $v = $null }
        if ($v) { $cmd = $v; break }
    }
    if (-not $cmd) { Out-Decision $true; exit 0 }

    # Strip quoted segments (flags inside commit messages must not deny; `git commit`
    # inside quoted text must not consume), then evaluate each shell segment on its own.
    $scan = ($cmd -replace '"[^"]*"', ' ') -replace "'[^']*'", ' '
    $deny = $null
    $realCommit = $false
    foreach ($seg in [regex]::Split($scan, '[;&|\r\n]')) {
        if ($seg -notmatch '(^|[\s(\\/])git(\.exe)?(\s+\S+)*?\s+(commit|merge|revert|cherry-pick)(\s|$|\))') { continue }
        if ($seg -match '(^|\s)--(dry-run|abort|quit|continue)(\s|$|\))') { continue }   # inert, or finishing an operation the gate already admitted
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
    if ($deny) { Out-Decision $false $deny; exit 0 }
    if (-not $realCommit) { Out-Decision $true; exit 0 }

    $cwd = $evt.cwd
    if (-not $cwd -and $evt.workspacePaths) { $cwd = @($evt.workspacePaths)[0] }
    if (-not $cwd -and $evt.workspace_paths) { $cwd = @($evt.workspace_paths)[0] }
    if (-not $cwd) { Out-Decision $true; exit 0 }
    $marker = git -C $cwd rev-parse --path-format=absolute --git-path conductor-verified 2>$null
    if (-not $marker) {
        [Console]::Error.WriteLine("conductor antigravity gate: marker path not resolvable from cwd '$cwd' (fail-open)")
        Out-Decision $true
        exit 0
    }
    $ok = $false
    if (Test-Path $marker) {
        $age = (Get-Date).ToUniversalTime() - (Get-Item $marker).LastWriteTimeUtc
        if ($age.TotalMinutes -lt 30) { $ok = $true }
    }
    $gateInstalled = Ensure-GitGate $cwd
    if ($ok) {
        # With the git-native gate installed, post-commit consumes at the true commit
        # point; without it this hook is the single consumer (one marker per command).
        if (-not $gateInstalled) {
            Remove-Item $marker -Force -ErrorAction SilentlyContinue
        }
        Out-Decision $true
        exit 0
    }
    $reason = "Conductor commit gate: no fresh verification marker. Run the proving command (read its full output), then create the single-use marker in a SEPARATE command and retry the commit. PowerShell: New-Item -Force -ItemType File `"$marker`" | Out-Null ; bash: touch `"$marker`". User override in the current conversation lifts this gate (create the marker and say so)."
    Out-Decision $false $reason
    exit 0
} catch {
    [Console]::Error.WriteLine("conductor antigravity gate error (fail-open): $($_.Exception.Message)")
    Out-Decision $true
    exit 0
}
