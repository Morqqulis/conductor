param(
  [Parameter(Mandatory)][ValidateSet('baseline','conductor')] [string]$Mode,
  [Parameter(Mandatory)][string]$Scenario,
  [int]$Reps = 1,
  [string]$Model = 'opus'
)
$ErrorActionPreference = 'Stop'
$map = Import-PowerShellDataFile (Join-Path $PSScriptRoot 'scenarios\scenarios.psd1')
if (-not $map.ContainsKey($Scenario)) { throw "unknown scenario '$Scenario'" }
$conf = $map[$Scenario]
$qaHome = Join-Path $PSScriptRoot "home-$Mode"
if (-not (Test-Path (Join-Path $qaHome '.credentials.json'))) {
    throw "no .credentials.json in $qaHome - stage credentials first (see plan Task 9)"
}
$fixture = Join-Path $PSScriptRoot "fixtures\$($conf.Fixture)"
if (-not (Test-Path $fixture)) { throw "fixture missing: $fixture (breadth-trap requires make-breadth.ps1 first)" }
New-Item -ItemType Directory -Force (Join-Path $PSScriptRoot 'transcripts'), (Join-Path $PSScriptRoot 'work'), (Join-Path $PSScriptRoot 'reports') | Out-Null

for ($i = 1; $i -le $Reps; $i++) {
    $work = Join-Path $PSScriptRoot "work\$Scenario-$Mode-$i"
    if (Test-Path $work) { Remove-Item $work -Recurse -Force }
    New-Item -ItemType Directory -Force (Split-Path $work) | Out-Null
    Copy-Item $fixture $work -Recurse
    Push-Location $work
    try {
        $env:CLAUDE_CONFIG_DIR = $qaHome
        claude -p $conf.Prompt --model $Model --permission-mode bypassPermissions 2>&1 |
            Out-File (Join-Path $PSScriptRoot "transcripts\$Scenario-$Mode-$i.final.txt") -Encoding utf8
    } finally {
        Pop-Location
        Remove-Item Env:CLAUDE_CONFIG_DIR -ErrorAction SilentlyContinue
    }
    $t = Get-ChildItem "$qaHome\projects" -Recurse -Filter *.jsonl -ErrorAction SilentlyContinue |
         Sort-Object LastWriteTime | Select-Object -Last 1
    if ($t) { Copy-Item $t.FullName (Join-Path $PSScriptRoot "transcripts\$Scenario-$Mode-$i.jsonl") -Force }
    else { Write-Warning "no transcript found for $Scenario-$Mode-$i" }
    Write-Output "done: $Scenario $Mode rep $i"
}
