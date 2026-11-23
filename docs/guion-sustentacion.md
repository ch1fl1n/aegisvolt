# Guion de la sustentación (demo virtual en vivo, ~13 min)

Complementa `runbook-demo.md` (comandos detallados y tabla "Si algo falla en vivo").
Regla de oro: en vivo no se construye nada pesado a mano. Lo único que corre solo en vivo es el
pipeline (merge de un PR dev->test ya en verde), y corre en test, sin tocar la SAGA de dev.

## A0. La víspera (deja el PR de promoción listo)

| Paso | Comando / acción | Listo cuando |
| --- | --- | --- |
| Commit nuevo en dev | PR `docs/...` -> dev con los últimos cambios de docs; merge | deploy de dev por merge en verde (~7 min) |
| PR de promoción | PR dev -> test, SIN mergear | 8/8 checks verdes y `CLEAN` (~5 min) |

El PR queda abierto toda la noche: sus checks no caducan. Mañana solo se revisa que siga `CLEAN`.

Comandos (con runner y clúster arriba; cada demo gasta un PR dev->test, por eso se rehace).
Todo en T1, uno por uno; `gh` ya está autenticado:

```powershell
git switch dev; git pull
git switch -c docs/ensayo-AAAAMMDD                    # rama nueva desde dev
# ... cambio real (p. ej. una línea en docs con lo aprendido) ...
git add -A; git commit -m "docs: ajustes del ensayo"; git push -u origin HEAD
gh pr create --base dev --title "docs: ajustes del ensayo" --body "Ajustes del ensayo."
Start-Sleep 20; gh pr checks --watch                  # ~5 min; todo en verde
kubectl -n aegisvolt-test scale deploy --all --replicas=0   # RAM para el canary de dev
kubectl -n aegisvolt-prod scale deploy --all --replicas=0
gh pr merge --merge                                   # dispara el deploy de dev (~7 min)
Start-Sleep 20
$run = gh run list --branch dev --workflow deploy.yml --limit 1 --json databaseId -q ".[0].databaseId"
gh run watch $run                                     # debe terminar en verde
gh pr create --base test --head dev --title "release: promover dev a test" --body "Demo en vivo."
$pr = gh pr list --base test --head dev --json number -q ".[0].number"
Start-Sleep 20; gh pr checks $pr --watch              # ~5 min; todo en verde, SIN mergear
```

Si el deploy de dev sale inconcluso por RAM: `gh run rerun $run --failed` con test y prod en 0.
(test vuelve a subir en la preparación de mañana, paso -49.)
Mañana: `gh pr list --base test --head dev` muestra el PR y `gh pr checks <n>` todo en verde.

## A. Preparación (orden: lo más lento primero; total ~20 min + ensayo)

