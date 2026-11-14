# Plan: carpeta `aegisvolt-plan/` — guía de construcción manual de AegisVolt

## Contexto

Proyecto final individual de Patrones Arquitectónicos Avanzados (14 días, sustentación oral con
preguntas Correcto/Incorrecto por capa). Pediste un **plan escrito**, no el proyecto construido:
teoría previa, decisiones, **un bloque de código por cada archivo en el orden en que se crean**
(los tecleas tú en el IDE), una sección de QA y un roadmap paso a paso para la sustentación.

Corrección de rumbo: yo había empezado a montar y probar una implementación de referencia. Eso se
detiene. **No construyo ni ejecuto el proyecto.** Lo único que escribo son los documentos del plan.

Decisiones ya tomadas contigo: **Floci local** (costo cero) y **backend en Python**.

Hechos comprobados en tu equipo (lo único que alcancé a ejecutar):
- Python 3.12.5, Node 24, Terraform 1.16.6, Docker 29.0.1, kubectl 1.35, Helm 3.14, minikube, AWS CLI v2, gh.
- **5,8 GB de RAM** y la VM de Docker con 2,9 GB → condiciona toda la arquitectura local.
- Floci 2.4.0 arranca en ~1 s, usa ~23 MB en reposo, imagen de 377 MB, salud en `/_floci/health`.
  Sin el socket de Docker montado, EKS/EC2 conservan el plano de control pero no levantan contenedores.
- Quedó encendido Docker Desktop y un contenedor de prueba. Para borrarlo: `docker rm -f floci-probe`.

## Qué entrego

Una carpeta `aegisvolt-plan/` con documentos Markdown numerados. Solo documentación; el repositorio
`aegisvolt/` lo creas tú siguiendo los bloques.

| Archivo | Contenido |
|---|---|
| `00-LEEME.md` | Índice, cómo usar el plan, prerrequisitos, ajuste de RAM (`.wslconfig`), calendario de 14 días, árbol final del repo |
| `01-investigacion-buenas-practicas.md` | Resultado de la investigación con fuentes: programación, seguridad, y cada tecnología del proyecto |
| `02-teoria-y-decisiones.md` | Teoría por capa + registro de decisiones (ADR): opción elegida, alternativas descartadas y por qué |
| `03-fase-0-repositorio-y-entorno.md` | Estructura del repo, Floci en Docker Compose, tooling de calidad |
| `04-fase-1-terraform.md` | Bootstrap del estado en S3, workspaces, módulos de red, VPCE, DynamoDB, EKS, API Gateway, logs |
| `05-fase-2-microservicios.md` | Librería común + los tres microservicios |
| `06-fase-3-graphql-saga-flags.md` | Capa GraphQL, orquestador SAGA, feature flags |
| `07-fase-4-docker.md` | Dockerfiles y stack local completo |
| `08-fase-5-kubernetes-canary.md` | Manifiestos por ambiente y script de canary |
| `09-fase-6-cicd-git.md` | Workflows de GitHub Actions, rulesets, flujo de promoción |
| `10-fase-7-observabilidad.md` | Logs en CloudWatch y flujos de Prefect |
| `11-fase-8-frontend.md` | UI React con los cuatro paneles |
| `12-qa.md` | Pruebas unitarias, integración y e2e (código incluido), matriz de pruebas manuales, checklist por rúbrica |
| `13-roadmap-sustentacion.md` | Guion de demo paso a paso, respuesta a cada pregunta del banco, planes B |

Cada documento de fase tiene siempre la misma forma:
1. **Teoría previa** — lo mínimo que debes poder explicar en voz alta de esa capa.
2. **Decisiones** — qué se eligió y qué pregunta del profesor responde.
3. **Archivos, en orden** — ruta exacta + un bloque de código completo por archivo + 2–4 líneas de qué hace y por qué.
4. **Punto de control** — comandos que ejecutas tú y la salida esperada antes de pasar a la siguiente fase.
5. **Errores típicos** de esa fase y cómo reconocerlos.

## Decisiones de arquitectura que el plan va a desarrollar

