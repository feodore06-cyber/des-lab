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
$labProcess = $null
if (Test-Path -LiteralPath $labPidFile) {
    $labStoredPid = Get-Content -LiteralPath $labPidFile
    $labExisting = Get-CimInstance Win32_Process -Filter "ProcessId = $labStoredPid" -ErrorAction SilentlyContinue
    if ($labExisting -and $labExisting.CommandLine -like "*$PSScriptRoot*Hello.py*") {
        $labProcess = Get-Process -Id $labStoredPid -ErrorAction SilentlyContinue
    }
}
if (-not $labProcess) {
    if (Get-NetTCPConnection -LocalPort $labPort -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $labPort is already in use by another process."
    }
    $labArguments = '-m streamlit run "' + (Join-Path $PSScriptRoot 'Hello.py') + '" --server.port ' + $labPort
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
Start-Process $labUrl
Write-Host "DES Lab is running at $labUrl"
