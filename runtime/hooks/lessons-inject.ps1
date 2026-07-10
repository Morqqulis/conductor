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
    $all = @([IO.File]::ReadAllLines($ledger, [System.Text.Encoding]::UTF8) |
        Where-Object { $_.Trim() -and $_ -notmatch '^\s*#' })
    if ($all.Count -eq 0) { exit 0 }
    $lines = @($all | Select-Object -First 10)
    $head = 'CONDUCTOR LESSONS (top of ~/.claude/conductor/lessons.md). Capture rule: a falsified hypothesis, a refuted skeptic claim, or a gate-caught real bug -> append ONE line "date | trigger | rule".'
    if ($all.Count -gt 20) {
        $head = "DISTILL DUE: the ledger holds $($all.Count) lessons (>20) - lines past the injection cap are silently invisible. Run the distillation procedure (playbooks/distill.md, deployed at ~/.claude/conductor/playbooks/distill.md) as a maintenance unit BEFORE new feature work.`n" + $head
    }
    $block = $head + "`n" + ($lines -join "`n")
    if ($block.Length -gt 3000) { $block = $block.Substring(0, 3000) }
    $payload = @{ hookSpecificOutput = @{ hookEventName = 'SessionStart'; additionalContext = $block } } | ConvertTo-Json -Depth 3 -Compress
    [Console]::Out.Write($payload)
    exit 0
} catch {
    [Console]::Error.WriteLine("conductor lessons hook error (fail-open): $($_.Exception.Message)")
    exit 0
}
