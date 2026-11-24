[CmdletBinding()]
param([int]$Threads = 2)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
dotnet build .\src\AsterRisk\AsterRisk.csproj -c Release --nologo
if ($LASTEXITCODE -ne 0) { throw 'Ошибка сборки.' }
dotnet .\src\AsterRisk\bin\Release\net8.0\AsterRisk.dll demo --threads $Threads