| T | Paso | Comando / acción | Tiempo medido | Mientras espera |
| --- | --- | --- | --- | --- |
| -60 | Cerrar lo pesado | Chrome, otras ventanas de Claude, juegos | | |
| -59 | Docker | abrir Docker Desktop | ~2 min | abrir 5 terminales y en TODAS `cd C:\Users\chifl\aegisvolt` |
| -57 | Floci | `docker compose up -d`; `docker network disconnect aegisvolt floci`; `docker compose restart floci` | ~30 s | |
| -56 | Clúster | `minikube start -p aegisvolt`; `docker update --cpus 4 aegisvolt` | ~3 min | doble clic al runner |
| -53 | Anti-tormenta | escalar dev/test/prod a 0 (runbook §0) | ~40 s | |
| -52 | dev completo | `uv run python scripts/deploy.py --env dev --skip-build` | ~3 min | abrir el editor |
| -49 | test (destino del merge en vivo) | `uv run python scripts/deploy.py --env test --skip-build --only graphql-gateway` | ~1,5 min | |
| -47 | prod en 0 | no se sube (RAM); "prod intacto" se muestra con DynamoDB, sin pods | | |
| -45 | Imágenes de canary manual | `uv run python scripts/deploy.py --env dev --tag demo1 --only graphql-gateway` (y `demo2` igual) | ~1,5 min c/u | |
| -43 | Acceso web | T3: `while ($true) { kubectl -n ingress-nginx port-forward svc/ingress-nginx-controller 8080:80; Start-Sleep 2 }` (el bucle reconecta si el pod del Ingress se reinicia); Chrome con `--host-resolver-rules="MAP *.aegisvolt.local 127.0.0.1"` | ~10 s | |
| -42 | Prefect | T4: `$py = "observability/prefect/.venv/Scripts/python.exe"; $env:PREFECT_HOME = "$PWD\observability\prefect\.home"; & $py -m prefect server start`; T5 (mismas 2 variables + `$env:PREFECT_API_URL = "http://127.0.0.1:4200/api"`): health_flow + saga_audit_flow; luego `serve.py` | ~2 min | abrir pestañas `http://dev.aegisvolt.local:8080` |
| -40 | Reset + verificar | T1: `uv run python scripts/reset_demo.py` (conectores libres, saldo 500, flags OFF); runner Idle; PR dev->test `CLEAN` | ~30 s | |
| -35 | Ensayo rápido | §C de punta a punta SIN mergear el PR | ~10 min | |
| -15 | Calma | CERRAR la app de Claude (~800 MB) y todo lo que no sea Teams + demo; RAM libre > 500 MB | | |

Los pasos de deploy van en serie: comparten un nodo de 2 GB (tormenta de reinicios si se solapan).
Durante el merge en vivo solo corren el gateway de test + su canary: dev se baja a 0 justo antes
del merge (min 6:00). Con dev arriba el host (6 GB) pagina y el canary da inconcluso (ensayo
del 22-nov).

## B. Qué dejar ABIERTO antes de entrar

1. T1 (PowerShell, raíz del repo): comandos de la demo.
2. T2: `kubectl get pods -n aegisvolt-test -w` (se ve el canary del pipeline subir y bajar).
3. T3: port-forward del Ingress (8080). T4: servidor de Prefect. T5: `serve.py`.
4. Ventana del runner (`run.cmd`): sin ella el merge no despliega. No cerrar.
5. Chrome con el flag de hosts, pestañas en este orden (sin IDE: ahorra RAM):
   - GitHub: `README.md`; PR dev -> test en verde; Actions; `.github/workflows/deploy.yml`;
     Settings > Rules;
   - frontend `http://dev.aegisvolt.local:8080`; Prefect `http://127.0.0.1:4200`.

### Links (abrir en este orden en Chrome)

| Pestaña | URL | Qué mostrar |
| --- | --- | --- |
| README | `https://github.com/ch1fl1n/aegisvolt` | diagrama |
| PR de promoción | `https://github.com/ch1fl1n/aegisvolt/pulls?q=is%3Aopen+base%3Atest+head%3Adev` | el PR abierto dev->test (el de A0, número nuevo): pestaña Checks en verde; Conversation -> **Merge pull request** |
| Actions | `https://github.com/ch1fl1n/aegisvolt/actions/workflows/deploy.yml` | tras el merge, el run de arriba "Merge pull request #N from ch1fl1n/dev" -> job `deploy-test` -> pasos; respaldo: run verde `https://github.com/ch1fl1n/aegisvolt/actions/runs/45099540645` (paso "Canary": 46 peticiones, 0 % -> PROMOCIÓN) |
| deploy.yml | `https://github.com/ch1fl1n/aegisvolt/blob/dev/.github/workflows/deploy.yml` | `ENV_NAME`, `workspace select`, canary |
| Rulesets | `https://github.com/ch1fl1n/aegisvolt/settings/rules` | clic en `protected-branches`: dev/test/prod, bypass vacío, 4 reglas (deletion, force push, PR, 6 checks) |
| Frontend | `http://dev.aegisvolt.local:8080` | SAGA, flags |
| Prefect | `http://127.0.0.1:4200` | runs de health y saga-audit |

