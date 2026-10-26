param(
    [switch]$Share,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$labPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $labPython)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ is required.' }
}
& $labPython -c 'import streamlit, pandas, matplotlib'
if ($LASTEXITCODE -ne 0) {
    & $labPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
}
New-Item -ItemType Directory -Force -Path '.runtime' | Out-Null
$labPort = 8514
$labUrl = "http://127.0.0.1:$labPort"
$labPidFile = Join-Path $PSScriptRoot '.runtime\server.pid'
$labBind = if ($Share) { '0.0.0.0' } else { '127.0.0.1' }

# First local IPv4 address (the one used to reach the internet), for the share URL.
function Get-LabLanAddress {
    try {
        $route = Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction Stop |
            Sort-Object RouteMetric, InterfaceMetric | Select-Object -First 1
        $address = Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $route.InterfaceIndex -ErrorAction Stop |
            Where-Object { $_.IPAddress -notlike '169.254.*' } | Select-Object -First 1
        if ($address) { return $address.IPAddress }
    } catch { }
    try {
        return (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
            Where-Object { $_.IPAddress -ne '127.0.0.1' -and $_.IPAddress -notlike '169.254.*' } |
            Select-Object -First 1).IPAddress
    } catch { return $null }
}

$labProcess = $null
$labNeedsRestart = $false
if (Test-Path -LiteralPath $labPidFile) {
    $labStoredPid = Get-Content -LiteralPath $labPidFile
    $labExisting = Get-CimInstance Win32_Process -Filter "ProcessId = $labStoredPid" -ErrorAction SilentlyContinue
    if ($labExisting -and $labExisting.CommandLine -like "*$PSScriptRoot*Hello.py*") {
        $labProcess = Get-Process -Id $labStoredPid -ErrorAction SilentlyContinue
        # an already running server only serves the right address if it was started with this bind
        if ($labExisting.CommandLine -notlike "*--server.address $labBind*") {
            $labNeedsRestart = $true
        }
    }
}
if ($labNeedsRestart -and $labProcess) {
    Stop-Process -Id $labProcess.Id -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
    $labProcess = $null
}
if (-not $labProcess) {
    if (Get-NetTCPConnection -LocalPort $labPort -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $labPort is already in use by another process."
    }
    $labArguments = '-m streamlit run "' + (Join-Path $PSScriptRoot 'Hello.py') +
        '" --server.port ' + $labPort + ' --server.address ' + $labBind
    $labProcess = Start-Process -FilePath $labPython -ArgumentList $labArguments -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput '.runtime\stdout.log' -RedirectStandardError '.runtime\stderr.log'
    $labProcess.Id | Set-Content -LiteralPath $labPidFile
}
$labReady = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    try {
        $labResponse = Invoke-WebRequest "$labUrl/_stcore/health" -UseBasicParsing -TimeoutSec 2
        if ($labResponse.StatusCode -eq 200) { $labReady = $true; break }
    } catch { Start-Sleep -Milliseconds 500 }
}
if (-not $labReady) { throw 'DES Lab did not start. See .runtime/stderr.log.' }
if (-not $NoBrowser) { Start-Process $labUrl }
Write-Host "DES Lab is running at $labUrl"

if ($Share) {
    $labLan = Get-LabLanAddress
    # allow the port through the firewall (needs an elevated shell; warn instead of failing)
    $labRule = Get-NetFirewallRule -DisplayName 'DES Lab 8514' -ErrorAction SilentlyContinue
    if (-not $labRule) {
        try {
            New-NetFirewallRule -DisplayName 'DES Lab 8514' -Direction Inbound -Protocol TCP -LocalPort $labPort -Action Allow -Profile Private | Out-Null
            Write-Host 'Firewall rule added for port 8514 (private networks).'
        } catch {
            Write-Host 'Could not add the firewall rule automatically (needs an elevated PowerShell).'
            Write-Host "Run this once in an Administrator PowerShell:"
            Write-Host "  New-NetFirewallRule -DisplayName 'DES Lab 8514' -Direction Inbound -Protocol TCP -LocalPort $labPort -Action Allow -Profile Private"
        }
    }
    if ($labLan) {
        Write-Host ''
        Write-Host "Share this address with teammates on the same network:"
        Write-Host "  http://$labLan`:$labPort"
        Write-Host ''
        Write-Host 'Anyone on this network can open it and sign in or create an account.'
        Write-Host 'Only for trusted networks (lab / home). Do not expose it to the internet.'
    } else {
        Write-Host 'Could not detect a network address; check ipconfig.'
    }
}
