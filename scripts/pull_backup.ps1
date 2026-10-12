# Fetch the newest encrypted backup archives from the VPS to this PC.
#
# The app now runs on the VPS; this script keeps a copy of every nightly
# AES-encrypted archive INSIDE the clinic, so the records survive the VPS
# disappearing. Register it with scripts\setup_backup_task.ps1, or run by hand:
#
#   .\scripts\pull_backup.ps1 -Remote mnhpull@mnh-vps -Dest E:\clinic-backups
#
# Requirements on this PC: OpenSSH client (built into Windows 10/11), the
# Tailscale client signed in to the clinic tailnet, and an SSH key whose
# public half is in the VPS user's authorized_keys (see docs/RUNBOOK.md,
# "Restricted pull key").
param(
    [string]$Remote = "mnhpull@mnh-vps",
    [string]$RemoteDir = "/archives",
    [string]$Dest = "E:\clinic-backups",
    [string]$KeyFile = "$env:USERPROFILE\.ssh\mnh_pull",
    [string]$KnownHostsFile = "$env:USERPROFILE\.ssh\known_hosts_mnh",
    [int]$Keep = 60,
    [int]$MaxAgeHours = 36
)

$ErrorActionPreference = "Stop"
$archivePattern = '^discharge_backup_\d{8}_\d{6}\.zip$'

New-Item -ItemType Directory -Force -Path $Dest | Out-Null
$logFile = Join-Path $Dest "pull_backup.log"

function Write-Log([string]$Message) {
    "$(Get-Date -Format s) $Message" | Add-Content -Path $logFile
    Write-Host $Message
}

function Stop-WithError([string]$Message) {
    Write-Log "ERROR $Message"
    [Console]::Error.WriteLine($Message)
    exit 1
}

function Invoke-Sftp([string[]]$Commands) {
    $ErrorActionPreference = "Continue"
    $batch = New-TemporaryFile
    try {
        [System.IO.File]::WriteAllLines($batch.FullName, $Commands)
        $sftpArgs = @(
            "-i", $KeyFile,
            "-o", "BatchMode=yes",
            "-o", "IdentitiesOnly=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "UserKnownHostsFile=$KnownHostsFile",
            "-o", "ConnectTimeout=30",
            "-b", $batch.FullName,
            $Remote
        )
        $output = & sftp @sftpArgs 2>&1
        return [pscustomobject]@{ ExitCode = $LASTEXITCODE; Output = @($output | ForEach-Object { "$_" }) }
    } finally {
        Remove-Item -Force $batch.FullName -ErrorAction SilentlyContinue
    }
}

if (-not (Test-Path $KeyFile)) {
    Stop-WithError "Pull key not found at $KeyFile (see docs/RUNBOOK.md, Restricted pull key)."
}

$listing = Invoke-Sftp @("ls -1 $RemoteDir")
if ($listing.ExitCode -ne 0) {
    $detail = ($listing.Output | Select-Object -Last 3) -join " | "
    Stop-WithError "Could not list $Remote`:$RemoteDir (is Tailscale up? is the key installed?): $detail"
}
$remoteNames = @(
    $listing.Output |
        Where-Object { $_ -notmatch '^sftp>' } |
        ForEach-Object { ($_.Trim() -split '/')[-1] } |
        Where-Object { $_ -match $archivePattern } |
        Sort-Object -Unique
)
if ($remoteNames.Count -eq 0) {
    Stop-WithError "No archives found in $Remote`:$RemoteDir."
}

$fetched = 0
foreach ($name in $remoteNames) {
    $local = Join-Path $Dest $name
    if (Test-Path $local) { continue }
    $part = "$local.part"
    Write-Host "Fetching $name"
    $localForSftp = $part -replace '\\', '/'
    $get = Invoke-Sftp @("get -p `"$RemoteDir/$name`" `"$localForSftp`"")
    if ($get.ExitCode -ne 0 -or -not (Test-Path $part)) {
        Remove-Item -Force $part -ErrorAction SilentlyContinue
        $detail = ($get.Output | Select-Object -Last 3) -join " | "
        Stop-WithError "Download of $name failed: $detail"
    }
    Move-Item -Force $part $local
    $fetched++
}

$all = @(Get-ChildItem -Path $Dest -Filter "discharge_backup_*.zip" | Where-Object { $_.Name -match $archivePattern } | Sort-Object Name)
if ($all.Count -gt $Keep) {
    $all | Select-Object -First ($all.Count - $Keep) | ForEach-Object {
        Write-Host "Pruning $($_.Name)"
        Remove-Item -Force $_.FullName
    }
}

$newest = Get-ChildItem -Path $Dest -Filter "discharge_backup_*.zip" | Where-Object { $_.Name -match $archivePattern } | Sort-Object Name | Select-Object -Last 1
$ageHours = [math]::Round(((Get-Date) - $newest.LastWriteTime).TotalHours, 1)
Write-Log "fetched=$fetched newest=$($newest.Name) size_mb=$([math]::Round($newest.Length / 1MB, 1)) age_hours=$ageHours"
if ($ageHours -gt $MaxAgeHours) {
    Stop-WithError "The newest archive is $ageHours hours old; the server has not written a backup since $($newest.LastWriteTime)."
}
