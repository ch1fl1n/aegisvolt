# Guion de la sustentación (demo virtual en vivo, 10 min)

Complementa `runbook-demo.md` (comandos detallados y tabla "Si algo falla en vivo").
Regla de oro: en vivo no se construye nada pesado a mano. Lo único que corre solo en vivo es el
pipeline (merge de un PR dev->test ya en verde), y corre en test, sin tocar la SAGA de dev.

## A0. La víspera (deja el PR de promoción listo)

| Paso | Comando / acción | Listo cuando |
| --- | --- | --- |
| Commit nuevo en dev | PR `docs/...` -> dev con los últimos cambios de docs; merge | deploy de dev por merge en verde (~7 min) |
| PR de promoción | PR dev -> test, SIN mergear | 8/8 checks verdes y `CLEAN` (~5 min) |

El PR queda abierto toda la noche: sus checks no caducan. Mañana solo se revisa que siga `CLEAN`.

## A. Preparación (orden: lo más lento primero; total ~20 min + ensayo)

| T | Paso | Comando / acción | Tiempo medido | Mientras espera |
| --- | --- | --- | --- | --- |
| -60 | Cerrar lo pesado | Chrome, otras ventanas de Claude, juegos | | |
| -59 | Docker | abrir Docker Desktop | ~2 min | abrir 3 terminales en el repo |
| -57 | Floci | `docker compose up -d`; `docker network disconnect aegisvolt floci`; `docker compose restart floci` | ~30 s | |
| -56 | Clúster | `minikube start -p aegisvolt`; `docker update --cpus 4 aegisvolt` | ~3 min | doble clic al runner |
| -53 | Anti-tormenta | escalar dev/test/prod a 0 (runbook §0) | ~40 s | |
| -52 | dev completo | `uv run python scripts/deploy.py --env dev --skip-build` | ~3 min | abrir el editor |
| -49 | test (destino del merge en vivo) | `uv run python scripts/deploy.py --env test --skip-build --only graphql-gateway` | ~1,5 min | |
| -47 | prod mínimo (flags) | `uv run python scripts/deploy.py --env prod --skip-build --only graphql-gateway` | ~1,5 min | |
| -45 | Imágenes de canary manual | `uv run python scripts/deploy.py --env dev --tag demo1 --only graphql-gateway` (y `demo2` igual) | ~1,5 min c/u | |
| -42 | Prefect | runbook §5: server + `serve.py` | ~2 min | abrir Chrome con las pestañas |
| -40 | Verificar | runner Idle; PR dev->test `CLEAN`; `kubectl get pods -A` sin reinicios | | |
| -35 | Ensayo rápido | §C de punta a punta SIN mergear el PR | ~10 min | |
| -15 | Calma | nada pesado; RAM libre > 500 MB | | |

Los pasos de deploy van en serie: comparten un nodo de 2 GB (tormenta de reinicios si se solapan).

## B. Qué dejar ABIERTO antes de entrar

1. Terminal 1 (PowerShell, raíz del repo): comandos de la demo.
2. Terminal 2: `kubectl get pods -n aegisvolt-test -w` (se ve el canary del pipeline subir y bajar).
3. Terminal 3: runner corriendo (no cerrar).
4. Navegador, pestañas en este orden:
   - PR dev -> test en verde (se mergea en vivo); Actions (para abrir el run de deploy);
   - frontend dev; Settings > Rules (ruleset); Prefect UI.
5. Editor con `.github/workflows/deploy.yml`, `scripts/canary.py` e `infra/envs`.

## C. Demo (10 min)

