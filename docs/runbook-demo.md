# Runbook de la demo (sustentación)

Comandos en PowerShell desde la raíz del repo, con `. .\scripts\env.ps1` cargado.
Cada bloque dice **qué se demuestra**, **el comando** y **qué debe verse**.

## 0. Preparar el equipo (antes de entrar)

El equipo tiene 6 GB: cerrar navegador extra, IDEs, Teams, juegos y `wsl -t Ubuntu`.
Minikube y Floci necesitan ~3 GB.

```powershell
# 1. Docker Desktop abierto. Si Floci ya está en la red de minikube, se suelta (choque de IP).
docker compose up -d                                  # Floci
docker network disconnect aegisvolt floci 2>$null
minikube start -p aegisvolt                           # ~3 min
docker update --cpus 4 aegisvolt                      # más CPU al nodo (no cuesta RAM)
# 2. CLAVE: al arrancar, Kubernetes sube TODOS los pods a la vez, ninguno termina el
#    startupProbe y entran en bucle de reinicios (exit 137) que satura el nodo. Se bajan
#    a 0 y deploy.py los sube DE A UNO.
foreach ($ns in "aegisvolt-dev", "aegisvolt-test", "aegisvolt-prod") {
  kubectl -n $ns scale deploy --all --replicas=0 2>$null
}
curl.exe -s http://127.0.0.1:4566/_floci/health     # si no da 200: docker compose restart floci
uv run python scripts/deploy.py --env dev --skip-build
C:\Users\chifl\actions-runner\start-aegisvolt-runner.cmd   # runner (otra terminal)
```

### Modo liviano: levantar SOLO lo que pide cada prueba

`--only` deja en 0 réplicas lo demás (ahorra 100–150 MB por pod de Python):

| Prueba en vivo | Comando |
| --- | --- |
| Canary / rollback | `uv run python scripts/deploy.py --env dev --skip-build --only graphql-gateway` |
| SAGA completa | `... --only station-reservation-service billing-wallet-service energy-dispatch-service graphql-gateway` |
| Frontend + flags | `... --only graphql-gateway frontend` (+ los 3 servicios si se inicia una carga) |
| Otro ambiente | `uv run python scripts/deploy.py --env test --skip-build --only graphql-gateway` |
| Prefect | clúster detenido: `minikube stop -p aegisvolt`; Prefect solo lee Floci |

Versión nueva para el canary (build DENTRO de minikube, sin `image load`):
`uv run python scripts/deploy.py --env dev --tag v5 --only graphql-gateway`
(los servicios de dominio pasan a v5; el gateway estable conserva su versión hasta el canary).

Si el nodo se satura (pods 0/1 reiniciando, `TLS handshake timeout`): bajar a `--only` lo
mínimo y esperar a que `kubectl get nodes` responda.

## 1. Infraestructura como código y ambientes (Terraform)

| Qué | Comando | Debe verse |
| --- | --- | --- |
| Estado remoto versionado | `aws --endpoint-url http://localhost:4566 s3api list-object-versions --bucket aegisvolt-tfstate --prefix env:/dev/` | varias versiones del tfstate |
| Aislamiento por workspace | `terraform -chdir=infra/envs workspace list` | dev, test, prod |
| Recursos por ambiente | `aws --endpoint-url http://localhost:4566 dynamodb list-tables` | `aegisvolt-<tabla>-dev/test/prod` |
| Guardia del plan (R7) | `uv run pytest tests/unit/test_plan_guard.py -v` | borrar otro ambiente = bloqueado |

## 2. SAGA (GraphQL)

```powershell
uv run python scripts/run_services.py     # o el gateway en k8s
uv run pytest tests/e2e -v                 # feliz, fondos insuficientes, falla de cargador
```

Debe verse: `COMPLETED`, `COMPENSATED` con los pasos `compensate` en orden inverso, e
idempotencia (repetir el mismo `sagaId` no cobra dos veces).

## 3. Canary con rollback automático

