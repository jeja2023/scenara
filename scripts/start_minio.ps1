# Scenara MinIO 本地后台独立启动脚本
param(
    [switch]$Foreground,
    [switch]$Stop
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
$RuntimeRoot = Join-Path $RootDir "runtime-state"
$MinioExe = Join-Path $RuntimeRoot "minio-native\minio.exe"
$DataDir = Join-Path $RuntimeRoot "minio-data"
$LogDir = Join-Path $RuntimeRoot "logs"
$LogOut = Join-Path $LogDir "minio.log"
$LogErr = Join-Path $LogDir "minio.err.log"

if ($Stop) {
    $processes = Get-Process -Name minio -ErrorAction SilentlyContinue
    if ($processes) {
        $processes | Stop-Process -Force
        Write-Host "已停止 MinIO 进程。" -ForegroundColor Yellow
    } else {
        Write-Host "未找到运行中的 MinIO 进程。" -ForegroundColor Gray
    }
    exit 0
}

if (-not (Test-Path $MinioExe)) {
    Write-Error "未找到 MinIO 可执行文件：$MinioExe"
    exit 1
}

New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

# 检查 9000 端口是否已在运行
$conn = Test-NetConnection -ComputerName 127.0.0.1 -Port 9000 -InformationLevel Quiet -WarningAction SilentlyContinue
if ($conn) {
    Write-Host "MinIO 已经在运行中 (http://127.0.0.1:9000)" -ForegroundColor Green
    Write-Host "Web 控制台: http://127.0.0.1:9001 (账号: minioadmin / 密码: minioadmin)" -ForegroundColor Cyan
    exit 0
}

$env:MINIO_ROOT_USER = "minioadmin"
$env:MINIO_ROOT_PASSWORD = "minioadmin"

if ($Foreground) {
    Write-Host "在前台启动 MinIO..." -ForegroundColor Cyan
    & $MinioExe server $DataDir --address ":9000" --console-address ":9001"
} else {
    Write-Host "在后台独立启动 MinIO..." -ForegroundColor Cyan
    $proc = Start-Process -FilePath $MinioExe `
        -ArgumentList "server `"$DataDir`" --address :9000 --console-address :9001" `
        -RedirectStandardOutput $LogOut `
        -RedirectStandardError $LogErr `
        -WindowStyle Hidden `
        -PassThru

    Start-Sleep -Seconds 1
    if (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue) {
        Write-Host "MinIO 已在后台启动 (PID: $($proc.Id))" -ForegroundColor Green
        Write-Host "  API 地址:   http://127.0.0.1:9000" -ForegroundColor White
        Write-Host "  Web 控制台: http://127.0.0.1:9001 (minioadmin / minioadmin)" -ForegroundColor White
        Write-Host "  日志文件:   $LogOut / $LogErr" -ForegroundColor Gray
    } else {
        Write-Error "MinIO 启动失败，请检查日志：$LogErr"
    }
}
