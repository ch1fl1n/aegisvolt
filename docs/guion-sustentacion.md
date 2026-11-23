# Guion de la sustentación (demo virtual en vivo, ~13 min)

Este documento basta solo: preparación, demo minuto a minuto, qué decir, qué hacer si algo falla.
Teoría y código: `explicaciones-demo.md`. Comandos de referencia: `runbook-demo.md`.

Regla de oro: en vivo no se construye nada a mano. Lo único que corre solo es el pipeline (merge
del PR dev->test ya en verde), y corre en test, después de terminar con la SAGA de dev.

## 0. Cómo quedó todo la noche del 22-nov (no hay que rehacer nada de esto)

- PR de promoción **#14** dev->test abierto, 8/8 checks en verde, SIN mergear:
  `https://github.com/ch1fl1n/aegisvolt/pull/14`. Es el que se mergea en vivo.
- dev desplegado por el pipeline (run 45113560271 en verde) con el commit `f6a2c92`: frontend
  con spinner/esqueletos, gateway con `HTTP_TIMEOUT_S=20`. `deploy.py --skip-build` conserva
  esas imágenes al volver a subir dev.
- test con el gateway `ab992cd` (distinto del que llega con el merge: el canary puede comparar).
- Imagen `demo1` (rollback manual) ya construida dentro de minikube: no hay que reconstruirla.
- `reset_demo.py` corrido: conectores libres, saldo 500, flags OFF.
- Probado esa noche con las imágenes del CI: switch con spinner, carga feliz c1, fondos
  insuficientes (acc-pobre), falla del cargador c2, `trace_saga.py` con los 4 servicios, push
  directo/force a test rechazado (GH013).

## A. Preparación (~25 min; empezar 60 min antes)

Abrir 5 terminales PowerShell (T1-T5) y en TODAS: `cd C:\Users\chifl\aegisvolt`.
Los pasos van EN SERIE y en orden: el nodo tiene 2 GB y dos deploys a la vez provocan una
tormenta de reinicios. Copiar los comandos del bloque de abajo (P1, P2…), uno por uno, en la
terminal indicada. Si un paso no da el "Listo cuando", ir a la columna "Si no".

| T | Paso | Terminal | Listo cuando (tiempo) | Si no |
| --- | --- | --- | --- | --- |
| -60 | Cerrar Chrome, juegos, IDEs; abrir Docker Desktop | | ballena "Engine running" (~2 min) | reiniciar Docker Desktop |
| -58 | P1 Floci | T1 | el health responde JSON (~30 s) | `docker compose restart floci` y repetir el health |
| -57 | P2 clúster | T1 | "Done!" (~3 min) | repetir `minikube start -p aegisvolt` |
| -54 | P3 anti-tormenta (todo a 0) | T1 | 3 bloques de "scaled" (~40 s) | esperar 30 s y repetir |
| -53 | P4 runner | T1 | se abre la ventana "AegisVolt runner (no cerrar)" con "Listening for Jobs" | cerrarla y repetir P4 |
| -52 | P5 dev completo | T1 | termina sin error, 5 servicios listos (~3 min) | repetir P5 (es idempotente) |
| -49 | P6 test (destino del merge) | T1 | termina sin error (~1,5 min) | repetir P6 |
| -47 | P7 imagen demo1 | T1 | aparece `graphql-gateway:demo1` | construirla (comando comentado en P7, ~1,5 min) |
| -46 | P8 port-forward en bucle | T3 | "Forwarding from 127.0.0.1:8080" | se reconecta solo; dejarlo |
| -45 | P9 Chrome de la demo | T1 | carga "AegisVolt DEV" | Ctrl+F5; mirar T3 |
| -44 | P10 servidor Prefect | T4 | "Check out the dashboard at http://127.0.0.1:4200" (~1 min) | cerrar T4 y repetir |
| -43 | P11 flows de Prefect | T5 | runs visibles en `http://127.0.0.1:4200`; `serve.py` queda corriendo (~2 min) | §F "Prefect" |
| -40 | P12 pods sanos | T1 | solo la línea de encabezado | esperar 1 min y repetir; si uno sigue reiniciando: `kubectl -n aegisvolt-dev rollout restart deploy/<nombre>` |
| -39 | P13 prueba de humo | T1 + Chrome demo | token pegado; st-norte `c1`, `acc-demo` -> COMPLETED | §F "Iniciar carga" |
| -37 | P14 reset | T1 | "Listo en ~25 s: dev limpio para la demo" | "no respondió": dev no está arriba, repetir P5 |
| -36 | P15 PR de promoción | T1 | `OPEN` y `CLEAN` | §F "PR #14" |
| -35 | P16 vigilar test | T2 | queda mirando (se ve el canary del merge) | |
| -34 | Pestañas de §B en el Chrome NORMAL (sesión de GitHub) | Chrome | todas cargadas | |
| -20 | CERRAR la app de Claude (~800 MB) y todo lo que no sea Teams + 2 Chrome + terminales | | memoria libre > 500 MB (Administrador de tareas) | cerrar pestañas extra |
| -5 | Chrome demo: Ctrl+F5, pegar token (P13), flags OFF, saldo 500,00 | Chrome | todo visible | §F |