| Tema | Decisión | Motivo principal |
|---|---|---|
| Nube | Floci 2.4 en Docker Compose con almacenamiento persistente; Terraform válido para AWS real cambiando solo un `.tfvars` | Costo cero; la guía lo permite |
| Estado Terraform | Raíz `bootstrap/` crea el bucket S3 **versionado**; raíz `envs/` usa backend S3 con workspaces `dev`/`test`/`prod` (`env:/<ws>/...`) y bloqueo | 30 % de la rúbrica; preguntas 6.1 |
| Nombres | Todo recurso lleva `${terraform.workspace}`; validación que prohíbe el workspace `default` | Evita pisar `prod` desde `test` |
| Red | VPC por ambiente, subredes públicas y privadas en 2 zonas, tablas de ruta separadas; VPCE Gateway (S3, DynamoDB) e Interface (`execute-api`, `logs`, `monitoring`); VPC Link + NLB interno entre API Gateway y el clúster | Pregunta del recorrido del paquete |
| Kubernetes | Recurso EKS por workspace en Floci (modo mock) + **un solo minikube con un namespace por ambiente** | 5,8 GB de RAM no soportan tres clústeres; se documenta como limitación honesta y cómo sería en AWS |
| Servicios | 4 desplegables: `graphql-gateway`, `station-reservation-service`, `billing-wallet-service`, `energy-dispatch-service`; FastAPI + Strawberry + boto3 | Coincide con el diagrama de la guía |
| Datos | Database-per-Service: tablas `reservations`, `billing`, `dispatch`, más `sagas` (orquestador) y `flags`, todas por ambiente | Requisito 2.4 |
| SAGA | **Orquestación** síncrona por HTTP dentro de la capa GraphQL; bitácora de saga en DynamoDB; compensaciones en orden inverso | Más fácil de demostrar y de auditar que coreografía |
| Idempotencia | `saga_id` como llave de idempotencia + escrituras condicionales y `TransactWriteItems`; repetir un cobro o un reembolso devuelve el resultado guardado | Pregunta 6.3 |
| Feature flags | Implementación propia en DynamoDB, una tabla por ambiente; Terraform siembra valores con `ignore_changes`; caché de 5 s; mutación protegida con token | Cambiar flag sin redesplegar (6.4) |
| Canary | Nativo de Kubernetes guiado por el pipeline: Deployments `stable` y `canary` bajo el mismo Service en proporción 4:1 (20 %); script Python evalúa readiness y tasa de error en CloudWatch (≤ 5 %, mínimo de muestras) y promueve o revierte | Explicable línea a línea; Argo Rollouts queda documentado como evolución |
| CI/CD | GitHub Actions. PR: lint-build, unit, integration, e2e (runners de GitHub con Floci efímero) y `terraform plan` del workspace destino. Merge: rama → workspace → `terraform apply` → canary, en un runner self-hosted en tu equipo | 25 % de la rúbrica; preguntas 6.2 |
| Gobernanza Git | Ramas `dev`, `test`, `prod`; rulesets que bloquean force push, borrado y push directo, y exigen los checks; promoción lineal con merge commit | Preguntas 6.2 |
| Observabilidad | Logs JSON con `correlation_id`, `saga_id`, ambiente, servicio y versión hacia `/aegisvolt/<env>/<servicio>`; Prefect 3 con flujo de salud y flujo de auditoría de sagas (huérfanas, compensadas, inconsistencias entre tablas) | 12 % de la rúbrica |
| Frontend | React + Vite + TypeScript, cliente GraphQL con `fetch` y sondeo cada 2–3 s; configuración por ambiente inyectada en tiempo de ejecución (una sola imagen para los tres ambientes) | 8 % de la rúbrica |
| Seguridad | Contenedores sin root y sistema de archivos de solo lectura, Pod Security `restricted`, NetworkPolicy deny-by-default, límites de profundidad en GraphQL, introspección apagada en prod, secretos fuera del repo, acciones fijadas por SHA, permisos mínimos del token, escaneo con Trivy/Checkov/gitleaks | Pediste buenas prácticas de seguridad |

## Orden de creación de archivos (≈110 archivos)

