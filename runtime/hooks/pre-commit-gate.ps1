# Conductor commit gate: a `git commit` tool call requires a fresh, single-use verification
# marker at <repo>/.git/conductor-verified (created by the model AFTER its proving run).
# Fail-open by design: any internal error allows the commit (a broken gate must not brick git),
# but failures are reported to stderr so they are visible.
try {
    $raw = [Console]::In.ReadToEnd()
    if (-not $raw) { exit 0 }
    $evt = $raw | ConvertFrom-Json
    $cmd = $evt.tool_input.command
    if (-not $cmd -or $cmd -notmatch 'git(\s+\S+)*\s+commit') { exit 0 }
    $cwd = $evt.cwd
    if (-not $cwd) { exit 0 }
    $root = git -C $cwd rev-parse --show-toplevel 2>$null
    if (-not $root) { exit 0 }
    $marker = Join-Path $root '.git/conductor-verified'
    $ok = $false
    if (Test-Path $marker) {
        $age = (Get-Date).ToUniversalTime() - (Get-Item $marker).LastWriteTimeUtc
        if ($age.TotalMinutes -lt 30) { $ok = $true }
    }
    if ($ok) {
        Remove-Item $marker -Force -ErrorAction SilentlyContinue   # single-use: each commit consumes one verification
        exit 0
    }
    $reason = 'Conductor commit gate: no fresh verification marker. Run the proving command (full output read), then create the single-use marker and retry the commit. PowerShell: New-Item -Force -ItemType File "<repo>\.git\conductor-verified" | Out-Null ; bash: touch "<repo>/.git/conductor-verified". User override in the current conversation lifts this gate (create the marker and say so).'
    $payload = @{ hookSpecificOutput = @{ hookEventName = 'PreToolUse'; permissionDecision = 'deny'; permissionDecisionReason = $reason } } | ConvertTo-Json -Depth 3 -Compress
    [Console]::Out.Write($payload)
    exit 0
} catch {
    [Console]::Error.WriteLine("conductor commit gate error (fail-open): $($_.Exception.Message)")
    exit 0
}
