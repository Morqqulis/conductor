# Native Windows entrypoint. Git for Windows is a prerequisite; Python 3.10+ is found on
# PATH or, with the user's explicit consent, installed with the official install manager.
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
# A caller's session may turn every non-zero native exit code into an exception; the exit
# codes are read here on purpose. Scoped to this script.
$PSNativeCommandUseErrorActionPreference = $false
# The second stage comes from the SAME revision as -Ref, so a pinned install never runs a
# bootstrap from a newer main. Same grammar as tools/bootstrap.py (case-sensitive).
if ($Ref -cnotmatch '^(main|[0-9a-fA-F]{40}|v[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?)$') {
    throw 'Conductor bootstrap: -Ref must be main, a version tag (vX.Y.Z) or a full commit; nothing installed.'
}

function Test-ConductorPython {
    param([string]$Path)
    # Continue: Windows PowerShell promotes native stderr to a terminating NativeCommandError
    # under Stop, and the Microsoft Store shortcut answers every call on stderr.
    $ErrorActionPreference = 'Continue'
    # A probe must never install anything: the Python install manager's own `py` and `python`
    # commands download a runtime when none is present unless this setting says no.
    $previousAutomatic = $env:PYTHON_MANAGER_AUTOMATIC_INSTALL
    $env:PYTHON_MANAGER_AUTOMATIC_INSTALL = 'false'
    # A file that is not a program leaves the previous exit code in place; start from failure.
    $global:LASTEXITCODE = 1
    try {
        & $Path -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>$null | Out-Null
        return ($global:LASTEXITCODE -eq 0)
    } catch {
        [Console]::Error.WriteLine("[conductor.bootstrap] Python probe could not start $Path; trying the next candidate.")
        return $false
    } finally {
        $env:PYTHON_MANAGER_AUTOMATIC_INSTALL = $previousAutomatic
    }
}

function Find-ConductorPython {
    foreach ($candidate in @($env:CONDUCTOR_PYTHON, 'python3', 'python', 'py')) {
        if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
        # Get-Command returns EVERY match on PATH (a real python.exe AND the Store shortcut of
        # the same name), so each match is probed on its own; invoking the whole result would
        # join the paths into one unrunnable command name.
        foreach ($command in @(Get-Command $candidate -CommandType Application -ErrorAction SilentlyContinue)) {
            if (-not $command) { continue }
            $path = [string]$command.Source
            # Programs only: a same-named file without a program extension (a shell shim)
            # would be handed to the Windows "open with" dialog instead of being run.
            if ($path -notmatch '\.(exe|cmd|bat|com)$') { continue }
            if (Test-ConductorPython $path) { return $path }
        }
    }
    return $null
}

function Find-ConductorPythonManager {
    $managers = @(Get-Command 'pymanager' -CommandType Application -ErrorAction SilentlyContinue | ForEach-Object { [string]$_.Source })
    if ($env:LOCALAPPDATA) {
        # The command alias is not always visible to the terminal that installed the package.
        $pattern = Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps\PythonSoftwareFoundation.PythonManager_*\pymanager.exe'
        $managers += @(Get-Item -Path $pattern -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
    }
    return ($managers | Where-Object { $_ } | Select-Object -First 1)
}

function Install-ConductorPython {
    # Continue: outside a plain console Windows PowerShell turns a native tool's stderr line
    # into a terminating error under Stop, which would cut winget off mid-install. Exit
    # codes are checked explicitly below and `throw` still terminates.
    $ErrorActionPreference = 'Continue'
    $manual = 'Install Python 3.10 or newer from https://www.python.org/downloads/ , open a new terminal and run this command again.'
    # An install manager that is already present needs no winget (which reports an error
    # for a package that is installed and current).
    $manager = Find-ConductorPythonManager
    $winget = @(Get-Command 'winget' -CommandType Application -ErrorAction SilentlyContinue) | Select-Object -First 1
    if (-not $manager -and -not $winget) { throw "Conductor requires Python 3.10+ and found none; winget is not available to install it. $manual" }
    $plan = 'This uses the official Python install manager that is already on this computer.'
    if (-not $manager) { $plan = 'This runs winget to install the official Python install manager from the Microsoft Store source and accepts the package and source terms for you.' }
    $answer = ''
    try {
        $answer = [string](Read-Host "Conductor needs Python 3.10+ and found none. Install the latest stable Python for your user account now? $plan [y/N]")
    } catch {
        [Console]::Error.WriteLine('[conductor.bootstrap] No answer could be read; Python is not installed automatically.')
    }
    if ($answer.Trim() -notmatch '^(y|yes)$') { throw "Conductor requires Python 3.10+ and found none; nothing was installed. $manual" }
    if (-not $manager) {
        & ([string]$winget.Source) install 9NQ7512CXL7T -e --accept-package-agreements --accept-source-agreements --disable-interactivity | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "winget could not install the Python install manager (exit $LASTEXITCODE). $manual" }
        $manager = Find-ConductorPythonManager
        if (-not $manager) { throw "The Python install manager was installed, but its pymanager command was not found. $manual" }
    }
    $previousConfirm = $env:PYTHON_MANAGER_CONFIRM
    $env:PYTHON_MANAGER_CONFIRM = 'false'
    try {
        & $manager install default | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "The Python install manager could not install Python (exit $LASTEXITCODE). $manual" }
        $listed = @(& $manager list --format=exe --one)
    } finally {
        $env:PYTHON_MANAGER_CONFIRM = $previousConfirm
    }
    foreach ($line in $listed) {
        $path = ([string]$line).Trim()
        if ($path -and (Test-Path -LiteralPath $path -PathType Leaf) -and (Test-ConductorPython $path)) { return $path }
    }
    $found = Find-ConductorPython
    if ($found) { return $found }
    throw 'Python was installed, but this terminal does not see it yet. Open a new terminal and run this command again.'
}

$pythonExecutable = Find-ConductorPython
if (-not $pythonExecutable) { $pythonExecutable = Install-ConductorPython }
$temporaryBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$temporaryDirectory = Join-Path $temporaryBase ('conductor-bootstrap-' + [guid]::NewGuid().ToString('N'))
$bootstrapFile = Join-Path $temporaryDirectory 'bootstrap.py'
New-Item -ItemType Directory -Path $temporaryDirectory | Out-Null
try {
    # SecurityProtocol change applies to this process only; never disable certificate checks.
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -UseBasicParsing -TimeoutSec 90 -Uri "https://raw.githubusercontent.com/Morqqulis/conductor/$Ref/tools/bootstrap.py" -OutFile $bootstrapFile
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