## C. Demo (~13 min; teoría de cada bloque en `explicaciones-demo.md`)

Terminales: **T1** todos los comandos de la demo · **T2** `kubectl get pods -n aegisvolt-test -w`
(solo mirar) · **T3** port-forward en bucle · **T4** servidor Prefect · **T5** `serve.py` (T3-T5
no se tocan). Todo lo demás es en Chrome. Código para mostrar: `explicaciones-demo.md` §11.

Orden: primero todo lo que usa dev; luego dev a 0 y merge en vivo; mientras el run corre (~6,5
min) se explica lo que no necesita pods. Ensayo del 22-nov: con dev arriba el canary dio
inconcluso (503 por RAM); con dev en 0 promovió (46 peticiones, 0 % 5xx, run de 6:16).

| Min | Bloque | Hacer | Decir (una idea) |
| --- | --- | --- | --- |
| 0:00 | Arquitectura | Chrome: `README.md` en GitHub (diagrama) | API GW -> VPC Link -> NLB -> Ingress -> gateway GraphQL -> 3 micros; Floci emula AWS |
| 1:00 | IaC | T1: `terraform -chdir=infra/envs workspace list` + versiones del tfstate (abajo, §6.1) | un estado por workspace en S3 versionado, KMS propia y lock |
| 2:00 | SAGA feliz | T1: copiar token (abajo) -> Chrome frontend dev: pegarlo; st-norte **c1** -> Iniciar carga -> COMPLETED (~10-15 s, spinner) | orquestación en el gateway, bitácora en DynamoDB |
| 3:00 | SAGA compensada | Chrome frontend: `SIMULATE_CHARGER_HARDWARE_FAULT` ON, esperar 5 s, conector **c2** -> Iniciar carga -> COMPENSATED; flag OFF | compensa en orden inverso: reembolso y libera conector |
| 4:00 | Flags | Chrome frontend: `ENABLE_FAST_CHARGE_BOOST` ON, esperar 5 s, conector **c2** -> Iniciar carga -> COMPLETED a **150 kW** (antes 50 kW) | flags por ambiente en DynamoDB, caché 5 s, push por WSS, sin redesplegar |
| 4:30 | Rollback | T1: `uv run python scripts/canary.py --env dev --tag demo1 --chaos 0.5` (~1,5 min) | versión rota: 5xx de ESA versión > 5 % -> rollback, estable intacto |
| 6:00 | **Merge en vivo** | T1: `kubectl -n aegisvolt-dev scale deploy --all --replicas=0`; Chrome PR dev->test: 8 checks, promote-guard; **merge**; Chrome Actions: abrir el run | nada llega a test sin PR y checks; el merge dispara el despliegue solo |
| 6:30 | Cómo elige ambiente | Chrome: `deploy.yml` en GitHub (`ENV_NAME: ${{ github.ref_name }}` -> `terraform workspace select`) | rama = ambiente: detección dinámica del target branch |
| 7:30 | Ruleset | Chrome: GitHub Settings > Rules -> `protected-branches`; si pide probarlo: T1 push directo/force (abajo, §6.2) | push directo o `--force` a test/prod -> `GH013` |
| 8:00 | Prod intacto | T1: los 2 `scan` de flags de abajo | la flag de dev no existe en prod: otra tabla, otro workspace, otro token |
| 9:00 | Observabilidad | Chrome Prefect: `environment-health` y `saga-audit` (artifact); T1: `uv run python scripts/trace_saga.py` (§6.4) | detecta lo que el SAGA solo no puede ver (huérfanas) |
| 10:30 | **Canary automático** | Chrome Actions: `terraform apply (test)` -> build -> canary 20 % -> PROMOVIDO; T2: pods canary | rama -> workspace -> apply -> canary con métricas de CloudWatch, sin humano |
| 12:30 | Cierre | | patrones: SAGA, canary, IaC por workspace, flags, observabilidad |
| +4 | Solo si pide SAGA en test (§6.3) | T1: `.\scripts\saga_test.ps1` | flag de falla en TEST + mutación + compensación en tablas de test |

