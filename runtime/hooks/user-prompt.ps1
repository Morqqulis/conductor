try {
    $payload = @{ hookSpecificOutput = @{ hookEventName = 'UserPromptSubmit'; additionalContext = '[Conductor active] Step 0 before responding; gates and counters in force; state lives in the conductor todo entry.' } } | ConvertTo-Json -Depth 3 -Compress
    [Console]::Out.Write($payload)
    exit 0
} catch {
    exit 0
}
