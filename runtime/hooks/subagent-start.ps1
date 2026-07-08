$ErrorActionPreference = 'Stop'
$contractPath = Join-Path $env:USERPROFILE '.claude\conductor\subagent-contract.md'
try {
    if (-not (Test-Path -LiteralPath $contractPath)) { throw "subagent-contract.md not found at $contractPath" }
    $contract = [System.IO.File]::ReadAllText($contractPath, [System.Text.Encoding]::UTF8)
    if ($contract.Length -gt 2500) {
        [Console]::Error.WriteLine("conductor: subagent-contract.md is $($contract.Length) chars (>2500)")
    }
    $payload = @{ hookSpecificOutput = @{ hookEventName = 'SubagentStart'; additionalContext = $contract } } | ConvertTo-Json -Depth 3 -Compress
    [Console]::Out.Write($payload)
    exit 0
} catch {
    [Console]::Error.WriteLine("conductor SubagentStart hook FAILED: $($_.Exception.Message)")
    exit 1
}
