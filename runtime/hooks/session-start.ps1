$ErrorActionPreference = 'Stop'
$corePath = Join-Path $env:USERPROFILE '.claude\conductor\core.md'
try {
    if (-not (Test-Path -LiteralPath $corePath)) { throw "core.md not found at $corePath" }
    $core = [System.IO.File]::ReadAllText($corePath, [System.Text.Encoding]::UTF8)
    $payload = @{ hookSpecificOutput = @{ hookEventName = 'SessionStart'; additionalContext = $core } } | ConvertTo-Json -Depth 3 -Compress
    if ($payload.Length -gt 10000) {
        throw "escaped payload is $($payload.Length) chars (>10000) - harness would silently truncate the core; refusing to emit a gutted core"
    }
    if ($payload.Length -gt 9500) {
        [Console]::Error.WriteLine("conductor: escaped payload $($payload.Length)/10000 chars - approaching truncation limit")
    }
    [Console]::Out.Write($payload)
    exit 0
} catch {
    [Console]::Error.WriteLine("conductor SessionStart hook FAILED: $($_.Exception.Message)")
    exit 1
}
