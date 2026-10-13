param(
  [int]$BackendPort = 8000,
  [int]$VuePort = 5173,
  [string]$HostAddr = "127.0.0.1",
  [switch]$SkipKill
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $root "backend"
$vueDir = Join-Path $root "frontend-vue"

$python = Join-Path $backendDir ".venv\Scripts\python.exe"
if (Test-Path $python) {
  & $python -c "import sys; print(sys.executable)" *> $null
  if ($LASTEXITCODE -ne 0) {
    $python = "python"
  }
} else {
  $python = "python"
}

& $python -c "import fastapi, uvicorn; print('ok')" *> $null
if ($LASTEXITCODE -ne 0) {
  throw "未找到可用的 Python/FastAPI/Uvicorn 环境。请先运行 .\安装依赖.ps1。"
}

$env:PYTHONPATH = $backendDir
$env:DATA_DIR = Join-Path $backendDir "data"
$env:DEMO_MODE = "true"

foreach ($port in @($BackendPort, $VuePort)) {
  if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
    throw "端口 $port 已被占用。请关闭占用程序或指定其他端口。"
  }
}

$backendArgs = @(
  "-m", "uvicorn", "app.main:app",
  "--host", $HostAddr,
  "--port", "$BackendPort"
)
$vueArgs = @("/c", "npm", "run", "dev", "--", "--host", $HostAddr, "--port", "$VuePort")

$backend = $null
$vue = $null

try {
  $vue = Start-Process -FilePath "cmd.exe" -WorkingDirectory $vueDir -ArgumentList $vueArgs -WindowStyle Hidden -PassThru
  $backend = Start-Process -FilePath $python -WorkingDirectory $backendDir -ArgumentList $backendArgs -WindowStyle Hidden -PassThru

  Write-Host "Backend: http://$HostAddr`:$BackendPort"
  Write-Host "Vue:     http://$HostAddr`:$VuePort"
  Wait-Process -Id @($backend.Id, $vue.Id)
} finally {
  foreach ($process in @($backend, $vue)) {
    if ($process -and !$process.HasExited) {
      Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    }
  }
}
