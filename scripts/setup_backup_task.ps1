# Registers a Windows Task Scheduler job that runs an encrypted backup
# every night at 21:30, optionally copying it to an external drive.
# The in-app scheduler already backs up daily while the app is running;
# this task covers machines where the app is not left open.
#
# Run from the project folder in an elevated PowerShell:
#   .\scripts\setup_backup_task.ps1 [-CopyTo "E:\clinic-backups"] [-At "21:30"]

param(
    [string]$CopyTo = "",
    [string]$At = "21:30"
)

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$script = Join-Path $projectRoot "scripts\backup_now.py"

if (-not (Test-Path $python)) {
    Write-Error "Python venv not found at $python. Run setup first."
    exit 1
}

$argLine = "`"$script`""
if ($CopyTo -ne "") {
    $argLine += " --copy-to `"$CopyTo`""
}

$action = New-ScheduledTaskAction -Execute $python -Argument $argLine -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd

Register-ScheduledTask -TaskName "MNH Discharge Backup" `
    -Action $action -Trigger $trigger -Settings $settings `
    -Description "Nightly encrypted backup of discharge records" -Force

Write-Host "Scheduled task 'MNH Discharge Backup' registered for $At daily."
if ($CopyTo -ne "") { Write-Host "Backups will also be copied to $CopyTo" }
