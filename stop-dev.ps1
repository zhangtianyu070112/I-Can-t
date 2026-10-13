param(
  [string]$Ports = "8000,5173",
  [switch]$Quiet
)

$ErrorActionPreference = "SilentlyContinue"

function Stop-PortProcess {
  param([int]$Port)

  $pids = @()

  try {
    $pids = Get-NetTCPConnection -LocalPort $Port -State Listen | Select-Object -ExpandProperty OwningProcess
  } catch {
    $pids = @()
  }

  if (!$pids -or $pids.Count -eq 0) {
    return
  }

  $pids = $pids | Sort-Object -Unique
  foreach ($processId in $pids) {
    $p = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($p) {
      if (!$Quiet) {
        Write-Host "Stop PID=$processId Port=$Port Name=$($p.ProcessName)"
      }
      Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
  }
}

$portList = $Ports -split "[,;\\s]+" | Where-Object { $_ -and $_.Trim().Length -gt 0 }
foreach ($port in $portList) {
  $p = 0
  if ([int]::TryParse($port, [ref]$p)) {
    Stop-PortProcess -Port $p
  }
}
