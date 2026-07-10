$ErrorActionPreference = 'Stop'
$fail = @()
$root = Join-Path $PSScriptRoot '..\runtime'
function Check($cond, $msg) { if (-not $cond) { $script:fail += $msg } }

$core = [System.IO.File]::ReadAllText("$root\core.md", [System.Text.Encoding]::UTF8)
$payload = @{ hookSpecificOutput = @{ hookEventName = 'SessionStart'; additionalContext = $core } } | ConvertTo-Json -Depth 3 -Compress
Check ($payload.Length -le 9500) "core.md escaped payload over budget: $($payload.Length)/9500 chars (harness truncates at 10000)"
Check ($core -match 'CONDUCTOR-CORE-v1-7f3a') "core.md missing sentinel"
$contract = [System.IO.File]::ReadAllText("$root\subagent-contract.md", [System.Text.Encoding]::UTF8)
Check ($contract.Length -le 2500) "contract over budget: $($contract.Length)/2500"
Check ($contract -match 'CONDUCTOR-SUB-v1') "contract missing sentinel"

$budgets = @{ 'debugging.md'=6000; 'implementing.md'=6000; 'investigating.md'=6000; 'orchestration.md'=6000; 'skeptic.md'=6000; 'distill.md'=3000 }
foreach ($name in $budgets.Keys) {
    $p = "$root\playbooks\$name"
    Check (Test-Path $p) "missing playbook $name"
    if (Test-Path $p) {
        $len = ([System.IO.File]::ReadAllText($p)).Length
        Check ($len -le $budgets[$name]) "$name over budget: $len/$($budgets[$name])"
        # wired = reachable from an injected surface: core.md (always in context) or a
        # session hook payload (injected when its trigger fires, e.g. distill.md via the
        # lessons hook's DISTILL DUE line)
        $hookTexts = (Get-ChildItem "$root\hooks\*.ps1" | ForEach-Object { [System.IO.File]::ReadAllText($_.FullName) }) -join "`n"
        Check (($core -match [regex]::Escape($name)) -or ($hookTexts -match [regex]::Escape($name))) "dead wiring: $name not referenced from core.md or any hook payload"
    }
}
$probes = [System.IO.File]::ReadAllText("$root\snippets\probes.md")
Check ($probes.Length -le 3200) "probes.md over budget: $($probes.Length)/3200"

$blacklist = 'TBD','TODO','add appropriate','fill in','similar to'
Get-ChildItem $root -Recurse -Include *.md | ForEach-Object {
    $t = [System.IO.File]::ReadAllText($_.FullName)
    foreach ($b in $blacklist) { Check ($t -cnotmatch [regex]::Escape($b)) "placeholder '$b' in $($_.Name)" }
}
foreach ($f in @("$root\core.md","$root\subagent-contract.md")) {
    $t = [System.IO.File]::ReadAllText($f)
    Check ($t -match 'DONE_WITH_CONCERNS' -and $t -match 'NEEDS_CONTEXT') "status tokens incomplete in $f"
}
if ($fail) { $fail | ForEach-Object { Write-Output "FAIL: $_" }; exit 1 }
Write-Output 'lint: PASS'; exit 0