```powershell
# P1 (T1) Floci
docker compose up -d
docker network disconnect aegisvolt floci 2>$null   # si dice que no está conectado: normal
curl.exe -s http://127.0.0.1:4566/_floci/health
# P2 (T1) clúster
minikube start -p aegisvolt
docker update --cpus 4 aegisvolt
# P3 (T1) anti-tormenta: al arrancar todos los pods suben a la vez y se reinician en bucle
foreach ($ns in "aegisvolt-dev", "aegisvolt-test", "aegisvolt-prod") { kubectl -n $ns scale deploy --all --replicas=0 }
# P4 (T1) runner en su propia ventana (NO cerrarla)
Start-Process C:\Users\chifl\actions-runner\start-aegisvolt-runner.cmd
# P5 (T1) dev completo, servicio por servicio (conserva las imágenes f6a2c92 del CI)
uv run python scripts/deploy.py --env dev --skip-build
# P6 (T1) test: solo el gateway (destino del merge en vivo)
uv run python scripts/deploy.py --env test --skip-build --only graphql-gateway
# P7 (T1) imagen de la versión rota para el rollback manual
minikube -p aegisvolt image ls | Select-String demo1
# si no aparece: uv run python scripts/deploy.py --env dev --tag demo1 --only graphql-gateway
# P8 (T3) acceso web (el bucle reconecta si el pod del Ingress se reinicia)
while ($true) { kubectl -n ingress-nginx port-forward svc/ingress-nginx-controller 8080:80; Start-Sleep 2 }
# P9 (T1) Chrome de la demo: perfil aparte que resuelve *.aegisvolt.local a 127.0.0.1
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir=$env:TEMP\aegis-chrome "--host-resolver-rules=MAP *.aegisvolt.local 127.0.0.1" http://dev.aegisvolt.local:8080
# P10 (T4) servidor de Prefect
$py = "observability/prefect/.venv/Scripts/python.exe"; $env:PREFECT_HOME = "$PWD\observability\prefect\.home"
& $py -m prefect server start
# P11 (T5) primeros runs y programación cada 5/15 min
$py = "observability/prefect/.venv/Scripts/python.exe"; $env:PREFECT_HOME = "$PWD\observability\prefect\.home"
$env:PREFECT_API_URL = "http://127.0.0.1:4200/api"
& $py observability/prefect/health_flow.py --env dev
& $py observability/prefect/saga_audit_flow.py --env dev    # sale Failed: tiene hallazgos (ver §C)
& $py observability/prefect/serve.py
# P12 (T1) pods sanos
kubectl get pods -A | Select-String -NotMatch "Running|Completed"
# P13 (T1) token al portapapeles -> pegarlo en el panel de flags; luego carga st-norte c1
(Get-Content .env | Where-Object { $_ -like "ADMIN_TOKEN=*" }).Split("=", 2)[1].Trim() | Set-Clipboard
# P14 (T1) dejar dev como al empezar (libera c1, saldo 500, flags OFF)
uv run python scripts/reset_demo.py
# P15 (T1) el PR que se mergea en vivo
gh pr view 14 --json state,mergeStateStatus
# P16 (T2) mirar los pods de test
kubectl get pods -n aegisvolt-test -w
```

