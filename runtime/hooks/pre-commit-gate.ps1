# Conductor commit gate (harness layer, PreToolUse): a `git commit` tool command requires
# a fresh, single-use verification marker created by the model AFTER its proving run.
# Marker location comes from `git rev-parse --git-path` so it always matches the git-native
# layer (runtime/git-hooks/), including inside linked worktrees. When that git-native gate
# is installed, this hook only checks and the post-commit hook consumes; otherwise this
# hook consumes. Commit commands carrying --no-verify (any accepted spelling) or a
# core.hooksPath override are denied outright - they disable the git-native layer.
# Fail-open by design: any internal error allows the commit (a broken gate must not brick
# git), but failures are reported to stderr so they are visible. Text matching is
# best-effort by nature (runtime string construction or quoting `git commit` inside
# sh -c '...' evades it); the git-native layer remains the enforcer for those.
try {
    # A headless PowerShell defaults both console encodings to the OEM codepage, while the
    # harness pipes UTF-8 JSON and git prints UTF-8 paths - non-ASCII repo paths (e.g.
    # Cyrillic dirs) corrupt in both directions without explicit UTF-8.
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $raw = (New-Object System.IO.StreamReader([Console]::OpenStandardInput(), (New-Object System.Text.UTF8Encoding($false)))).ReadToEnd()
    if (-not $raw) { exit 0 }
    $evt = $raw | ConvertFrom-Json
    $cmd = $evt.tool_input.command
    if (-not $cmd) { exit 0 }

    # Strip quoted segments first: flags inside commit messages must not trigger denials,
    # and `git commit` mentioned inside quoted text must not consume a marker. Then split
    # on command separators - the commit detector and its flag checks are only valid
    # within one shell segment (an unrelated `-n`/`-not` elsewhere must not deny, and a
    # second commit hidden after `&&` must not escape scanning).
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
    if ($deny) {
        $payload = @{ hookSpecificOutput = @{ hookEventName = 'PreToolUse'; permissionDecision = 'deny'; permissionDecisionReason = $deny } } | ConvertTo-Json -Depth 3 -Compress
        [Console]::Out.Write($payload)
        exit 0
    }
    if (-not $realCommit) { exit 0 }

    $cwd = $evt.cwd
    if (-not $cwd) { exit 0 }
    $marker = git -C $cwd rev-parse --path-format=absolute --git-path conductor-verified 2>$null
    if (-not $marker) {
        [Console]::Error.WriteLine("conductor commit gate: marker path not resolvable from cwd '$cwd' (fail-open)")
        exit 0
    }
    $ok = $false
    if (Test-Path $marker) {
        $age = (Get-Date).ToUniversalTime() - (Get-Item $marker).LastWriteTimeUtc
        if ($age.TotalMinutes -lt 30) { $ok = $true }
    }
    if ($ok) {
        # With the git-native gate installed, post-commit consumes the marker at the true
        # commit point; consuming here too would starve it. Without it, this hook is the
        # single consumer (then one marker admits one COMMAND, not one commit - the
        # git-native layer is required for strict per-commit accounting).
        $gateHookPath = git -C $cwd rev-parse --path-format=absolute --git-path hooks/pre-commit 2>$null
        $gateInstalled = $gateHookPath -and (Test-Path $gateHookPath) -and ((Get-Content $gateHookPath -Raw) -match 'conductor gate')
        if (-not $gateInstalled) {
            Remove-Item $marker -Force -ErrorAction SilentlyContinue
        }
        exit 0
    }
    $reason = "Conductor commit gate: no fresh verification marker. Run the proving command (full output read), then create the single-use marker and retry the commit. PowerShell: New-Item -Force -ItemType File `"$marker`" | Out-Null ; bash: touch `"$marker`". User override in the current conversation lifts this gate (create the marker and say so)."
    $payload = @{ hookSpecificOutput = @{ hookEventName = 'PreToolUse'; permissionDecision = 'deny'; permissionDecisionReason = $reason } } | ConvertTo-Json -Depth 3 -Compress
    [Console]::Out.Write($payload)
    exit 0
} catch {
    [Console]::Error.WriteLine("conductor commit gate error (fail-open): $($_.Exception.Message)")
    exit 0
}