Por qué c1 y luego c2: una carga COMPLETED deja su conector RESERVED (sigue cargando); en el
mismo conector la falla saldría en el paso 1 (reserva) y no en el 3. Cada llamada del gateway
espera hasta 20 s (`HTTP_TIMEOUT_S`): con el host paginando, Floci tardó 6-20 s (ensayo 22-nov).

Mientras espera (relleno con contenido, en este orden):

- **Rollback, paso [1/4] (~1 min arrancando el pod):** por qué canary y no blue-green (expone
  solo el 20 %, con datos reales); por qué la métrica es del SERVIDOR y por versión (el cliente
  no ve timeouts internos; la dimensión `Version` aísla al canary); las 4 reglas (fail-safe,
  anti-dilución, promoción con red, primer despliegue).
- **Si preguntan por qué llegó ~13 % y no 20 %:** el peso es probabilístico por petición; con
  200 peticiones la muestra varía. Por eso hay mínimo de 20 peticiones (si no: inconcluso).
- **Run del merge (~6,5 min):** terraform apply (1,5 min) -> plan_guard; build (1 min) -> tag =
  sha; canary (3 min). Mientras: `deploy.yml`, ruleset, prod intacto, Prefect (filas 6:30-9:00).

Comandos de T1 que piden las preguntas de la guía (§6), probados el 22-nov:

```powershell
# §6.1 versiones del tfstate de dev (restaurar = copy-object con versionId; ver explicaciones §10)
aws --endpoint-url http://localhost:4566 s3api list-object-versions --bucket aegisvolt-tfstate `
  --prefix env:/dev/ --max-items 5 --query "Versions[].[LastModified,IsLatest,VersionId]" --output table
# §6.2 push directo y forzado a test SIN tocar tu carpeta: commit vacío encima de test, en memoria
git fetch origin
$c = git commit-tree 'origin/test^{tree}' -p origin/test -m 'prueba: push directo (debe rechazarse)'
# Probado 22-nov: los dos -> GH013 "Changes must be made through a pull request" + "6 of 6 required
# status checks are expected"; test sigue en el mismo sha. El commit va ENCIMA de test (avance
# rápido), por eso --force no muestra la regla non_fast_forward: lo frena antes la de PR.
# Reescribir historia (non_fast_forward) también está bloqueado: Settings > Rules lo muestra; no se prueba
# en vivo porque, si fallara, borraría commits de test.
git push origin "$($c):refs/heads/test"
git push --force origin "$($c):refs/heads/test"
# §6.4 saga fallida -> correlation_id -> logs de los 4 servicios en CloudWatch
uv run python scripts/trace_saga.py
```

Comandos de T1 (copiar tal cual):

```powershell
# Token de admin de dev al portapapeles (no se imprime); pegarlo en el panel de flags
(Get-Content .env | Where-Object { $_ -like "ADMIN_TOKEN=*" }).Split("=", 2)[1].Trim() | Set-Clipboard
# Prod intacto: flags de dev vs prod (prod sin filas = todas en su valor por defecto, apagadas)
aws --endpoint-url http://localhost:4566 dynamodb scan --table-name aegisvolt-flags-dev `
  --query "Items[].{flag:flag_name.S,on:enabled.BOOL}" --output table
aws --endpoint-url http://localhost:4566 dynamodb scan --table-name aegisvolt-flags-prod `
  --query "Items[].{flag:flag_name.S,on:enabled.BOOL}" --output table
