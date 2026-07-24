# Installs Conductor GLOBALLY for Cursor, Antigravity and Codex (Claude Code is already
# global via install.ps1). What it does:
#   1. Cursor:      the global RULE cannot be a file - paste the digest once into
#                   Cursor Settings -> Rules (this script prints the source path).
#                   Any conductor commit-gate entry left in ~/.cursor/hooks.json by older
#                   versions is removed (the marker gate is retired).
#   2. Antigravity: installs the digest as ~/.gemini/AGENTS.md (global rules file;
#                   your personal ~/.gemini/GEMINI.md is NOT touched). Any conductor
#                   commit-gate entry left in ~/.gemini/config/hooks.json is removed.
#   3. Codex:       installs the digest as ~/.codex/AGENTS.md (head of Codex's
#                   instruction chain) with a session-start pointer at the shared
#                   lessons ledger (Codex has no injection hook - the rule pulls it).
#   4. Retires the git-template commit gate of older versions: unsets init.templateDir
#                   if it points at the conductor template.
# The commit discipline is textual now: "prove before commit" lives in the core and the
# digests, not in an enforcement hook (agents satisfied the marker ritually - see lessons).
# Idempotent; every modified config is backed up with a timestamp first.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'

foreach ($f in @('adapters\antigravity\conductor-core.md', 'adapters\cursor\conductor-core.mdc')) {
    if (-not (Test-Path (Join-Path $PSScriptRoot $f))) { throw "adapter source not found: $f - run from the conductor repo root" }
}

# 1. Cursor: rule pointer + retired-gate cleanup in global hooks.json
Write-Output "[1/5] Cursor global RULE: paste the body of adapters\cursor\conductor-core.mdc"
Write-Output "      once into Cursor Settings -> Rules (no global rules file exists in Cursor)."
$cursorHooks = Join-Path $env:USERPROFILE '.cursor\hooks.json'
if (Test-Path $cursorHooks) {
    $cfg = Get-Content $cursorHooks -Raw | ConvertFrom-Json
    if (($cfg.PSObject.Properties.Name -contains 'hooks') -and
        ($cfg.hooks.PSObject.Properties.Name -contains 'beforeShellExecution')) {
        $all = @($cfg.hooks.beforeShellExecution)
        $kept = @($all | Where-Object { ($_ | ConvertTo-Json -Depth 10) -notmatch 'conductor' })
        if ($kept.Count -ne $all.Count) {
            Copy-Item $cursorHooks "$cursorHooks.bak-$stamp" -Force
            $cfg.hooks.PSObject.Properties.Remove('beforeShellExecution')
            if ($kept.Count -gt 0) { $cfg.hooks | Add-Member -NotePropertyName beforeShellExecution -NotePropertyValue $kept }
            $cfg | ConvertTo-Json -Depth 20 | Set-Content $cursorHooks -Encoding utf8
            Write-Output "      retired conductor gate removed from $cursorHooks (backup: hooks.json.bak-$stamp)"
        }
    }
}

# 2. Antigravity: retired-gate cleanup in global hooks.json
$agHooks = Join-Path $env:USERPROFILE '.gemini\config\hooks.json'
if (Test-Path $agHooks) {
    $cfg = Get-Content $agHooks -Raw | ConvertFrom-Json
    if ($cfg.PSObject.Properties.Name -contains 'conductor-commit-gate') {
        Copy-Item $agHooks "$agHooks.bak-$stamp" -Force
        $cfg.PSObject.Properties.Remove('conductor-commit-gate')
        $cfg | ConvertTo-Json -Depth 20 | Set-Content $agHooks -Encoding utf8
        Write-Output "[2/5] retired conductor gate removed from $agHooks (backup: hooks.json.bak-$stamp)"
    } else {
        Write-Output "[2/5] Antigravity hooks.json clean (no conductor gate entry)"
    }
} else {
    Write-Output "[2/5] Antigravity hooks.json absent - nothing to clean"
}

# 3. Antigravity: global AGENTS.md digest
$digestSrc = Get-Content (Join-Path $PSScriptRoot 'adapters\antigravity\conductor-core.md') -Raw
$bodyStart = $digestSrc.IndexOf('## Iron laws')
if ($bodyStart -lt 0) { throw 'digest body marker "## Iron laws" not found in adapters\antigravity\conductor-core.md' }
$agentsMd = "# Conductor Core (global rules)`n`n" + $digestSrc.Substring($bodyStart)
$agentsPath = Join-Path $env:USERPROFILE '.gemini\AGENTS.md'
if (Test-Path $agentsPath) { Copy-Item $agentsPath "$agentsPath.bak-$stamp" -Force }
[IO.File]::WriteAllText($agentsPath, $agentsMd, (New-Object System.Text.UTF8Encoding($false)))
Write-Output "[3/5] Antigravity global rules -> $agentsPath (GEMINI.md untouched)"

# 4. Codex: global AGENTS.md (head of the instruction chain, ~32 KiB cap - digest is ~9k).
# Codex has no session-injection hook, so the lessons ledger is pulled by instruction.
$codexDir = Join-Path $env:USERPROFILE '.codex'
New-Item -ItemType Directory -Force $codexDir | Out-Null
$codexMd = "# Conductor Core (global rules)`n`n" +
    "At session start, read the top 10 lines of ``~/.claude/conductor/lessons.md`` - the`n" +
    "lessons ledger shared by every AI tool on this machine. The capture rule below`n" +
    "appends new lessons to the same file.`n`n" +
    $digestSrc.Substring($bodyStart)
$codexPath = Join-Path $codexDir 'AGENTS.md'
if (Test-Path $codexPath) { Copy-Item $codexPath "$codexPath.bak-$stamp" -Force }
[IO.File]::WriteAllText($codexPath, $codexMd, (New-Object System.Text.UTF8Encoding($false)))
Write-Output "[4/5] Codex global rules -> $codexPath (prior file backed up if present)"

# 5. Retire the git-template gate of older versions
$tplRoot = Join-Path $env:USERPROFILE '.claude\conductor\git-template'
$existingTpl = git config --global --get init.templateDir
if ($existingTpl -and (($existingTpl -replace '/', '\') -eq $tplRoot)) {
    git config --global --unset init.templateDir
    Write-Output "[5/5] init.templateDir unset (was the conductor template - marker gate retired)"
} else {
    Write-Output "[5/5] init.templateDir untouched (not pointing at the conductor template)"
}
if (Test-Path $tplRoot) { Remove-Item $tplRoot -Recurse -Force }

Write-Output ''
Write-Output 'Done. Restart Cursor, Antigravity and Codex sessions to pick up rule changes.'
Write-Output 'Commit discipline is textual: prove before commit (core + digests), no marker file.'
