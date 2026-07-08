$ErrorActionPreference = 'Stop'
$corePath = Join-Path $env:USERPROFILE '.claude\conductor\core.md'
try {
    if (-not (Test-Path -LiteralPath $corePath)) { throw "core.md not found at $corePath" }
    $core = [System.IO.File]::ReadAllText($corePath, [System.Text.Encoding]::UTF8)
    if ($core.Length -gt 9500) {
        [Console]::Error.WriteLine("conductor: core.md is $($core.Length) chars (>9500); harness truncates at 10000")
    }
    $payload = @{ hookSpecificOutput = @{ hookEventName = 'SessionStart'; additionalContext = $core } } | ConvertTo-Json -Depth 3 -Compress
    [Console]::Out.Write($payload)
    exit 0
} catch {
    [Console]::Error.WriteLine("conductor SessionStart hook FAILED: $($_.Exception.Message)")
    exit 1
}
