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
    [string]$RemoteDir = "/srv/mnh/data/backups",
    [string]$Dest = "E:\clinic-backups",
    [string]$KeyFile = "$env:USERPROFILE\.ssh\mnh_pull",
    [int]$Keep = 60
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null

$sshOpts = @("-i", $KeyFile, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new")

Write-Host "Listing archives on $Remote..."
$remoteList = & ssh @sshOpts $Remote "ls -1 $RemoteDir/discharge_backup_*.zip 2>/dev/null"
if ($LASTEXITCODE -ne 0 -or -not $remoteList) {
    Write-Error "Could not list remote backups (is Tailscale up? is the key installed?)"
    exit 1
}

$fetched = 0
foreach ($remotePath in $remoteList) {
    $name = Split-Path -Leaf $remotePath
    $local = Join-Path $Dest $name
    if (Test-Path $local) { continue }
    Write-Host "Fetching $name"
    & scp @sshOpts "${Remote}:$remotePath" "$local.part"
    if ($LASTEXITCODE -ne 0) { Remove-Item -Force "$local.part" -ErrorAction SilentlyContinue; Write-Error "scp failed for $name"; exit 1 }
    Move-Item -Force "$local.part" $local
    $fetched++
}

# Keep the newest $Keep locally.
$all = Get-ChildItem -Path $Dest -Filter "discharge_backup_*.zip" | Sort-Object Name
if ($all.Count -gt $Keep) {
    $all | Select-Object -First ($all.Count - $Keep) | ForEach-Object {
        Write-Host "Pruning $($_.Name)"
        Remove-Item -Force $_.FullName
    }
}

$newest = Get-ChildItem -Path $Dest -Filter "discharge_backup_*.zip" | Sort-Object Name | Select-Object -Last 1
Write-Host "Fetched $fetched new archive(s). Newest local copy: $($newest.Name) ($([math]::Round($newest.Length / 1MB, 1)) MB)"
"$(Get-Date -Format s) fetched=$fetched newest=$($newest.Name)" | Add-Content -Path (Join-Path $Dest "pull_backup.log")
