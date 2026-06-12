$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$ServerPath = [IO.Path]::GetFullPath((Join-Path $Root "backtest_platform\server.py"))
$Port = 8765

if (Test-Path $BundledPython) {
    $Python = $BundledPython
} else {
    $Python = "python"
}

$Listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1

if ($Listener) {
    $Existing = Get-CimInstance Win32_Process -Filter "ProcessId = $($Listener.OwningProcess)" -ErrorAction SilentlyContinue
    $CommandLine = [string]$Existing.CommandLine
    $IsBacktestServer = $CommandLine -and (
        $CommandLine.IndexOf($ServerPath, [StringComparison]::OrdinalIgnoreCase) -ge 0
    )

    if (-not $IsBacktestServer) {
        throw "Port $Port is already used by process $($Listener.OwningProcess)."
    }

    Write-Host "Restarting the existing backtest service..."
    Stop-Process -Id $Listener.OwningProcess -Force
    for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
        Start-Sleep -Milliseconds 100
        $Listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if (-not $Listener) {
            break
        }
    }
    if ($Listener) {
        throw "The existing backtest service did not release port $Port."
    }
}

& $Python -X utf8 $ServerPath $Port
