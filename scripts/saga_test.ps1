# Plan B de la rúbrica §6.3: la SAGA con la flag de falla en el ambiente TEST.
# test vive en modo liviano (solo gateway); esto sube los 3 micros en test SIN construir
# (usa las imágenes ya construidas para dev), activa SIMULATE_CHARGER_HARDWARE_FAULT con el
# token de TEST, dispara la mutación startCharge y muestra la compensación en DynamoDB.
# Correr DESPUÉS de que termine el run del merge a test (ese run deja los micros de test en 0).
# Uso:  .\scripts\saga_test.ps1            (~4 min: ~3 de arranque escalonado + ~30 s de prueba)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$t0 = Get-Date
$micros = "station-reservation-service", "billing-wallet-service", "energy-dispatch-service"

Write-Host "[1/5] dev a 0 (libera RAM del nodo de 2 GB; dev ya se mostró)"
kubectl -n aegisvolt-dev scale deploy --all --replicas=0 | Out-Null

$img = kubectl -n aegisvolt-dev get deploy station-reservation-service `
  -o jsonpath="{.spec.template.spec.containers[0].image}"
$tag = $img.Split(":")[-1]
Write-Host "[2/5] 3 micros + gateway en test con la imagen ya construida $tag (sin build)"
uv run python scripts/deploy.py --env test --skip-build --tag $tag --only @micros graphql-gateway
if ($LASTEXITCODE -ne 0) { throw "deploy.py falló" }

Write-Host "[3/5] port-forward a los servicios de test"
$pf = @(
  @{ svc = "graphql-gateway"; port = 8000 },
  @{ svc = "station-reservation-service"; port = 8001 },
  @{ svc = "billing-wallet-service"; port = 8002 }
) | ForEach-Object {
  Start-Process kubectl -WindowStyle Hidden -PassThru -ArgumentList @(
    "-n", "aegisvolt-test", "port-forward", "svc/$($_.svc)", "$($_.port):8000")
}
try {
  foreach ($i in 1..60) {
    try {
      Invoke-WebRequest http://127.0.0.1:8000/readyz -UseBasicParsing -TimeoutSec 2 | Out-Null
      break
    }
    catch { Start-Sleep -Milliseconds 500 }
  }

  Write-Host "[4/5] flag de falla ON en test + mutación startCharge (prueba e2e escenario 3)"
  # Token de TEST desde .env, sin imprimirlo (cada ambiente tiene el suyo).
  $line = Get-Content .env | Where-Object { $_ -like "ADMIN_TOKEN_TEST=*" } | Select-Object -First 1
  if (-not $line) { throw "Falta ADMIN_TOKEN_TEST en .env" }
  $env:ADMIN_TOKEN = $line.Split("=", 2)[1].Trim()
  $env:GATEWAY_URL = "http://127.0.0.1:8000"
  uv run pytest tests/e2e/test_saga_e2e.py -k "escenario_3" -v --no-header -p no:cacheprovider
  $ok = $LASTEXITCODE -eq 0

  Write-Host "[5/5] evidencia en las tablas de TEST (última saga compensada)"
  $q = aws --endpoint-url http://localhost:4566 dynamodb scan --table-name aegisvolt-sagas-test `
    --filter-expression "#s = :c" `
    --expression-attribute-names '{\"#s\":\"status\"}' `
    --expression-attribute-values '{\":c\":{\"S\":\"COMPENSATED\"}}' `
    --output json | ConvertFrom-Json
  $saga = $q.Items | Sort-Object { $_.updated_at.S } | Select-Object -Last 1
  $id = $saga.saga_id.S
  Write-Host "  saga $id -> $($saga.status.S)"
  aws --endpoint-url http://localhost:4566 dynamodb query --table-name aegisvolt-billing-test `
    --index-name by-saga --key-condition-expression "saga_id = :id" `
    --expression-attribute-values "{\`":id\`":{\`"S\`":\`"$id\`"}}" `
    --query "Items[].{sk:sk.S,monto:amount_cents.N}" --output table
  # Al liberar, el conector pierde su saga_id: se consulta por la estación de la saga.
  $st = $saga.station_id.S
  aws --endpoint-url http://localhost:4566 dynamodb query --table-name aegisvolt-reservations-test `
    --key-condition-expression "station_id = :st" `
    --expression-attribute-values "{\`":st\`":{\`"S\`":\`"$st\`"}}" `
    --query "Items[].{estacion:station_id.S,conector:connector_id.S,estado:status.S}" --output table
}
finally {
  $pf | ForEach-Object { Stop-Process -Id $_.Id -ErrorAction SilentlyContinue }
  Remove-Item Env:ADMIN_TOKEN -ErrorAction SilentlyContinue
}
$res = if ($ok) { "OK" } else { "FALLÓ" }
"Listo en {0:N0} s (prueba {1})" -f ((Get-Date) - $t0).TotalSeconds, $res
