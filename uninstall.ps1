# Removes Conductor from this machine, symmetric to the installers. Conservative by
# design: every touched config is backed up with a timestamp BEFORE modification; only
# artifacts carrying conductor sentinels are removed; foreign hooks/entries survive;
# your global CLAUDE.md is NEVER deleted (values, not machinery - backups are listed).
# Modes:
#   -WhatIf              dry run: print every planned action, change nothing
#   -KeepLessons         copy the lessons ledger to the Desktop before removal
#   -SweepRoots a,b,...  also remove git-gate hooks and project adapters from every
#                        repository found under these roots (depth 4)
# The repo folder itself and anything on GitHub are not touched.
param(
    [string[]]$SweepRoots = @(),
    [switch]$KeepLessons,
    [switch]$WhatIf
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
# pwsh -File binds "-SweepRoots a,b" as ONE string - split it back
$SweepRoots = @($SweepRoots | ForEach-Object { $_ -split ',' } | Where-Object { $_ })
# Anchored sentinel: 'conductor' as a path segment or our config keys - a bare substring
# match deleted a foreign 'semiconductor-lint' entry in skeptic testing
$sentinel = '[\\/]conductor[\\/]|conductor-commit-gate|conductor-core'

function Act([string]$desc, [scriptblock]$do) {
    if ($WhatIf) { Write-Host "[WHATIF] $desc" } else { & $do; Write-Host "[OK]     $desc" }
}

$hookNames = @('pre-commit', 'post-commit', 'pre-merge-commit', 'post-merge')

# --- 1. Claude Code: hooks out of settings.json, conductor dir gone -------------------
$settingsPath = Join-Path $env:USERPROFILE '.claude\settings.json'
if (Test-Path $settingsPath) {
    $settings = Get-Content $settingsPath -Raw | ConvertFrom-Json
    if (($settings.PSObject.Properties.Name -contains 'hooks') -and $settings.hooks -and
        (($settings.hooks | ConvertTo-Json -Depth 20) -match $sentinel)) {
        Act "settings.json: remove conductor hook entries (backup settings.json.bak-$stamp)" {
            Copy-Item $settingsPath "$settingsPath.bak-$stamp" -Force
            foreach ($ev in @($settings.hooks.PSObject.Properties.Name)) {
                $kept = @($settings.hooks.$ev) | Where-Object { ($_ | ConvertTo-Json -Depth 20) -notmatch $sentinel }
                $settings.hooks.PSObject.Properties.Remove($ev)
                if (@($kept).Count -gt 0) { $settings.hooks | Add-Member -NotePropertyName $ev -NotePropertyValue @($kept) }
            }
            $settings | ConvertTo-Json -Depth 20 | Set-Content $settingsPath -Encoding utf8
        }
    }
}
$conductorDir = Join-Path $env:USERPROFILE '.claude\conductor'
if (Test-Path $conductorDir) {
    $ledger = Join-Path $conductorDir 'lessons.md'
    if ($KeepLessons -and (Test-Path $ledger)) {
        Act "lessons ledger -> conductor-lessons-backup.md (Desktop or profile root)" {
            $desk = Join-Path $env:USERPROFILE 'Desktop'
            if (-not (Test-Path $desk)) { $desk = [Environment]::GetFolderPath('Desktop') }   # OneDrive redirect
            if (-not $desk -or -not (Test-Path $desk)) { $desk = $env:USERPROFILE }
            Copy-Item $ledger (Join-Path $desk 'conductor-lessons-backup.md') -Force
        }
    }
    Act "remove $conductorDir (runtime, adapters, git-template, ledger)" {
        Remove-Item $conductorDir -Recurse -Force
    }
}
$globalMd = Join-Path $env:USERPROFILE '.claude\CLAUDE.md'
if (Test-Path $globalMd) {
    $baks = @(Get-ChildItem "$globalMd.bak-*" -ErrorAction SilentlyContinue | Sort-Object Name)
    Write-Host "[NOTE]   global CLAUDE.md left in place (your values file). Backups: $(if ($baks) { $baks.Count } else { 'none' })$(if ($baks) { ', oldest = pre-conductor state: ' + $baks[0].Name })"
}

# --- 2. Cursor: global hook entry ------------------------------------------------------
$cursorHooks = Join-Path $env:USERPROFILE '.cursor\hooks.json'
if (Test-Path $cursorHooks) {
    $cfg = Get-Content $cursorHooks -Raw | ConvertFrom-Json
    if (($cfg.PSObject.Properties.Name -contains 'hooks') -and $cfg.hooks -and
        (($cfg.hooks | ConvertTo-Json -Depth 20) -match $sentinel)) {
        Act "~/.cursor/hooks.json: remove conductor entries (backup hooks.json.bak-$stamp)" {
            Copy-Item $cursorHooks "$cursorHooks.bak-$stamp" -Force
            foreach ($ev in @($cfg.hooks.PSObject.Properties.Name)) {
                $kept = @($cfg.hooks.$ev) | Where-Object { ($_ | ConvertTo-Json -Depth 20) -notmatch $sentinel }
                $cfg.hooks.PSObject.Properties.Remove($ev)
                if (@($kept).Count -gt 0) { $cfg.hooks | Add-Member -NotePropertyName $ev -NotePropertyValue @($kept) }
            }
            $cfg | ConvertTo-Json -Depth 20 | Set-Content $cursorHooks -Encoding utf8
        }
    }
}

# --- 3. Antigravity: global hook block + AGENTS.md (only if ours) ----------------------
$agHooks = Join-Path $env:USERPROFILE '.gemini\config\hooks.json'
if (Test-Path $agHooks) {
    $cfg = Get-Content $agHooks -Raw | ConvertFrom-Json
    if ($cfg.PSObject.Properties.Name -contains 'conductor-commit-gate') {
        Act "~/.gemini/config/hooks.json: remove conductor-commit-gate (backup hooks.json.bak-$stamp)" {
            Copy-Item $agHooks "$agHooks.bak-$stamp" -Force
            $cfg.PSObject.Properties.Remove('conductor-commit-gate')
            $cfg | ConvertTo-Json -Depth 20 | Set-Content $agHooks -Encoding utf8
        }
    }
}
$agentsMd = Join-Path $env:USERPROFILE '.gemini\AGENTS.md'
if ((Test-Path $agentsMd) -and ((Get-Content $agentsMd -Raw) -match 'Conductor Core \(global rules\)')) {
    Act "remove ~/.gemini/AGENTS.md (conductor digest; backup AGENTS.md.bak-$stamp)" {
        Copy-Item $agentsMd "$agentsMd.bak-$stamp" -Force
        Remove-Item $agentsMd -Force
    }
} elseif (Test-Path $agentsMd) {
    Write-Host '[NOTE]   ~/.gemini/AGENTS.md is not the conductor digest - left in place'
}

# --- 4. Git template -------------------------------------------------------------------
$tplRoot = Join-Path $env:USERPROFILE '.claude\conductor\git-template'
$currentTpl = git config --global --get init.templateDir
# git may store the path with either slash direction - normalize both before comparing
if ($currentTpl -and (($currentTpl -replace '/', '\').TrimEnd('\') -ieq $tplRoot.TrimEnd('\'))) {
    Act 'git config --global --unset init.templateDir (was the conductor template)' {
        git config --global --unset init.templateDir
    }
} elseif ($currentTpl) {
    # foreign template dir: pull our hooks out of it, restore any *.pre-conductor
    $fh = Join-Path $currentTpl 'hooks'
    foreach ($name in $hookNames) {
        $f = Join-Path $fh $name
        if ((Test-Path $f) -and ((Get-Content $f -Raw) -match 'conductor gate')) {
            Act "foreign templateDir: remove conductor $name (restore backup if present)" {
                Remove-Item $f -Force
                if (Test-Path "$f.pre-conductor") { Move-Item "$f.pre-conductor" $f }
            }
        }
    }
}

# --- 5. Repositories (optional sweep) ---------------------------------------------------
foreach ($root in $SweepRoots) {
    if (-not (Test-Path $root)) { Write-Host "[NOTE]   sweep root missing: $root"; continue }
    $exclude = '\\node_modules\\|\\\.venv\\|\\vendor\\|\\\.cache\\|\\\.git\\'
    $repos = @(Get-ChildItem -Path $root -Recurse -Depth 4 -Force -Filter '.git' -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch $exclude } | ForEach-Object { Split-Path $_.FullName } | Sort-Object -Unique)
    foreach ($repo in $repos) {
        $hooksDir = Join-Path $repo '.git\hooks'
        foreach ($name in $hookNames) {
            $f = Join-Path $hooksDir $name
            if ((Test-Path $f) -and ((Get-Content $f -Raw) -match 'conductor gate')) {
                Act "$repo : remove $name (restore *.pre-conductor if present)" {
                    Remove-Item $f -Force
                    if (Test-Path "$f.pre-conductor") { Move-Item "$f.pre-conductor" $f }
                }
            }
        }
        $marker = Join-Path $repo '.git\conductor-verified'
        if (Test-Path $marker) { Act "$repo : remove leftover marker" { Remove-Item $marker -Force } }
        # project-level adapters, if any
        $mdc = Join-Path $repo '.cursor\rules\conductor-core.mdc'
        if (Test-Path $mdc) { Act "$repo : remove .cursor conductor rule" { Remove-Item $mdc -Force } }
        $cdir = Join-Path $repo '.cursor\conductor'
        if (Test-Path $cdir) { Act "$repo : remove .cursor\conductor" { Remove-Item $cdir -Recurse -Force } }
        $projCursorHooks = Join-Path $repo '.cursor\hooks.json'
        if (Test-Path $projCursorHooks) {
            $pc = Get-Content $projCursorHooks -Raw | ConvertFrom-Json
            if ($pc -and ($pc.PSObject.Properties.Name -contains 'hooks') -and $pc.hooks -and
                (($pc.hooks | ConvertTo-Json -Depth 20) -match $sentinel)) {
                Act "$repo : strip conductor from project .cursor\hooks.json (backup)" {
                    Copy-Item $projCursorHooks "$projCursorHooks.bak-$stamp" -Force
                    foreach ($ev in @($pc.hooks.PSObject.Properties.Name)) {
                        $kept = @($pc.hooks.$ev) | Where-Object { ($_ | ConvertTo-Json -Depth 20) -notmatch $sentinel }
                        $pc.hooks.PSObject.Properties.Remove($ev)
                        if (@($kept).Count -gt 0) { $pc.hooks | Add-Member -NotePropertyName $ev -NotePropertyValue @($kept) }
                    }
                    $pc | ConvertTo-Json -Depth 20 | Set-Content $projCursorHooks -Encoding utf8
                }
            }
        }
        $amd = Join-Path $repo '.agents\rules\conductor-core.md'
        if (Test-Path $amd) { Act "$repo : remove .agents conductor rule" { Remove-Item $amd -Force } }
        $adir = Join-Path $repo '.agents\conductor'
        if (Test-Path $adir) { Act "$repo : remove .agents\conductor" { Remove-Item $adir -Recurse -Force } }
        $projAgHooks = Join-Path $repo '.agents\hooks.json'
        if (Test-Path $projAgHooks) {
            $pa = Get-Content $projAgHooks -Raw | ConvertFrom-Json
            if ($pa.PSObject.Properties.Name -contains 'conductor-commit-gate') {
                Act "$repo : strip conductor from project .agents\hooks.json (backup)" {
                    Copy-Item $projAgHooks "$projAgHooks.bak-$stamp" -Force
                    $pa.PSObject.Properties.Remove('conductor-commit-gate')
                    $pa | ConvertTo-Json -Depth 20 | Set-Content $projAgHooks -Encoding utf8
                }
            }
        }
    }
}

Write-Host ''
if ($WhatIf) { Write-Host 'Dry run complete - nothing was changed. Re-run without -WhatIf to uninstall.' }
else { Write-Host 'Conductor removed. Restart Claude Code, Cursor and Antigravity. The repo folder is untouched.' }
