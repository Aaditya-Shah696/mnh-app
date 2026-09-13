# Registers a Windows Task Scheduler job on the CLINIC PC that pulls the
# newest encrypted backup archives from the VPS every night, so a copy of
# the records is always inside the building.
#
# Run from the project folder in an elevated PowerShell:
#   .\scripts\setup_backup_task.ps1 -Remote mnhpull@mnh-vps -Dest "E:\clinic-backups" [-At "22:00"]
#
# Prerequisites: Tailscale signed in on this PC, and the restricted pull key
# at %USERPROFILE%\.ssh\mnh_pull (see docs/RUNBOOK.md).
param(
    [string]$Remote = "mnhpull@mnh-vps",
    [string]$Dest = "E:\clinic-backups",
    [string]$At = "22:00"
)

$projectRoot = Split-Path -Parent $PSScriptRoot
$script = Join-Path $projectRoot "scripts\pull_backup.ps1"

if (-not (Test-Path $script)) {
    Write-Error "pull_backup.ps1 not found at $script"
    exit 1
}

$argLine = "-NoProfile -ExecutionPolicy Bypass -File `"$script`" -Remote `"$Remote`" -Dest `"$Dest`""

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $argLine -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd -RunOnlyIfNetworkAvailable

Register-ScheduledTask -TaskName "MNH Discharge Backup Pull" `
    -Action $action -Trigger $trigger -Settings $settings `
    -Description "Nightly pull of encrypted discharge-record backups from the VPS" -Force

Write-Host "Scheduled task 'MNH Discharge Backup Pull' registered for $At daily."
Write-Host "Archives land in $Dest. Run the task once now from Task Scheduler to confirm the key works."
