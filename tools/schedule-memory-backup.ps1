[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)][string]$MemoryDirectory,
    [Parameter(Mandatory = $true)][string]$BashPath,
    [ValidatePattern('^[A-Za-z0-9_-]+$')][string]$TaskName = 'ConductorMemoryBackup',
    [ValidatePattern('^(?:[01][0-9]|2[0-3]):[0-5][0-9]$')][string]$DailyAt = '21:00',
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
try {
    $memoryPath = (Resolve-Path -LiteralPath $MemoryDirectory).ProviderPath
    $bashExecutable = (Get-Item -LiteralPath $BashPath).FullName
    $backupScript = Join-Path $memoryPath 'backup-push.sh'
    if (-not (Test-Path -LiteralPath $backupScript -PathType Leaf) -or
        -not (Test-Path -LiteralPath (Join-Path $memoryPath '.git') -PathType Container) -or
        -not (Test-Path -LiteralPath $bashExecutable -PathType Leaf)) {
        throw 'Expected a cloned memory repository, backup-push.sh, and a Bash executable.'
    }
    # A script argument, never bash -c. Forward slashes avoid Windows quote/backslash ambiguity.
    $scriptArgument = $backupScript.Replace('\', '/')
    if ($scriptArgument -match '["\r\n]') { throw 'Unsupported quote or newline in script path.' }
    $definition = [ordered]@{
        TaskName = $TaskName
        Execute = $bashExecutable
        Arguments = '--noprofile --norc -- "' + $scriptArgument + '"'
        WorkingDirectory = $memoryPath
        DailyAt = $DailyAt
        UserId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        LogonType = 'Interactive'
        RunLevel = 'Limited'
    }
    if ($DryRun) {
        $definition | ConvertTo-Json
        return
    }
    if ($PSCmdlet.ShouldProcess($TaskName, 'Register daily memory backup for the current signed-in user')) {
        # Never replace a task, even one with the same name and apparently matching fields.
        $existing = @(Get-ScheduledTask -TaskPath '\' | Where-Object TaskName -EQ $TaskName)
        if ($existing.Count -ne 0) { throw "Task already exists: $TaskName. Inspect it or choose another name." }
        $action = New-ScheduledTaskAction -Execute $definition.Execute -Argument $definition.Arguments -WorkingDirectory $memoryPath
        $trigger = New-ScheduledTaskTrigger -Daily -At ([datetime]::ParseExact($DailyAt, 'HH:mm', [cultureinfo]::InvariantCulture))
        $principal = New-ScheduledTaskPrincipal -UserId $definition.UserId -LogonType Interactive -RunLevel Limited
        $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew
        Register-ScheduledTask -TaskPath '\' -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
        $definition | ConvertTo-Json
    }
} catch {
    Write-Error ('memory-backup-schedule: ' + $_.Exception.Message)
    exit 1
}