| Min | Bloque | Hacer | Decir (una idea) |
| --- | --- | --- | --- |
| 0:00 | CI/CD arranca | mostrar el PR dev->test: 8 checks verdes, promote-guard, ruleset; **merge** | nada llega a test sin PR y checks; el merge dispara el despliegue (corre solo ~5 min) |
| 1:00 | Arquitectura | diagrama/README | API Gateway -> VPC Link -> NLB -> Ingress -> gateway GraphQL -> 3 micros; Floci emula AWS |
| 2:00 | IaC | `terraform -chdir=infra/envs workspace list` | un estado por workspace en S3 versionado y cifrado con KMS propia, con lock |
| 3:00 | SAGA | frontend dev: feliz -> COMPLETED; flag de falla -> COMPENSATED | orquestación en el gateway; compensaciones en orden inverso |
| 5:00 | Flags | misma flag en prod sigue apagada | flags por ambiente en DynamoDB, caché 5 s, push por WSS |
| 6:00 | **Canary automático** | Actions: run del merge -> `terraform apply (test)` -> deploy -> canary 20 % -> PROMOVIDO; terminal 2 | rama -> workspace -> apply -> canary, sin humano (rúbrica) |
| 8:00 | Rollback | `uv run python scripts/canary.py --env dev --tag demo1 --chaos 0.5` | versión rota: 5xx > 5 % -> rollback automático, estable intacto |
| 9:30 | Observabilidad | Prefect: health y auditoría de sagas | detecta lo que el SAGA solo no puede evitar |
| 10:00 | Cierre | | |

Si a los 6:00 el run aún no termina: mostrar el log en vivo (paso en curso) y volver a él al
final; si falló, abrir un run anterior en verde (dev/test de la víspera) y explicar la causa.

## C2. Canary en vivo: que funcione y cómo justificarlo

Lo que califica la rúbrica es el canary AUTOMÁTICO del pipeline ("despliegue tras el merge: rama
-> workspace -> terraform apply -> canary", con 10-20 % del tráfico). Se ve en vivo con el merge
del PR dev->test (min 0:00 y 6:00). El canary manual solo muestra el camino de rollback.

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

## D. Preguntas difíciles probables (respuesta corta)

- **¿Por qué orquestación y no coreografía?** Un solo lugar con el estado de la saga
  (bitácora), compensaciones explícitas y trazables; con 3 servicios la coreografía dispersa
  la lógica y dificulta auditar.
- **¿Qué pasa si el gateway muere a mitad de una saga?** Queda en STARTED en la bitácora; la
  auditoría de Prefect la marca como huérfana. Siguiente paso natural: reanudar o compensar
  automáticamente las que pasen un umbral.
- **¿Idempotencia?** Cada paso usa el `sagaId` como clave: repetir no cobra dos veces.
- **¿Cómo evitan que un plan de dev destruya prod?** Workspaces separados y `plan_guard.py`
  (R7): bloquea cualquier `delete` de un recurso cuyo nombre no termine en `-<workspace>`.
- **¿Por qué el health check del NLB es HTTP?** Comprueba que el ingress responde, no solo que
  el puerto abre (doc de AWS NLB health checks).
- **¿Por qué KMS propia en el bucket del estado?** El tfstate puede tener datos sensibles:
  control de acceso y auditoría de quién descifra; bucket key reduce llamadas a KMS.
- **Si el canary no recibe suficiente tráfico?** Inconcluso => rollback igual (fail-safe, como
  Argo Rollouts "Inconclusive"); en CI no hay humano para decidir.
- **¿Y el primer despliegue de un ambiente?** No hay versión anterior contra la cual medir: entra
  directo como estable y el canary se omite con aviso (como Argo Rollouts con la primera
  revisión). Se detecta con `--ignore-not-found`: una API caída falla el job, no salta el canary.
- **¿Por qué la versión va dentro de la imagen?** Imágenes inmutables: el tag identifica el
  contenido; la métrica se filtra por versión. Y el ARG va al final para no romper la caché.
- **¿Por qué los checks omitidos no cuentan?** Un job saltado reporta "skipped" y GitHub lo
  toma como aprobado: por eso en forks `terraform-plan` corre y falla a propósito (R1).
- **¿Cómo se protege el runner self-hosted de un fork?** T3: aprobación obligatoria para todo
  contribuidor externo, y los jobs de fork van a ubuntu-latest, nunca al runner.
- **¿Secretos?** `.env` fuera del repo; en CI secretos de environment, uno por ambiente;
  gitleaks en cada PR; se rotó el token tras imprimirse una vez.
- **¿Por qué FilterLogEvents?** Floci no genera datapoints de metric filters (R5): plan A
  métricas, plan B logs, misma condición de decisión.
