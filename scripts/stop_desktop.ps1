[CmdletBinding()]
param(
    [int]$BackendPort = 3018,
    [int]$FrontendPort = 3011
)

$ErrorActionPreference = 'SilentlyContinue'

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$StateDir = Join-Path $Root '.desktop'
$PidFile = Join-Path $StateDir 'dev.pid'
$DevScript = Join-Path $Root 'dev.ps1'

function Stop-ProcessTree($pid) {
    if (-not $pid) { return }
    try {
        [System.Diagnostics.Process]::GetProcessById([int]$pid) | Out-Null
        $null = & cmd /c "taskkill /F /T /PID $pid 2>nul"
    } catch {}
}

function Stop-PortListeners($port) {
    $listeners = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    $pids = @($listeners.OwningProcess | Where-Object { $_ -gt 0 } | Sort-Object -Unique)
    foreach ($pid in $pids) {
        Stop-ProcessTree $pid
    }
}

if (Test-Path $PidFile) {
    $savedPid = (Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    Stop-ProcessTree $savedPid
}

Stop-PortListeners $BackendPort
Stop-PortListeners $FrontendPort

$escapedDevScript = $DevScript.Replace('\', '\\')
$devProcesses = Get-CimInstance Win32_Process |
    Where-Object {
        $_.CommandLine -and
        $_.CommandLine -match 'dev\.ps1' -and
        $_.CommandLine -match [regex]::Escape($DevScript)
    }

foreach ($proc in $devProcesses) {
    Stop-ProcessTree $proc.ProcessId
}

Remove-Item $PidFile -Force -ErrorAction SilentlyContinue

Write-Host 'TickFlow services stopped.' -ForegroundColor Green
Start-Sleep -Seconds 1
