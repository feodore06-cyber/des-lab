$labPidFile = Join-Path $PSScriptRoot '.runtime\server.pid'
if (Test-Path -LiteralPath $labPidFile) {
    $labStoredPid = Get-Content -LiteralPath $labPidFile
    $labExisting = Get-CimInstance Win32_Process -Filter "ProcessId = $labStoredPid" -ErrorAction SilentlyContinue
    if ($labExisting -and $labExisting.CommandLine -like "*$PSScriptRoot*Hello.py*") {
        Stop-Process -Id $labStoredPid
        Write-Host 'DES Lab stopped.'
    }
}
