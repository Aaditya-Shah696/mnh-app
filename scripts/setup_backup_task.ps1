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
    [string]$At = "22:00",
    [string]$KeyFile = "$env:USERPROFILE\.ssh\mnh_pull"
)

$ErrorActionPreference = "Stop"

$principalCheck = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principalCheck.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "Run this from an elevated PowerShell (Run as administrator)."
    exit 1
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$script = Join-Path $projectRoot "scripts\pull_backup.ps1"

if (-not (Test-Path $script)) {
    Write-Error "pull_backup.ps1 not found at $script"
    exit 1
}
if (-not (Test-Path $KeyFile)) {
    Write-Error "Pull key not found at $KeyFile. Create it first (docs/RUNBOOK.md, Restricted pull key)."
    exit 1
}

$keyPath = (Resolve-Path $KeyFile).Path
$knownHosts = Join-Path (Split-Path -Parent $keyPath) "known_hosts_mnh"
$argLine = "-NoProfile -ExecutionPolicy Bypass -File `"$script`" -Remote `"$Remote`" -Dest `"$Dest`" -KeyFile `"$keyPath`" -KnownHostsFile `"$knownHosts`""

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $argLine -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew
$account = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $account -LogonType S4U -RunLevel Limited

Register-ScheduledTask -TaskName "MNH Discharge Backup Pull" `
    -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
    -Description "Nightly pull of encrypted discharge-record backups from the VPS" -Force | Out-Null

Write-Host "Scheduled task 'MNH Discharge Backup Pull' registered for $At daily as $account."
Write-Host "It runs whether or not anyone is signed in to this PC, and wakes the PC if it is asleep."
Write-Host "Archives land in $Dest. Run the task once now from Task Scheduler and check $Dest\pull_backup.log."
