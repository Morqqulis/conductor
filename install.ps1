# Native Windows entrypoint. Git for Windows + Python 3.10+ are prerequisites.
[CmdletBinding()]
param(
    [string]$Language,
    [ValidateSet('all', 'claude', 'global')][string]$Scope = 'all',
    [string]$Ref = 'main',
    [switch]$SkipCompanions,
    [switch]$NoSuperpowers,
    [switch]$SkipGlobalMd
)
$ErrorActionPreference = 'Stop'
$pythonExecutable = $null
foreach ($candidate in @($env:CONDUCTOR_PYTHON, 'python3', 'python')) {
    if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
    $command = Get-Command $candidate -CommandType Application -ErrorAction SilentlyContinue
    if ($command) {
        try {
            & $command.Source -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>$null
            if ($LASTEXITCODE -eq 0) { $pythonExecutable = $command.Source; break }
        } catch {
            # Windows PowerShell promotes native stderr to NativeCommandError under Stop.
            [Console]::Error.WriteLine('[conductor.bootstrap] Python probe failed; trying the next candidate.')
        }
    }
}
if (-not $pythonExecutable) { throw 'Conductor requires Python 3.10+ on PATH.' }
$temporaryBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$temporaryDirectory = Join-Path $temporaryBase ('conductor-bootstrap-' + [guid]::NewGuid().ToString('N'))
$bootstrapFile = Join-Path $temporaryDirectory 'bootstrap.py'
New-Item -ItemType Directory -Path $temporaryDirectory | Out-Null
try {
    # SecurityProtocol change applies to this process only; never disable certificate checks.
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -UseBasicParsing -TimeoutSec 90 -Uri 'https://raw.githubusercontent.com/Morqqulis/conductor/main/tools/bootstrap.py' -OutFile $bootstrapFile
    $downloadSize = (Get-Item -LiteralPath $bootstrapFile).Length
    if ($downloadSize -eq 0 -or $downloadSize -gt 1048576) { throw 'Bootstrap download is empty or exceeds size limit.' }
    $bootstrapArguments = @('-B', $bootstrapFile, '--ref', $Ref, '--scope', $Scope)
    if ($PSBoundParameters.ContainsKey('Language')) { $bootstrapArguments += @('--language', $Language) }
    if ($SkipCompanions) { $bootstrapArguments += '--skip-companions' }
    if ($NoSuperpowers) { $bootstrapArguments += '--no-superpowers' }
    if ($SkipGlobalMd) { $bootstrapArguments += '--skip-global-md' }
    & $pythonExecutable @bootstrapArguments
    if ($LASTEXITCODE -ne 0) { throw "Conductor bootstrap failed (exit $LASTEXITCODE)." }
} finally {
    # Exact files only; no recursive deletion and no persistent execution-policy changes.
    if (Test-Path -LiteralPath $bootstrapFile) { Remove-Item -LiteralPath $bootstrapFile }
    if (Test-Path -LiteralPath $temporaryDirectory) { Remove-Item -LiteralPath $temporaryDirectory }
}
