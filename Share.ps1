param(
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

# 1) make sure the local app is running
& (Join-Path $PSScriptRoot 'Start.ps1') -NoBrowser | Out-Null

$runtime = Join-Path $PSScriptRoot '.runtime'
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
$urlFile = Join-Path $runtime 'public_url.txt'
$exe = Join-Path $env:LOCALAPPDATA 'cloudflared\cloudflared.exe'
if (-not (Test-Path -LiteralPath $exe)) {
    throw 'cloudflared is missing. Run "Start DES Lab (public tunnel).cmd" once to download it.'
}

$url = $null
$running = Get-CimInstance Win32_Process -Filter "Name = 'cloudflared.exe'" -ErrorAction SilentlyContinue
if ($running -and (Test-Path -LiteralPath $urlFile)) {
    $candidate = (Get-Content -LiteralPath $urlFile -Raw).Trim()
    try {
        $probe = Invoke-WebRequest "$candidate/_stcore/health" -UseBasicParsing -TimeoutSec 8
        if ($probe.StatusCode -eq 200) { $url = $candidate }
    } catch { }
}

if (-not $url) {
    if ($running) { $running | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } }
    $logOut = Join-Path $runtime 'cf-out.log'
    $logErr = Join-Path $runtime 'cf-err.log'
    Remove-Item $logOut, $logErr -Force -ErrorAction SilentlyContinue
    Start-Process -FilePath $exe -WindowStyle Hidden -ArgumentList @(
        'tunnel', '--url', 'http://127.0.0.1:8514', '--no-autoupdate', '--protocol', 'http2') `
        -RedirectStandardOutput $logOut -RedirectStandardError $logErr | Out-Null
    for ($attempt = 0; $attempt -lt 25; $attempt++) {
        Start-Sleep -Seconds 2
        $text = (Get-Content -LiteralPath $logOut -Raw -ErrorAction SilentlyContinue) +
                (Get-Content -LiteralPath $logErr -Raw -ErrorAction SilentlyContinue)
        $match = [regex]::Match($text, 'https://[a-z0-9-]+\.trycloudflare\.com')
        if ($match.Success) { $url = $match.Value; break }
    }
    if (-not $url) { throw 'The tunnel did not produce a URL. See .runtime\cf-err.log' }
    Start-Sleep -Seconds 3
}

Set-Content -LiteralPath $urlFile -Value $url -Encoding ascii

$desktop = [Environment]::GetFolderPath('Desktop')
$desktopFile = Join-Path $desktop 'DES-Lab-link.txt'
$body = @(
    'BioMat Lab - Experiment Workbench',
    '',
    'PUBLIC url (anyone, anywhere):',
    $url,
    '',
    'LOCAL url (this computer only):',
    'http://127.0.0.1:8514',
    '',
    'The public url changes every time the tunnel restarts - always trust this file.',
    'It stops working when the computer is off or cloudflared is closed.',
    'Regenerate: double-click "Share DES Lab.cmd" in the project folder.',
    '',
    ('Updated ' + (Get-Date -Format 'yyyy-MM-dd HH:mm'))
) -join [Environment]::NewLine
Set-Content -LiteralPath $desktopFile -Value $body -Encoding UTF8

Write-Host "Local : http://127.0.0.1:8514"
Write-Host "Public: $url"
Write-Host "Saved  : $desktopFile"