- **Fase 0** — `.gitignore`, `.editorconfig`, `README.md`, `compose.yaml` (Floci), `pyproject.toml` (ruff, pytest), `.pre-commit-config.yaml`, `scripts/dev.ps1`.
- **Fase 1** — `infra/bootstrap/*.tf`; `infra/envs/{versions,backend,providers,variables,locals,main,outputs}.tf`; `infra/envs/floci.tfvars`, `aws.tfvars`; módulos `network`, `vpc_endpoints`, `dynamodb`, `observability`, `eks`, `api_gateway`, `k8s_namespace` (cada uno `main.tf`, `variables.tf`, `outputs.tf`).
- **Fase 2** — `libs/aegis_common/` (config, logging, correlación, cliente DynamoDB, errores); por cada servicio: `app/{main,config,models,repository,service,routes}.py` y `requirements.txt`.
- **Fase 3** — `services/graphql-gateway/app/`: `schema.py`, `resolvers.py`, `clients.py`, `saga/{orchestrator,steps,repository,models}.py`, `flags.py`, `security.py`, `schema.graphql` exportado.
- **Fase 4** — un `Dockerfile` por servicio, `.dockerignore`, `compose.apps.yaml`, `scripts/seed.py`.
- **Fase 5** — `k8s/base/` (Deployments stable/canary, Services, ConfigMap, NetworkPolicy, ResourceQuota), `k8s/overlays/{dev,test,prod}/kustomization.yaml`, `scripts/canary.py`, `scripts/deploy.py`.
- **Fase 6** — `.github/workflows/{pr-checks,deploy,promote-guard}.yml`, `.github/rulesets/protected-branches.json`, `.github/pull_request_template.md`, `CODEOWNERS`, `scripts/setup_rulesets.ps1`.
- **Fase 7** — `observability/prefect/{health_flow,saga_audit_flow,serve}.py`, `requirements.txt`, consultas de CloudWatch.
- **Fase 8** — `frontend/` (Vite): `src/api/graphql.ts`, `src/hooks/usePolling.ts`, cuatro paneles, `public/config.js`, `Dockerfile`, `nginx.conf`.
- **QA** — `tests/unit/`, `tests/integration/`, `tests/e2e/` con sus `conftest.py`.

## Límites y honestidad del plan

- El código de los bloques **no habrá sido ejecutado por mí**. Por eso cada fase termina en un punto
  de control: si algo falla, lo detectas en esa fase y no al final.
- Marcaré con una etiqueta visible los tramos que dependen de comportamiento de Floci que no está
  documentado con claridad (bloqueo nativo del estado en S3, integración API Gateway → VPC Link → NLB,
  EKS en modo mock con el proveedor de Terraform) y daré en cada uno la alternativa segura.
- Con 5,8 GB vas justo. El plan incluye el ajuste de memoria y, como salida de emergencia, cómo correr
  el mismo stack en GitHub Codespaces.
- Si después quieres, puedo hacer una pasada de verificación de una fase concreta; solo si lo pides.

## Verificación (la haces tú, guiada por el plan)

- Puntos de control al final de cada fase con comando y salida esperada.
- `12-qa.md`: `pytest` unitario (lógica de saga, compensaciones e idempotencia), integración contra
  DynamoDB en Floci, e2e por GraphQL (camino feliz, fondos insuficientes, fallo de cargador), y matriz
  de pruebas manuales por ambiente.
- `13-roadmap-sustentacion.md`: ensayo completo de la demo, pregunta por pregunta del banco 6.1–6.4,
  con el comando exacto, lo que debe verse y qué hacer si falla en vivo.

## Ejecución tras aprobar

1. Crear `aegisvolt-plan/` en la carpeta de esta sesión (luego puedes moverla a la que elijas).
2. Escribir `00`, `01` y `02` (índice, investigación, teoría y decisiones).
3. Escribir las fases `03`–`11` en orden, con todos los bloques de código.
4. Escribir `12-qa.md` y `13-roadmap-sustentacion.md`.
5. Borrar el contenedor de prueba `floci-probe`. No ejecutar nada más.
