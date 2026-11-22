# Guion de la sustentación (demo virtual en vivo, 10 min)

Complementa `runbook-demo.md` (comandos detallados y tabla "Si algo falla en vivo").
Regla de oro: en vivo NO se construyen imágenes ni se aplica Terraform desde cero; eso se
hace en la preparación. En vivo solo se ejecuta lo que tarda segundos.

## A. Preparación (T-80 min, ~40 min reales)

| T | Paso | Comando / acción | Listo cuando |
| --- | --- | --- | --- |
| -80 | Cerrar todo lo pesado | navegador extra, juegos, IDEs; `wsl -t Ubuntu` | |
| -78 | Docker + Floci | abrir Docker Desktop (~2 min); `docker compose up -d`; `docker network disconnect aegisvolt floci`; `docker compose restart floci` (al soltar la red se rompe su puerto; 8 s) | `curl.exe -s http://127.0.0.1:4566/_floci/health` = 200 |
| -75 | Clúster | `minikube start -p aegisvolt`; `docker update --cpus 4 aegisvolt` | ~3 min |
| -71 | Evitar bucle de reinicios | escalar dev/test/prod a 0 (runbook §0) | `kubectl get pods -A` sin pods de la app |
| -70 | dev completo | `uv run python scripts/deploy.py --env dev --skip-build` | 5/5 Running, 0 reinicios |
| -60 | prod mínimo (flags) | `uv run python scripts/deploy.py --env prod --skip-build --only graphql-gateway` | 1/1 Running |
| -55 | Imagen del canary | `uv run python scripts/deploy.py --env dev --tag demo1 --only graphql-gateway` | build ~15 s; gateway estable intacto |
| -50 | Runner | `C:\Users\chifl\actions-runner\start-aegisvolt-runner.cmd` | GitHub > Settings > Runners: Idle |
| -48 | Prefect | runbook §5: server + `serve.py` | UI en http://127.0.0.1:4200 |
| -45 | Ensayo rápido | correr §B de punta a punta una vez | todo verde |
| -15 | Calma | no lanzar nada pesado; revisar RAM libre | |

## B. Qué dejar ABIERTO antes de entrar

1. Terminal 1 (PowerShell, raíz del repo): para los comandos de la demo.
2. Terminal 2: `kubectl get pods -n aegisvolt-dev -w` (se ve el canary subir y bajar).
3. Terminal 3: runner corriendo (no cerrar).
4. Navegador, pestañas en este orden:
   - frontend dev; GitHub PR con los 7 checks; Actions (run de deploy por merge);
   - Settings > Rules (ruleset); Prefect UI (flujos y artifact de auditoría).
5. Editor con `infra/envs`, `scripts/canary.py` y `.github/workflows/` para enseñar código.

## C. Demo (10 min)

| Min | Bloque | Hacer | Decir (una idea) |
| --- | --- | --- | --- |
| 0:00 | Arquitectura | diagrama/README | API Gateway -> VPC Link -> NLB -> Ingress -> gateway GraphQL -> 3 micros; Floci emula AWS |
| 1:00 | IaC | `terraform -chdir=infra/envs workspace list`; tablas por ambiente | un estado por workspace en S3 versionado y cifrado con KMS propia, con lock |
| 2:00 | SAGA | frontend: carga feliz -> COMPLETED; activar flag de falla en dev -> COMPENSATED | orquestación en el gateway; compensaciones en orden inverso; bitácora en DynamoDB |
| 4:00 | Flags | misma flag en prod sigue apagada | flags por ambiente en DynamoDB, caché 5 s, push por WSS |
| 5:00 | Canary | `uv run python scripts/canary.py --env dev --tag demo1 --chaos 0.5` | 20 % al canary; mide 5xx en CloudWatch; >5 % => rollback automático |
| 7:00 | CI/CD | PR con 7 checks; ruleset; promote-guard; run de deploy disparado por merge | nada llega a dev/test/prod sin PR y checks; promoción lineal dev->test->prod |
| 9:00 | Observabilidad | Prefect: health Completed y auditoría con sagas huérfanas | detecta lo que el SAGA solo no puede evitar |
| 10:00 | Cierre | | |

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
