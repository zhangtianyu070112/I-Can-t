param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $projectRoot 'backend'
$frontendIndex = Join-Path $projectRoot 'frontend-vue\dist\index.html'
$sourceDataDir = Join-Path $backendDir 'data'
$roadshowDataDir = Join-Path $projectRoot 'roadshow-data'
$pythonExe = Join-Path $backendDir '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $pythonExe)) { $pythonExe = 'python' }

if (!(Test-Path -LiteralPath $frontendIndex)) {
  throw '缺少前端构建文件。请先在 frontend-vue 目录执行 npm ci 和 npm run build。'
}

& $pythonExe -c 'import fastapi, uvicorn, fitz, pptx'
if ($LASTEXITCODE -ne 0) { throw '缺少后端依赖。请先运行安装依赖.ps1。' }

$env:PYTHONPATH = $backendDir
foreach ($folder in @('users', 'files')) {
  $demoTarget = Join-Path $roadshowDataDir "$folder\demo"
  if (!(Test-Path -LiteralPath $demoTarget)) {
    New-Item -ItemType Directory -Force -Path (Join-Path $roadshowDataDir $folder) | Out-Null
    Copy-Item -LiteralPath (Join-Path $sourceDataDir "$folder\demo") -Destination $demoTarget -Recurse -Force
  }
}
$env:DATA_DIR = $roadshowDataDir
$env:FRONTEND_DIST = Join-Path $projectRoot 'frontend-vue\dist'
$env:APP_ENV = 'roadshow'

$selectedPort = $null
foreach ($candidate in 8000..8010) {
  if (!(Get-NetTCPConnection -LocalPort $candidate -State Listen -ErrorAction SilentlyContinue)) {
    $selectedPort = $candidate
    break
  }
}
if ($null -eq $selectedPort) { throw '8000–8010 端口均被占用。请关闭占用程序后重试。' }

$logDir = Join-Path $projectRoot 'roadshow-logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stdoutPath = Join-Path $logDir 'server.out.log'
$stderrPath = Join-Path $logDir 'server.err.log'
$server = Start-Process -FilePath $pythonExe -WorkingDirectory $backendDir `
  -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$selectedPort") `
  -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -WindowStyle Hidden -PassThru

try {
  $url = "http://127.0.0.1:$selectedPort"
  $ready = $false
  foreach ($attempt in 1..40) {
    if ($server.HasExited) { break }
    try {
      $response = Invoke-WebRequest -UseBasicParsing -Uri "$url/api/health" -TimeoutSec 2
      if ($response.StatusCode -eq 200) { $ready = $true; break }
    } catch { Start-Sleep -Milliseconds 500 }
  }
  if (!$ready) { throw "服务启动失败。请查看 $stderrPath" }
  Write-Host "路演版已启动：$url" -ForegroundColor Green
  Write-Host '点击"使用预置数据进入路演"，即可查看离线数据。关闭本窗口会停止服务。'
  if (!$NoBrowser) { Start-Process $url }
  Wait-Process -Id $server.Id
} finally {
  if (!$server.HasExited) { Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue }
}