```

Si a las 10:30 el run aún no termina: mostrar el paso en curso del log y seguir hablando del
canary (§C2). Si falló inconcluso: es el fail-safe (rollback por falta de datos); mostrar el
run verde del ensayo (`gh run list --branch test --workflow deploy.yml`) y explicar la causa.

### Repetible (ensayo hoy = demo mañana)

Cada demo consume UN PR dev->test; todo lo demás queda igual. Al terminar un ensayo:

1. `uv run python scripts/reset_demo.py`: libera conectores (una carga COMPLETED deja el suyo
   RESERVED), saldo 500 y flags OFF.
2. No promover `demo1` ni `demo2` (si se promovió `demo2`, construir `demo3` para la próxima).
3. Volver a subir dev (quedó en 0 por el merge): `uv run python scripts/deploy.py --env dev --skip-build`
   (~3 min).
4. Rehacer A0: commit nuevo en dev (docs con lo aprendido) + PR dev->test en verde sin mergear.

Tiempos objetivo: preparación < 1 h (medida ~24 min + ensayo); demo < 15 min (guion ~13 min).

## C2. Canary en vivo: que funcione y cómo justificarlo

Lo que califica la rúbrica es el canary AUTOMÁTICO del pipeline ("despliegue tras el merge: rama
-> workspace -> terraform apply -> canary", con 10-20 % del tráfico). Se ve en vivo con el merge
del PR dev->test (min 6:00 y 10:30). El canary manual solo muestra el camino de rollback.

Antes de entrar (preparación): imagen `demo1` construida (paso -45) y comprobar
`minikube -p aegisvolt image ls | Select-String demo1`. El estable de dev NO puede ser `demo1`.

En vivo SOLO se corre la versión rota (`--chaos 0.5`): el rollback deja el estable intacto, así
que se puede repetir. Si el profe pide ver una promoción sana, usar un tag NUEVO (`demo2`, ~1 min
de build); nunca `demo1` sin chaos, porque al promoverse el estable pasaría a `demo1` y el
siguiente intento abortaría con "el estable ya es demo1" (regla anti-dilución).

Qué decir mientras corre (lo imprime el script en 4 pasos):

1. **Despliega** la versión nueva en un Deployment aparte (1 réplica); el estable no se toca.
2. **20 % del tráfico** al canary con la anotación `canary-weight` del Ingress NGINX: es por
   petición, no por pod; el 80 % sigue en la versión probada.
3. **Tráfico real** por el Ingress; cada respuesta trae `x-service-version` para ver el reparto.
4. **Decide con datos del servidor** (CloudWatch en Floci), no del cliente: tasa de 5xx SOLO de
   la versión canary (dimensión `Version`). Plan A métricas; plan B logs (Floci no da
   datapoints de metric filters, R5). Umbral 5 %: con chaos 0.5 sale ~50 % -> ROLLBACK.

Por qué es seguro (4 reglas, modelo Argo Rollouts Successful/Failed/Inconclusive):

- **Fail-safe:** si no se puede medir o hay pocas peticiones -> rollback (en CI no hay humano).
- **Anti-dilución:** estable y canary con el mismo tag mezclarían su tráfico en la métrica y una
  versión rota podría promoverse -> se aborta antes de tocar nada.
- **Promoción con red:** si el rollout del estable no termina, `rollout undo` + peso 0.
- **Primer despliegue:** sin versión anterior no hay contra qué medir -> entra como estable y el
  canary se omite con aviso (igual que la primera revisión en Argo Rollouts).

## D. Teoría y preguntas

Están en `explicaciones-demo.md` (mismo orden que §C; preguntas difíciles y banco §6 al final).

## F. Si algo falla en vivo (plan B por bloque)

Regla: no improvisar arreglos en vivo. Decir qué pasó, por qué es seguro y mostrar la evidencia
ya guardada. Todo lo de esta tabla se vio en los ensayos del 22-nov.

| Síntoma | Qué hacer (T1/Chrome) | Qué decir |
| --- | --- | --- |
| `dev.aegisvolt.local:8080` no carga (ERR_CONNECTION_REFUSED) | T3: si no tiene el bucle, `while ($true) { kubectl -n ingress-nginx port-forward svc/ingress-nginx-controller 8080:80; Start-Sleep 2 }`; Ctrl+F5 | el pod del Ingress se reinició (RAM) y el port-forward muere con él; el bucle reconecta |
| "Iniciar carga" tarda | esperar (hasta ~20 s por paso); ver el spinner | en local Floci va lento por la RAM; el gateway espera 20 s y reintenta, seguro por idempotencia |
| Sale COMPENSATED con `ReadTimeout` en vez de COMPLETED | no repetir en el mismo conector; usar otro (c2) y reintentar | la saga hizo lo correcto: no pudo confirmar el paso y compensó (reembolso + liberar); es el patrón funcionando |
| La falla compensa en el paso 1 (reserva) | era el mismo conector de la carga feliz: usar c2 | una carga COMPLETED deja su conector RESERVED (está cargando) |
| Una flag no cambia | revisar que el token esté pegado; esperar 5 s | caché de 5 s por réplica; sin token el interruptor está deshabilitado (FORBIDDEN) |
| `canary.py` dice "ABORTADO: el estable ya es demo1" | usar `--tag demo2` (construirlo ~1,5 min) | regla anti-dilución: con el mismo tag la métrica se mezclaría |
| `canary.py` da ROLLBACK (inconcluso) | mostrar la salida: es el fail-safe | sin datos suficientes no se promueve; en CI no hay humano |
| El merge no arranca el run | Chrome Actions: ¿runner Idle? abrir la ventana de `run.cmd` | el job corre en el runner self-hosted (llega a Floci y minikube) |
| El run del merge sale inconcluso / falla | mostrar el log (paso Canary) y el run verde de respaldo `https://github.com/ch1fl1n/aegisvolt/actions/runs/45099540645` | el canary aplicó fail-safe y revirtió: prod/test nunca quedan rotos. El ensayo con dev en 0 promovió (46 peticiones, 0 %) |
| El run tarda más de 7 min | seguir con 6:30-9:00 y volver al final | terraform 1,5 + build 1 + canary 3 min |
| Prefect UI no abre | T4: `$py = "observability/prefect/.venv/Scripts/python.exe"; $env:PREFECT_HOME = "$PWD\observability\prefect\.home"; & $py -m prefect server start` | Prefect corre local; la auditoría se puede correr directo: `& $py observability/prefect/saga_audit_flow.py --env dev` |
| Piden la SAGA en TEST (§6.3) | T1: `.\scripts\saga_test.ps1` (~4,5 min, después del run) | test vive en modo liviano (aprobado); el script sube los micros y muestra CHARGE+REFUND en las tablas de test |
| Piden ver código | `explicaciones-demo.md` §11 (rutas) -> abrir en GitHub | |