Prod NO se sube (RAM): "prod intacto" se muestra con DynamoDB (tablas de prod), sin pods.
Durante el merge en vivo solo corren el gateway de test y su canary: dev se baja a 0 justo antes
del merge. Con dev arriba el host (6 GB) pagina y el canary dio inconcluso (ensayo 22-nov).

## B. Qué dejar ABIERTO antes de entrar

- **T1** (raíz del repo): todos los comandos de la demo.
- **T2**: `kubectl get pods -n aegisvolt-test -w` (P16). La ventana del runner (P4) aparte: NO cerrar.
- **T3** port-forward en bucle · **T4** servidor Prefect · **T5** `serve.py`. No se tocan.
- **Chrome de la demo** (perfil `aegis-chrome`): solo el frontend `http://dev.aegisvolt.local:8080`.
- **Chrome normal** (sesión de GitHub), pestañas en este orden:

| Pestaña | URL | Qué mostrar |
| --- | --- | --- |
| README | `https://github.com/ch1fl1n/aegisvolt` | diagrama de arquitectura |
| PR #14 | `https://github.com/ch1fl1n/aegisvolt/pull/14` | pestaña Checks en verde; Conversation -> botón **Merge pull request** |
| Actions | `https://github.com/ch1fl1n/aegisvolt/actions/workflows/deploy.yml` | tras el merge, el run de arriba "Merge pull request #14 from ch1fl1n/dev" -> job `deploy-test` |
| deploy.yml | `https://github.com/ch1fl1n/aegisvolt/blob/dev/.github/workflows/deploy.yml` | `ENV_NAME`, `terraform workspace select`, canary |
| Rulesets | `https://github.com/ch1fl1n/aegisvolt/settings/rules` | `protected-branches`: dev/test/prod, sin bypass, reglas deletion, force push, PR, 6 checks |
| Prefect | `http://127.0.0.1:4200` | runs de `environment-health` y `saga-audit` + artifact |
| Respaldo | `https://github.com/ch1fl1n/aegisvolt/actions/runs/45099540645` | run verde de promoción a test (attempt 2: 46 peticiones al canary, 0 % -> PROMOVIDO) |

## C. Demo (~13 min)

Al empezar, en T1: `$t0 = Get-Date` (para ver el tiempo: `(Get-Date) - $t0`).

Antes de CADA carga: escribir el conector en el campo (se queda con el último valor) y elegir la
cuenta correcta. Esperar el resultado (spinner "Procesando saga…", 5-20 s) sin volver a clicar.

