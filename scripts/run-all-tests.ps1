param(
  [string]$HostAddr = "127.0.0.1",
  [int]$BackendPort = 8000,
  [int]$FrontendPort = 5173,
  [switch]$SkipInstall,
  [switch]$SkipE2E
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$backendDir = Join-Path $root "backend"
$frontendDir = Join-Path $root "frontend-vue"
$resultsDir = Join-Path $root "test-results"
New-Item -ItemType Directory -Force -Path $resultsDir | Out-Null
$runtimeDataDir = Join-Path $resultsDir ("runtime-data-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $runtimeDataDir | Out-Null
Copy-Item -Path (Join-Path $root "roadshow-data\*") -Destination $runtimeDataDir -Recurse -Force

function Write-Step($message) {
  Write-Host ""
  Write-Host "==== $message ====" -ForegroundColor Cyan
}

function Wait-Http($url, $name) {
  for ($i = 0; $i -lt 60; $i++) {
    try {
      $resp = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 2
      if ($resp.StatusCode -lt 500) {
        Write-Host "$name ready: $url"
        return
      }
    } catch {
      Start-Sleep -Milliseconds 700
    }
  }
  throw "$name did not become ready: $url"
}

function Stop-Port($port) {
  $processIds = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique
  foreach ($processId in $processIds) {
    if ($processId) {
      Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
  }
}

function Invoke-Checked([scriptblock]$Command, [string]$Name) {
  & $Command
  if ($LASTEXITCODE -ne 0) {
    throw "$Name failed with exit code $LASTEXITCODE"
  }
}

$backend = $null
$frontend = $null
$failed = $false

try {
  Write-Step "Install dependencies"
  if (!$SkipInstall) {
    Push-Location $frontendDir
    Invoke-Checked { npm install } "npm install"
    Pop-Location
  }

  Write-Step "Restart services"
  foreach ($port in @($BackendPort, $FrontendPort)) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
      throw "Port $port is already in use. Choose free BackendPort and FrontendPort values."
    }
  }

  $env:PYTHONPATH = $backendDir
  $env:DATA_DIR = $runtimeDataDir
  $backend = Start-Process -FilePath "python" -WorkingDirectory $backendDir -ArgumentList @(
    "-m", "uvicorn", "app.main:app",
    "--host", $HostAddr,
    "--port", "$BackendPort"
  ) -WindowStyle Hidden -PassThru

  $frontend = Start-Process -FilePath "cmd.exe" -WorkingDirectory $frontendDir -ArgumentList @(
    "/c", "npm", "run", "dev", "--", "--host", $HostAddr, "--port", "$FrontendPort"
  ) -WindowStyle Hidden -PassThru

  Wait-Http "http://$HostAddr`:$BackendPort/api/health" "Backend"
  Wait-Http "http://$HostAddr`:$FrontendPort" "Frontend"

  Write-Step "Backend unit tests"
  Push-Location $backendDir
  $env:PYTHONPATH = $backendDir
  Invoke-Checked { python -m unittest discover -s tests -p "test*.py" -v } "backend unit tests"
  Pop-Location

  Write-Step "Frontend build"
  Push-Location $frontendDir
  Invoke-Checked { npm run build } "frontend build"
  Pop-Location

  if (!$SkipE2E) {
    Write-Step "Frontend E2E"
    Push-Location $frontendDir
    $env:PLAYWRIGHT_BASE_URL = "http://$HostAddr`:$FrontendPort"
    Invoke-Checked { npm run test:roadshow -- --project=msedge --workers=1 } "roadshow E2E"
    Pop-Location
  }
} catch {
  $failed = $true
  Write-Host $_ -ForegroundColor Red
} finally {
  foreach ($process in @($frontend, $backend)) {
    if ($process -and !$process.HasExited) {
      Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    }
  }
  if ($frontend) { Stop-Port $FrontendPort }
  if ($backend) { Stop-Port $BackendPort }
}

if ($failed) {
  exit 1
}

Write-Step "All tests passed"
exit 0
