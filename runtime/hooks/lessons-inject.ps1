# Conductor lessons injector (SessionStart, second hook entry): emits the TOP of the
# lessons ledger as its own additionalContext payload - separate from the core payload,
# which sits ~550 chars under the 10000-char truncation limit and cannot host lessons.
# Cost model: <=10 lines, hard 3000-char cap, once per session start - not per message.
# The ledger lives OUTSIDE the runtime tree (~/.claude/conductor/lessons.md) so installs
# and syncs never clobber accumulated lessons. Missing or empty ledger -> silent exit.
$ErrorActionPreference = 'Stop'
try {
    $ledger = Join-Path $env:USERPROFILE '.claude\conductor\lessons.md'
    if (-not (Test-Path -LiteralPath $ledger)) { exit 0 }
    $lines = @([IO.File]::ReadAllLines($ledger, [System.Text.Encoding]::UTF8) |
        Where-Object { $_.Trim() -and $_ -notmatch '^#' } | Select-Object -First 10)
    if ($lines.Count -eq 0) { exit 0 }
    $head = 'CONDUCTOR LESSONS (top of ~/.claude/conductor/lessons.md). Capture rule: a falsified hypothesis, a refuted skeptic claim, or a gate-caught real bug -> append ONE line "date | trigger | rule". Over 20 lines -> distill: generalize, graduate stable rules into playbooks via the repo cycle, trim here.'
    $block = $head + "`n" + ($lines -join "`n")
    if ($block.Length -gt 3000) { $block = $block.Substring(0, 3000) }
    $payload = @{ hookSpecificOutput = @{ hookEventName = 'SessionStart'; additionalContext = $block } } | ConvertTo-Json -Depth 3 -Compress
    [Console]::Out.Write($payload)
    exit 0
} catch {
    [Console]::Error.WriteLine("conductor lessons hook error (fail-open): $($_.Exception.Message)")
    exit 0
}
