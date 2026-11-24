[CmdletBinding()]
param([ValidateRange(1024,65535)][int]$WebPort=8093)
$ErrorActionPreference='Stop'
Push-Location $PSScriptRoot
try {
    docker version --format '{{.Server.Version}}'
    if ($LASTEXITCODE -ne 0) { throw 'Запустите Linux Engine в Docker Desktop.' }
    if (-not (Test-Path -LiteralPath '.env')) {
        $taskBytes=New-Object byte[] 32
        $taskRandom=[System.Security.Cryptography.RandomNumberGenerator]::Create()
        try { $taskRandom.GetBytes($taskBytes) } finally { $taskRandom.Dispose() }
        $taskKey=([System.BitConverter]::ToString($taskBytes)).Replace('-','').ToLowerInvariant()
        [System.IO.File]::WriteAllText((Join-Path $PSScriptRoot '.env'),"ASTER_KEY=$taskKey`n")
    }
    $taskPreviousPort=$env:ASTER_WEB_PORT
    $env:ASTER_WEB_PORT=[string]$WebPort
    try {
        docker compose config --quiet
        if ($LASTEXITCODE -ne 0) { throw 'Ошибочная конфигурация Compose.' }
        docker compose up --build --detach
        if ($LASTEXITCODE -ne 0) { throw 'Контейнеры не запущены; проверьте docker compose logs.' }
        docker compose ps
        Write-Output "Интерфейс: http://127.0.0.1:$WebPort/"
    } finally { $env:ASTER_WEB_PORT=$taskPreviousPort }
} finally { Pop-Location }
