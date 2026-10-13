param()

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendRequirements = Join-Path $root "backend\requirements.txt"
$frontendDir = Join-Path $root "frontend-vue"

Write-Host "[1/2] 安装 Python 依赖..." -ForegroundColor Cyan
& python -m pip install -r $backendRequirements
if ($LASTEXITCODE -ne 0) {
  throw "Python 依赖安装失败，退出码：$LASTEXITCODE"
}

Write-Host "[2/2] 安装前端依赖..." -ForegroundColor Cyan
Push-Location $frontendDir
try {
  & npm ci
  if ($LASTEXITCODE -ne 0) {
    throw "前端依赖安装失败，退出码：$LASTEXITCODE"
  }
} finally {
  Pop-Location
}

Write-Host "依赖安装完成。可双击 启动源码.bat 启动项目。" -ForegroundColor Green
