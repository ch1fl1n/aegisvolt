# Carga las variables de .env en la sesion ACTUAL de PowerShell.
# Uso (con punto y espacio delante):  . .\scripts\env.ps1
$envFile = Join-Path $PSScriptRoot '..\.env'
if (-not (Test-Path $envFile)) { throw "No existe .env. Ejecuta: Copy-Item .env.example .env" }

Get-Content $envFile | Where-Object { $_ -match '^\s*[^#\s][^=]*=' } | ForEach-Object {
    $k, $v = $_ -split '=', 2
    Set-Item -Path "env:$($k.Trim())" -Value $v.Trim()
}
Write-Host "Variables cargadas: AWS_ENDPOINT_URL=$env:AWS_ENDPOINT_URL  AEGIS_ENV=$env:AEGIS_ENV"