```powershell
# construir una versión nueva (tag NUNCA reutilizado: el nodo cachea por tag)
uv run python scripts/deploy.py --env dev --tag v5 --only graphql-gateway
# versión sana: debe PROMOVER (exit 0)
uv run python scripts/canary.py --env dev --tag v5
# versión rota: 50 % de 500 inducidos, debe hacer ROLLBACK (exit 1)
uv run python scripts/canary.py --env dev --tag v5 --chaos 0.5
```

Debe verse: reparto aproximado 80/20 por `x-service-version`, la fuente de la evaluación
(FilterLogEvents, plan B porque Floci no da datapoints) y la decisión. Regla: canary Ready,
≥ 20 peticiones de la versión nueva y ≤ 5 % de 5xx.

Forzar la versión nueva para probar a mano: header `x-canary: always`.

## 4. CI/CD y gobernanza (GitHub)

| Qué | Cómo | Debe verse |
| --- | --- | --- |
| Push directo bloqueado | `git push origin dev` con un commit local | `GH013: Repository rule violations` |
| Force push bloqueado | `git push --force origin dev` | rechazado por el ruleset |
| Checks obligatorios | PR con un test roto | botón de merge deshabilitado |
| Promoción lineal | PR `feature/x -> test` | `promote-guard` en rojo |
| Plan en el PR | cualquier PR | comentario `terraform plan — workspace <base>` |

## 5. Observabilidad

```powershell
# buscar una saga fallida por correlation_id
aws --endpoint-url http://localhost:4566 logs filter-log-events `
  --log-group-name /aegisvolt/dev/graphql-gateway `
  --filter-pattern '{ $.event = \"saga_finished\" && $.outcome = \"compensated\" }'
# Prefect vive en su PROPIO entorno (choque de FastAPI con los servicios). Una sola vez:
uv venv observability/prefect/.venv --python 3.12
uv pip install --python observability/prefect/.venv -r observability/prefect/requirements.txt
$py = "observability/prefect/.venv/Scripts/python.exe"
$env:PREFECT_HOME = "$PWD\observability\prefect\.home"   # base propia: evita 'Can't locate revision'
& $py -m prefect server start                                    # terminal 1: UI :4200
$env:PREFECT_API_URL = "http://127.0.0.1:4200/api"               # terminal 2
& $py observability/prefect/health_flow.py --env dev             # Completed si todo sano
& $py observability/prefect/saga_audit_flow.py --env dev         # Failed si hay hallazgos
& $py observability/prefect/serve.py                             # programados cada 5/15 min
```

## 6. Frontend y feature flags en tiempo real

Abrir `http://dev.aegisvolt.local` (o `npm run dev` en `frontend/`). Cambiar
`SIMULATE_CHARGER_HARDWARE_FAULT` con el token: el badge `● en vivo (WSS)` actualiza sin
recargar, y la siguiente carga termina en `COMPENSATED`. En `prod` la flag sigue igual.

## Si algo falla en vivo

| Síntoma | Causa probable | Acción |
| --- | --- | --- |
| 503 del Ingress | pods aún no Ready | `kubectl -n aegisvolt-dev get pods`, esperar |
| Todo responde `v1` | tag reutilizado o env `SERVICE_VERSION` viejo | usar un tag nuevo; `kubectl set env deploy/<x> SERVICE_VERSION-` |
| `TLS handshake timeout` | nodo sin RAM | escalar a 0 lo que no se muestra |
| `get --raw /readyz` da NotFound en Git Bash | MSYS convierte la ruta | usar PowerShell o `MSYS_NO_PATHCONV=1` (canary.py ya lo verifica solo) |
| `minikube start` falla: `Address already in use` | Floci tomó la IP de minikube al reiniciar Docker | `docker network disconnect aegisvolt floci`; `minikube start -p aegisvolt` (deploy.py lo reconecta) |
| Prefect: `Can't locate revision` | `~/.prefect` migrada por otra versión | `$env:PREFECT_HOME` a una carpeta nueva |
| Canary "sin evidencia" | tráfico no llegó al canary | revisar `canary-weight` y que los dos Ingress tengan el mismo host/path |