| Min | Bloque | Hacer (dónde) | Decir (una idea) | Resultado esperado |
| --- | --- | --- | --- | --- |
| 0:00 | Arquitectura | Chrome normal: README (diagrama) | Cliente -> API Gateway -> VPC Link -> NLB -> Ingress NGINX -> gateway GraphQL -> 3 microservicios, cada uno con su tabla DynamoDB; Floci emula AWS en local | |
| 1:00 | IaC | T1: `terraform -chdir=infra/envs workspace list` + versiones del tfstate (abajo §6.1) | un estado por workspace (`env:/dev/…`) en S3 versionado, KMS propia y lock | lista dev/test/prod; tabla de versiones |
| 2:00 | SAGA feliz | T1: copiar token (abajo). Chrome demo: pegar token. Estación `st-norte`, conector `c1`, cuenta `acc-demo`, 20 kWh -> **Iniciar carga** | orquestación en el gateway: reservar -> cobrar -> activar; cada paso se guarda en la bitácora (DynamoDB) | `COMPLETED 16.00 · 50 kW`; saldo 484,00; c1 RESERVED |
| 2:40 | Falla en paso 2 | cuenta `acc-pobre` (saldo 1,00), estación `st-centro`, conector `c1` -> Iniciar carga. Luego volver a `acc-demo` | fondos insuficientes: solo se libera el conector (no hubo cobro que reembolsar) | `COMPENSATED`, `INSUFFICIENT_FUNDS`, pasos: reserve ok, charge error 402, ↩ charge ok, ↩ reserve ok |
| 3:00 | Falla en paso 3 | `SIMULATE_CHARGER_HARDWARE_FAULT` ON, esperar 5 s. Estación `st-norte`, conector **`c2`**, `acc-demo` -> Iniciar carga. Luego la flag OFF | se compensa en orden inverso: detener carga -> reembolso -> liberar conector | `COMPENSATED`, `CHARGER_FAULT`, 6 pasos; saldo vuelve a 484,00; c2 AVAILABLE |
| 4:00 | Flags | `ENABLE_FAST_CHARGE_BOOST` ON, esperar 5 s. `st-norte`, `c2`, `acc-demo` -> Iniciar carga. **Dejar BOOST ON** (se usa en 8:00) | flags por ambiente en DynamoDB, caché 5 s, push por WebSocket: cambia el comportamiento sin redesplegar | `COMPLETED 16.00 · 150 kW` (antes 50 kW) |
| 4:30 | Rollback | T1: `uv run python scripts/canary.py --env dev --tag demo1 --chaos 0.5` (~1,5 min; ver "Mientras espera") | versión rota: 5xx de ESA versión > 5 % -> rollback automático, el estable no se toca | `ROLLBACK` (exit 1), ~50 % de error en el canary |
| 6:00 | Merge en vivo | T1: `kubectl -n aegisvolt-dev scale deploy --all --replicas=0`. Chrome: PR #14 -> Checks (8 verdes, promote-guard) -> Conversation -> **Merge pull request** -> Confirm. Luego pestaña Actions: abrir el run nuevo | nada llega a test sin PR y checks; el merge dispara el despliegue solo | run "Merge pull request #14" en curso, job `deploy-test` |
| 6:30 | Cómo elige ambiente | Chrome: deploy.yml (`ENV_NAME: ${{ github.ref_name }}` -> `terraform workspace select`) | rama = ambiente: el pipeline detecta la rama destino del merge | |
| 7:30 | Ruleset | Chrome: Rulesets -> `protected-branches`. Si pide probarlo: T1 push directo/force (abajo §6.2) | ni el dueño escribe directo: PR + 6 checks, sin bypass | `GH013` en los dos push |
| 8:00 | Prod intacto | T1: los 2 `scan` de flags (abajo) | dev tiene BOOST ON; prod no tiene filas = todo apagado: otra tabla, otro workspace, otro token | dev: tabla con BOOST True; prod: vacío |
| 9:00 | Observabilidad | Chrome: Prefect -> runs `environment-health` y `saga-audit` -> artifact. T1: `uv run python scripts/trace_saga.py` | health de los 3 ambientes + auditoría de consistencia; correlation_id en los 4 servicios | traza CHARGER_FAULT con 9/4/4/5 eventos |
| 10:30 | Canary automático | Chrome: Actions -> run -> pasos `terraform apply (workspace test)` -> build -> `Canary del gateway` (20 %) -> PROMOVIDO. T2: pods canary subiendo/bajando | rama -> workspace -> apply -> canary con métricas de CloudWatch, sin humano | run verde (~6,5 min desde el merge) |
| 12:30 | Cierre | | patrones: SAGA orquestada, canary con fail-safe, IaC por workspace, feature flags, observabilidad | |
| +4 | Solo si piden SAGA en test (§6.3) | T1: `.\scripts\saga_test.ps1` (~4,5 min, después del run) | flag de falla en TEST + mutación + compensación en las tablas de test | CHARGE + REFUND en tablas de test |

