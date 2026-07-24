# Installs the Conductor Cursor adapter into a project: always-on rule (digest of core).
# The commit-gate hook of older versions is retired (the marker gate certified nothing -
# agents satisfied it ritually): any conductor entry left in .cursor/hooks.json and the
# .cursor/conductor/gate.ps1 script are removed. Idempotent; configs backed up first.
param(
    [string]$Repo = (Get-Location).Path
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

$srcRule = Join-Path $PSScriptRoot 'adapters\cursor\conductor-core.mdc'
if (-not (Test-Path $srcRule)) { throw "adapter source not found: $srcRule - run this script from the conductor repo root" }
if (-not (Test-Path $Repo)) { throw "target directory does not exist: $Repo" }
$Repo = (Resolve-Path $Repo).Path

$cursorDir = Join-Path $Repo '.cursor'
$rulesDir = Join-Path $cursorDir 'rules'
New-Item -ItemType Directory -Force $rulesDir | Out-Null
Copy-Item $srcRule (Join-Path $rulesDir 'conductor-core.mdc') -Force
Write-Output "rule installed:  $rulesDir\conductor-core.mdc (alwaysApply)"

# Retired commit-gate cleanup (older versions)
$gateScript = Join-Path $cursorDir 'conductor\gate.ps1'
if (Test-Path $gateScript) {
    Remove-Item (Join-Path $cursorDir 'conductor') -Recurse -Force
    Write-Output "retired gate script removed: $gateScript"
}
$hooksJsonPath = Join-Path $cursorDir 'hooks.json'
if (Test-Path $hooksJsonPath) {
    $cfg = Get-Content $hooksJsonPath -Raw | ConvertFrom-Json
    if (($cfg.PSObject.Properties.Name -contains 'hooks') -and
        ($cfg.hooks.PSObject.Properties.Name -contains 'beforeShellExecution')) {
        $all = @($cfg.hooks.beforeShellExecution)
        $kept = @($all | Where-Object { ($_ | ConvertTo-Json -Depth 10) -notmatch 'conductor' })
        if ($kept.Count -ne $all.Count) {
            $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
            Copy-Item $hooksJsonPath "$hooksJsonPath.bak-$stamp" -Force
            $cfg.hooks.PSObject.Properties.Remove('beforeShellExecution')
            if ($kept.Count -gt 0) { $cfg.hooks | Add-Member -NotePropertyName beforeShellExecution -NotePropertyValue $kept }
            $cfg | ConvertTo-Json -Depth 20 | Set-Content $hooksJsonPath -Encoding utf8
            Write-Output "retired gate hook removed from $hooksJsonPath (backup: hooks.json.bak-$stamp)"
        }
    }
}
Write-Output 'Done. Restart the Cursor agent session in this project to pick up the rule.'