## G. Check final

### Esta noche, antes de apagar (en este orden)

1. A0 completo (comandos arriba): commit con todo lo de hoy -> PR a dev -> merge -> deploy de dev
   en verde -> PR dev->test abierto con 8/8 verdes, SIN mergear.
2. `uv run python scripts/reset_demo.py` -> "dev limpio para la demo".
3. Verificar y apagar:

```powershell
gh pr list --base test --head dev                      # debe mostrar el PR nuevo
gh pr checks (gh pr list --base test --head dev --json number -q ".[0].number")   # todo pass
minikube -p aegisvolt image ls | Select-String demo1   # imagen del rollback
minikube stop -p aegisvolt
docker compose stop
```

Cerrar T1-T5, el runner y Docker Desktop. No hace falta `wsl --shutdown` (sí ayuda si la RAM
sigue alta: libera la memoria de WSL).

### Mañana, antes de entrar (sobre la preparación §A)

- [ ] Preparación §A completa; en -40: `reset_demo.py` OK y PR `CLEAN`.
- [ ] Runner en la ventana `run.cmd` diciendo "Listening for Jobs".
- [ ] `kubectl get pods -A | Select-String -NotMatch Running,Completed` vacío.
- [ ] Frontend dev abre con Ctrl+F5; token copiado; flags OFF; saldo 500,00.
- [ ] Prefect `http://127.0.0.1:4200` con runs de health/saga-audit.
- [ ] App de Claude CERRADA; solo Teams + pestañas de la demo; RAM libre > 500 MB.
- [ ] `$t0 = Get-Date` en T1 al empezar.