Por qué cada conector: una carga COMPLETED deja su conector RESERVED (el auto sigue cargando);
en el mismo conector la siguiente carga compensa en el paso 1 (CONFLICT: "el conector no está
disponible"). Por eso: c1 feliz, st-centro c1 para fondos, c2 para la falla, c2 otra vez para
BOOST (la falla lo liberó). El orden 2:40 antes de 3:00 importa: `trace_saga.py` muestra la
ÚLTIMA saga compensada, y debe ser la del cargador (pasa por los 4 servicios).

### Mientras espera (relleno con contenido)

- **Carga en curso (5-20 s):** "cada llamada espera hasta 20 s y reintenta errores de red; es
  seguro porque cada paso es idempotente con el saga_id como llave".
- **Rollback, paso [1/4] (~1 min arrancando el pod):** por qué canary y no blue-green (expone
  solo el 20 %, con tráfico real); por qué la métrica es del SERVIDOR y por versión (dimensión
  `Version`); las 4 reglas (fail-safe, anti-dilución, promoción con red, primer despliegue).
- **Si preguntan por qué llegó ~13 % y no 20 %:** el peso es probabilístico por petición; por
  eso hay un mínimo de 20 peticiones (si no: inconcluso -> rollback).
- **Run del merge (~6,5 min):** terraform apply (1,5 min) -> plan_guard; build (1 min) -> tag =
  sha; canary (3 min). Mientras: deploy.yml, ruleset, prod intacto, Prefect (filas 6:30-9:00).
- **Prefect `saga-audit` en rojo (Failed):** es CORRECTO y es buen ejemplo: encontró hallazgos
  reales de los ensayos: una huérfana (`f0422695`, el gateway se reinició a mitad) y una FAILED
  (`274f2cea`: el reembolso falló porque billing se estaba redesplegando). La auditoría solo lee
  y avisa; corregir dinero automáticamente sin contexto es peligroso, decide una persona.

### Comandos de T1 (copiar tal cual)

```powershell
# Token de admin de dev al portapapeles (no se imprime); pegarlo en el panel de flags
(Get-Content .env | Where-Object { $_ -like "ADMIN_TOKEN=*" }).Split("=", 2)[1].Trim() | Set-Clipboard
# §6.1 versiones del tfstate de dev (restaurar = copy-object con versionId; explicaciones §10)
aws --endpoint-url http://localhost:4566 s3api list-object-versions --bucket aegisvolt-tfstate `
  --prefix env:/dev/ --max-items 5 --query "Versions[].[LastModified,IsLatest,VersionId]" --output table
# Prod intacto: flags de dev vs prod (prod sin filas = todas en su valor por defecto, apagadas)
aws --endpoint-url http://localhost:4566 dynamodb scan --table-name aegisvolt-flags-dev `
  --query "Items[].{flag:flag_name.S,on:enabled.BOOL}" --output table
aws --endpoint-url http://localhost:4566 dynamodb scan --table-name aegisvolt-flags-prod `
  --query "Items[].{flag:flag_name.S,on:enabled.BOOL}" --output table
# §6.4 saga compensada -> correlation_id -> logs de los 4 servicios en CloudWatch
uv run python scripts/trace_saga.py
```

§6.2 push directo y forzado a test, SIN tocar tu carpeta (commit vacío encima de test, en memoria):

```powershell
git fetch origin
$c = git commit-tree 'origin/test^{tree}' -p origin/test -m 'prueba: push directo (debe rechazarse)'
git push origin "$($c):refs/heads/test"
git push --force origin "$($c):refs/heads/test"
```

Probado el 22-nov: los dos responden `GH013` "Changes must be made through a pull request" y
"6 of 6 required status checks are expected"; test queda en el mismo sha. El commit va ENCIMA de
test (avance rápido), por eso `--force` no muestra la regla `non_fast_forward`: lo frena antes la
de PR. Reescribir historia también está bloqueado (Settings > Rules lo muestra); no se prueba en
vivo porque, si fallara, borraría commits de test.

## C2. Canary: qué califica y cómo justificarlo

Lo que califica la rúbrica es el canary AUTOMÁTICO del pipeline (rama -> workspace -> terraform
apply -> canary con 10-20 % del tráfico): se ve con el merge del PR #14 (6:00 y 10:30). El canary
manual (4:30) solo muestra el camino de rollback.

En vivo SOLO se corre la versión rota (`--chaos 0.5`): el rollback deja el estable intacto y se
puede repetir. Si el profe pide ver una promoción sana: tag NUEVO `demo2` (construir ~1,5 min:
`uv run python scripts/deploy.py --env dev --tag demo2 --only graphql-gateway`, y luego
`uv run python scripts/canary.py --env dev --tag demo2`); nunca `demo1` sin chaos (el estable
pasaría a `demo1` y el siguiente intento abortaría por anti-dilución). Necesita dev arriba: hacerlo
antes de 6:00 o volver a subir dev (§H paso 3).

Qué decir mientras corre (lo imprime el script en 4 pasos):

1. **Despliega** la versión nueva en un Deployment aparte (1 réplica); el estable no se toca.
2. **20 % del tráfico** con la anotación `canary-weight` del Ingress NGINX (por petición).
3. **Tráfico real** por el Ingress; cada respuesta trae `x-service-version`.
4. **Decide con datos del servidor** (CloudWatch en Floci): tasa de 5xx SOLO de la versión
   canary. Plan A métricas; plan B logs (Floci no da datapoints de metric filters). Umbral 5 %.

Por qué es seguro (modelo Argo Rollouts Successful/Failed/Inconclusive):

- **Fail-safe:** si no se puede medir o hay pocas peticiones -> rollback (en CI no hay humano).
- **Anti-dilución:** estable y canary con el mismo tag mezclarían su métrica -> se aborta antes.
- **Promoción con red:** si el rollout del estable no termina, `rollout undo` + peso 0.
- **Primer despliegue:** sin versión anterior no hay contra qué medir -> entra como estable.

## D. Teoría y preguntas

`explicaciones-demo.md`: mismo orden que §C; §9 preguntas difíciles (incluye "¿serviría en una
empresa real?"), §10 banco de la guía (§6), §11 código real para mostrar, §12 preguntas de código.

## F. Si algo falla en vivo (plan B por síntoma)

Regla: no arreglar en vivo. Decir qué pasó, por qué es seguro y mostrar la evidencia. Todo lo de
esta tabla pasó de verdad en los ensayos del 21 y 22-nov.

| Síntoma | Qué hacer | Qué decir |
| --- | --- | --- |
| Frontend no carga (ERR_CONNECTION_REFUSED) | mirar T3: el bucle reconecta solo en ~2 s; Ctrl+F5. Si T3 no tiene el bucle, pegarlo (§A P8) | el pod del Ingress se reinició (RAM) y el port-forward muere con él |
| Frontend recargado: flags deshabilitados | volver a pegar el token (T1: comando del token) | sin token el panel es solo lectura (FORBIDDEN) |
| "Iniciar carga" tarda | esperar el spinner (hasta ~20 s por paso); NO volver a clicar | en local Floci va lento por la RAM; el gateway espera y reintenta, seguro por idempotencia |
| Sale CONFLICT "el conector no está disponible" | usar otro conector libre (st-centro c2/c3, st-sur c1) | ese conector ya tiene una carga activa: la saga compensó en el paso 1, correcto |
| Sale COMPENSATED con `ReadTimeout` | repetir en OTRO conector libre | no pudo confirmar un paso a tiempo y compensó todo: el patrón funcionando |
| Sale FAILED | no repetir; mostrar los pasos: una compensación dio error | pasó en el ensayo cuando billing se redesplegaba: la saga NO se marca como bien; queda para revisión y la auditoría de Prefect la detecta |
| Una flag no cambia | token pegado; esperar 5 s | caché de 5 s por réplica |
| El 150 kW no aparece con BOOST | esperar 5 s más tras activar y repetir en otro conector libre | la saga congela las flags al iniciar: una carga ya iniciada no cambia |
| `trace_saga.py` muestra fondos insuficientes o una saga vieja | `uv run python scripts/trace_saga.py --saga <id>` con los 8 caracteres que muestra el frontend junto a COMPENSATED (p. ej. `--saga ba01f9b2`), o mostrar la que sale | toma la última compensada; el correlation_id une los servicios igual |
| `canary.py` dice "ABORTADO: el estable ya es demo1" | usar `demo2` (§C2) | anti-dilución |
| `canary.py` da ROLLBACK inconcluso | mostrar la salida | fail-safe: sin datos suficientes no se promueve |
| El merge no arranca el run | ¿ventana del runner abierta y "Listening for Jobs"? Si no: correr `start-aegisvolt-runner.cmd`; el run espera en cola y arranca solo | el job corre en el runner self-hosted (llega a Floci y minikube) |
| El run del merge falla o sale inconcluso | mostrar el log del paso Canary y el run de respaldo 45099540645 (§B) | fail-safe: revirtió, test nunca queda roto; el ensayo con dev en 0 promovió (46 peticiones, 0 %) |
| El run tarda más de 7 min | seguir con 6:30-9:00 y volver al final | terraform 1,5 + build 1 + canary 3 min |
| PR #14 no está `CLEAN` en la preparación | abrir PR -> Checks -> "Re-run failed jobs"; si no alcanza: mergear igual NO se puede (ruleset): mostrar el run de respaldo y el PR #13 mergeado con checks verdes | el ruleset exige los 6 checks: es la gobernanza funcionando |
| Prefect UI no abre | T4: repetir P10. Alternativa sin UI: T5 `& $py observability/prefect/saga_audit_flow.py --env dev` | Prefect corre local y solo lee Floci |
| Pods reiniciando (`kubectl get pods -A`) | esperar a que estén Running antes de iniciar cargas | una carga durante un reinicio puede quedar FAILED (pasó en el ensayo) |
| Piden la SAGA en TEST (§6.3) | T1: `.\scripts\saga_test.ps1` (~4,5 min, después del run) | test vive en modo liviano (aprobado); el script sube los micros y muestra CHARGE+REFUND |
| Piden ver código | `explicaciones-demo.md` §11 (rutas) -> abrir en GitHub | |

## G. Check final

### Antes de apagar (22-nov, ya hecho)

```powershell
gh pr view 14 --json state,mergeStateStatus        # OPEN, CLEAN
minikube -p aegisvolt image ls | Select-String demo1
minikube stop -p aegisvolt
docker compose stop
```

Cerrar T1-T5, el runner y Docker Desktop.

### Mañana, antes de entrar (marcar)

- [ ] §A completa y sin pasos en "Si no".
- [ ] Runner: "Listening for Jobs".
- [ ] `kubectl get pods -A | Select-String -NotMatch "Running|Completed"`: solo el encabezado.
- [ ] Prueba de humo c1 COMPLETED y después `reset_demo.py` OK.
- [ ] PR #14 `OPEN` y `CLEAN`.
- [ ] Chrome demo: Ctrl+F5, token pegado, flags OFF, saldo 500,00, c1/c2 AVAILABLE.
- [ ] Prefect `http://127.0.0.1:4200` con runs.
- [ ] App de Claude CERRADA; RAM libre > 500 MB.
- [ ] `$t0 = Get-Date` en T1 al empezar.

## H. Después de la demo (o si un ensayo gasta el PR #14)

Cada demo consume UN PR dev->test. Para volver a dejarlo listo:

1. `uv run python scripts/reset_demo.py` (conectores libres, saldo 500, flags OFF).
2. No promover `demo1` ni `demo2` (si se promovió `demo2`, construir `demo3` para la próxima).
3. Subir dev (quedó en 0 por el merge): `uv run python scripts/deploy.py --env dev --skip-build`.
4. Commit nuevo en dev y PR dev->test nuevo (todo en T1; test y prod en 0 para dar RAM):

```powershell
git switch dev; git pull
git switch -c docs/ensayo-AAAAMMDD
git add -A; git commit -m "docs: ajustes del ensayo"; git push -u origin HEAD
gh pr create --base dev --title "docs: ajustes del ensayo" --body "Ajustes del ensayo."
Start-Sleep 20; gh pr checks --watch
kubectl -n aegisvolt-test scale deploy --all --replicas=0
kubectl -n aegisvolt-prod scale deploy --all --replicas=0
gh pr merge --merge
Start-Sleep 20
$run = gh run list --branch dev --workflow deploy.yml --limit 1 --json databaseId -q ".[0].databaseId"
gh run watch $run
gh pr create --base test --head dev --title "release: promover dev a test" --body "Demo en vivo."
$pr = gh pr list --base test --head dev --json number -q ".[0].number"
Start-Sleep 20; gh pr checks $pr --watch
```

No iniciar cargas mientras corre el deploy de dev (los pods se reemplazan: la saga puede quedar
FAILED). Si el deploy sale inconcluso por RAM: `gh run rerun $run --failed`.
