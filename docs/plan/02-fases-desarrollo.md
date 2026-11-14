# AegisVolt — Fases de desarrollo propuestas

Plan de construcción por bloques del proyecto final de *Patrones Arquitectónicos Avanzados*.
Cada bloque produce documentos de la carpeta `aegisvolt-plan/` y termina con un **punto de control**
que se ejecuta antes de avanzar. Si el punto de control falla, no se pasa al siguiente bloque.

## Decisiones base

| Tema | Decisión |
| --- | --- |
| Equipo de desarrollo | Linux (CachyOS, Arch), shell zsh/fish; todos los scripts en **Bash (`.sh`)** |
| Nube | Floci 2.4 (`floci/floci:latest`, puerto 4566) en Docker Compose; Terraform portable a AWS real cambiando solo el `.tfvars` |
| Backend | Python **3.12** dentro de los contenedores (imagen `python:3.12-slim`): FastAPI + Strawberry (GraphQL) + boto3 |
| Python en el host | Entorno virtual con Python 3.12 mediante `uv` (el sistema trae 3.14, que Prefect y algunas librerías aún no soportan bien) |
| Frontend | React + Vite + TypeScript |
| Kubernetes | EKS por workspace en Floci (plano de control) + un solo minikube con un namespace por ambiente y el addon `ingress` |
| SAGA | Orquestación síncrona en la capa GraphQL, con bitácora en DynamoDB |
| Feature flags | Propias en DynamoDB, una tabla por ambiente, caché de 5 s |
| Canary | Peso de tráfico exacto con Ingress canary (`canary-weight: 20` → `100`), promovido o revertido por un script del pipeline |
| Tiempo real | Suscripciones GraphQL sobre **WSS** (`graphql-transport-ws`), con sondeo como respaldo |
| CI/CD | GitHub Actions, con runners de GitHub y un runner self-hosted |
| Repositorio | Público, con rulesets en `dev`, `test` y `prod` |

---

## Ajustes al plan original

### Entorno

#### E1. Scripts en Bash y sin `.wslconfig`

El equipo es Linux nativo, así que el ajuste de memoria de WSL no aplica. Los scripts de PowerShell
pasan a Bash con `set -euo pipefail` y se validan con `shellcheck`:

| Original | Nuevo |
| --- | --- |
| `dev.ps1` | `scripts/dev.sh` |
| `setup_rulesets.ps1` | `scripts/setup_rulesets.sh` |

#### E2. La Fase 0 instala las herramientas que faltan y arregla Docker

En este equipo no hay kubectl, minikube ni Helm, la AWS CLI es v1 y el `credsStore` de Docker
(pass/gpg) está roto, así que `docker pull` falla. Para resolverlo, la Fase 0 incluye:

```bash
sudo pacman -S --needed kubectl minikube helm shellcheck uv
sudo pacman -S aws-cli-v2      # reemplaza a aws-cli v1 (pacman pide confirmar el conflicto)
```

Para reparar Docker hay dos opciones:

- **Opción A (simple):** quitar la línea `"credsStore": "pass"` de `~/.docker/config.json`.
- **Opción B:** inicializar el almacén con `pass init <id-gpg>`.

**Punto de control:** `docker pull hello-world`, `kubectl version --client`, `minikube version`,
`helm version` y `aws --version` (debe mostrar `aws-cli/2.x`) responden sin error.

#### E3. Python 3.12 en contenedores y en el host

- **Contenedores:** todos los Dockerfiles parten de `python:3.12-slim`.
- **Host:** las pruebas y Prefect corren en un entorno creado con
  `uv venv --python 3.12 && source .venv/bin/activate` (o `activate.fish`).
- **Versión fijada:** `pyproject.toml` declara `requires-python = ">=3.12,<3.13"` para que nadie use 3.14
  por error.

### Decisiones técnicas alineadas con la rúbrica

#### T1. `terraform plan` en el runner self-hosted

**Rúbrica:** *"terraform plan en MR"* y *"validando el plan antes de autorizar el merge"*. Un plan contra un
Floci vacío no valida nada, porque siempre muestra "crear todo".

**Decisión:**

- El job `terraform-plan` corre en el runner self-hosted y lee el tfstate real del workspace destino
  (`env:/<ws>/terraform.tfstate`).
- El plan se publica como comentario del PR y como artifact.
- El job falla si el plan intenta destruir recursos con el prefijo de otro ambiente.
- Los demás checks corren en runners de GitHub con Floci efímero.

#### T2. Repositorio público

**Rúbrica:** *"reglas de protección de ramas (bloqueo de force push y push directo)"*, que se demuestran
en vivo (pregunta 6.2). En una cuenta gratuita, esas reglas solo se aplican en repos públicos.

**Decisión:** repo **público**, con rulesets que bloquean el force push, el borrado y el push directo,
y que exigen PR y checks.

#### T3. Runner self-hosted protegido frente a forks

**Motivo:** un repo público con runner self-hosted permite que un fork ejecute código en tu equipo.

**Decisión:**

- **Settings → Actions → General:** "Require approval for all outside collaborators".
- **Jobs self-hosted** solo con `if: github.event.pull_request.head.repo.full_name == github.repository`
  o en `push` a ramas protegidas.
- **Disparador:** nunca `pull_request_target`.
- **Permisos y aislamiento:** `permissions:` mínimos; el runner corre con un usuario sin privilegios,
  con la etiqueta `self-hosted, aegisvolt` y sin credenciales de AWS real.

#### T4. Canary con peso de tráfico exacto (Ingress canary)

**Rúbrica:** *"10 % - 20 % del tráfico hacia la nueva versión"*. Una proporción de pods 4:1 solo aproxima
el tráfico, así que se descarta como mecanismo principal.

**Decisión:** el addon `ingress` de minikube (ingress-nginx) con dos Ingress sobre el mismo host. Así se
ve exactamente qué porcentaje se mueve y quién decide:

| Ingress | Apunta a | Configuración |
| --- | --- | --- |
| Estable | Service `stable` | Sin anotaciones de canary |
| Canary | Service `canary` | `nginx.ingress.kubernetes.io/canary: "true"` y `canary-weight: "20"` |

**Lógica de `scripts/canary.py`:**

1. Aplica el peso de 20 %.
2. Espera una ventana de observación.
3. Evalúa la condición de promoción (la que pregunta el profesor en 6.2):
   - pods canary en `Ready`;
   - tasa de error en CloudWatch ≤ 5 %, sobre el metric filter de logs con dimensión `version`;
   - un mínimo de N peticiones.
4. Si se cumple, sube el peso a 100 %, actualiza `stable` a la nueva imagen y pone el canary en 0.
   Si no, pone el peso en 0 y elimina el canary (rollback).

**Respaldo:** la proporción de réplicas 4:1, ya documentada. **Evolución:** Argo Rollouts o pesos con
Gateway API (`HTTPRoute`).

**A tener en cuenta:** el proyecto ingress-nginx anunció su retiro. Para minikube sirve, pero el `13`
incluye la respuesta preparada por si lo preguntan.

#### T5. Bloqueo del estado

**Rúbrica:** se evalúan el estado en S3, el versionamiento y el aislamiento por workspace; no el
mecanismo de bloqueo.

**Decisión:**

- **Mecanismo principal:** `use_lockfile = true` (bloqueo nativo de S3, Terraform ≥ 1.10, el
  recomendado actualmente).
- **Verificación en el punto de control de la Fase 1:** dos `terraform plan` simultáneos; el segundo
  debe fallar con `Error acquiring the state lock`.
- **Plan B:** si Floci no respeta las escrituras condicionales, `dynamodb_table` con la tabla de lock
  que crea `bootstrap/`.

#### T6. Nombres de los checks idénticos en el YAML y en el ruleset

**Rúbrica:** *"checks de CI obligatorios en verde antes de habilitar el botón de merge"*.

**Decisión:** cada job declara un `name:` fijo, y `.github/rulesets/protected-branches.json` lista
exactamente los mismos nombres:

- `lint-build`
- `unit-tests`
- `integration-tests`
- `e2e-tests`
- `terraform-plan`
- `promote-guard`

Si no coinciden, el merge queda bloqueado para siempre. Por eso esto va como error típico de la Fase 6
y con un punto de control propio: un PR con un test roto no se puede fusionar.

#### T7. Tiempo real con suscripciones GraphQL sobre WSS

**Rúbrica:** *"reflejando en tiempo real el comportamiento de las Feature Flags y el estado de las
reservas/compensaciones"*. El diagrama de la guía marca `HTTPS / WSS`.

**Decisión:**

- **Suscripciones:** Strawberry expone `stationUpdates`, `sagaUpdates` y `featureFlagsChanged` sobre
  WebSocket (`graphql-transport-ws`).
- **Varias réplicas:** cada suscripción consulta DynamoDB en el servidor cada 1–2 s y emite solo los
  cambios. Así funciona con varias réplicas del gateway sin necesidad de un pub/sub.
- **Ruta del tráfico:** queries y mutaciones van por HTTPS a través de API Gateway; las suscripciones
  van por WSS al Ingress de la capa GraphQL. En AWS real equivaldría a una API Gateway WebSocket API.
- **Respaldo:** si el WebSocket cae, el frontend vuelve al sondeo cada 3 s.

---

## Fases

### Bloque A — Fundamentos (día 1)

**Objetivo:** entender y poder defender cada decisión antes de escribir código.

| Documento | Contenido |
| --- | --- |
| `00-LEEME.md` | Índice, prerrequisitos, calendario de 14 días, árbol final del repo |
| `01-investigacion-buenas-practicas.md` | Buenas prácticas por tecnología, con fuentes |
| `02-teoria-y-decisiones.md` | Teoría por capa + ADR de las decisiones E1–E3 y T1–T7 (opción elegida, alternativas, motivo) |

**Punto de control:** explicar en voz alta, sin leer, qué es la SAGA por orquestación, para qué sirven
los workspaces y qué hace un VPC Endpoint.

---

### Bloque B — Entorno e infraestructura (días 2–4) · 30 % de la rúbrica

**Objetivo:** tener el estado versionado en S3 y los tres ambientes aislados por workspace.

| Documento | Contenido |
| --- | --- |
| `03-fase-0-repositorio-y-entorno.md` | Instalación de herramientas y arreglo de Docker (E2), `uv` con Python 3.12 (E3), estructura del repo, Floci en `compose.yaml`, ruff, pre-commit, shellcheck, `scripts/dev.sh` |
| `04-fase-1-terraform.md` | `bootstrap/` (bucket S3 versionado + tabla de lock de respaldo), `envs/` con backend S3 (`use_lockfile`) y workspaces, módulos `network`, `vpc_endpoints`, `dynamodb`, `observability`, `eks`, `api_gateway`, `k8s_namespace` |

**Entregables clave:**

- Validación que impide usar el workspace `default`.
- `${terraform.workspace}` en todos los nombres.
- VPCE Gateway (S3, DynamoDB) e Interface (`execute-api`, `logs`, `monitoring`).
- VPC Link + NLB interno.
- Tablas `reservations`, `billing`, `dispatch`, `sagas` y `flags` por ambiente.
- Metric filter de errores con dimensión `version` (lo usa el canary, T4).

**Punto de control:**

- Las herramientas de E2 responden sin error.
- `terraform workspace list` muestra `dev`, `test` y `prod`.
- `aws s3api list-object-versions` muestra varias versiones de `env:/dev/terraform.tfstate`.
- La prueba de bloqueo concurrente de T5 falla como se espera.
- Las tablas `aegisvolt-*-dev|test|prod` existen sin colisiones.

---

### Bloque C — Backend (días 5–7) · 25 % de la rúbrica

**Objetivo:** que la SAGA y sus compensaciones se puedan demostrar.

| Documento | Contenido |
| --- | --- |
| `05-fase-2-microservicios.md` | Librería `aegis_common` (configuración, logging JSON, correlación, cliente DynamoDB, errores) y los tres microservicios |
| `06-fase-3-graphql-saga-flags.md` | Esquema GraphQL (queries, mutaciones y suscripciones WSS, T7), orquestador SAGA, pasos y compensaciones, idempotencia, feature flags |

**Entregables clave:**

- **Idempotencia:** `saga_id` como llave, escrituras condicionales y `TransactWriteItems`. Un reembolso
  repetido no tiene efecto.
- **Flags:** `ENABLE_DYNAMIC_SURGE_PRICING`, `ENABLE_FAST_CHARGE_BOOST` y `SIMULATE_CHARGER_HARDWARE_FAULT`.

**Punto de control:** tres escenarios por GraphQL:

- **Camino feliz:** la sesión queda activa.
- **Fondos insuficientes:** se libera el conector.
- **Fallo de cargador:** se reembolsa y luego se libera.

En los tres, el estado se verifica en las tablas y la suscripción `sagaUpdates` emite cada transición.

---

### Bloque D — Empaquetado y despliegue (días 8–9)

**Objetivo:** tener los servicios corriendo en Kubernetes con despliegue canary.

| Documento | Contenido |
| --- | --- |
| `07-fase-4-docker.md` | Dockerfiles sobre `python:3.12-slim` sin root, `.dockerignore`, stack local completo, `scripts/seed.py` |
| `08-fase-5-kubernetes-canary.md` | `minikube addons enable ingress`, `k8s/base` (Deployments, Services e Ingress `stable` y `canary`) + overlays por ambiente, NetworkPolicy, ResourceQuota, `scripts/canary.py` (T4), `scripts/deploy.sh` |

**Punto de control:**

- Con `canary-weight: 20`, alrededor de 20 de cada 100 peticiones responden con la versión nueva.
- Una imagen sana promueve al 100 %.
- Una imagen con errores inducidos revierte sola a 0 %.

---

### Bloque E — Gobernanza y CI/CD (días 10–11) · 25 % de la rúbrica

**Objetivo:** que el push esté bloqueado, que todo pase por PR con checks y que el apply dependa de la rama.

| Documento | Contenido |
| --- | --- |
| `09-fase-6-cicd-git.md` | `pr-checks.yml`, `deploy.yml`, `promote-guard.yml`, ruleset JSON, `scripts/setup_rulesets.sh`, plantilla de PR, CODEOWNERS, registro del runner self-hosted |

**Entregables clave:**

- **Ubicación de los jobs:** `terraform-plan` en el runner self-hosted (T1); los demás checks en
  runners de GitHub.
- **Repo y runner:** repo público con rulesets (T2) y endurecimiento frente a forks (T3).
- **Nombres de los checks** idénticos en el YAML y en el ruleset (T6).
- **`promote-guard`:** solo acepta `feature/* → dev`, `dev → test` y `test → prod`.
- **Despliegue tras el merge:** se toma la rama, se selecciona el workspace, corre `terraform apply` y
  después el canary.

**Punto de control:**

- `git push --force` y el push directo a `test` son rechazados por el ruleset.
- Un PR con un check en rojo no puede fusionarse.
- El merge a `dev` solo modifica el workspace `dev`.

---

### Bloque F — Observabilidad y frontend (días 12–13) · 12 % + 8 %

**Objetivo:** dar trazabilidad por `correlation_id` y tener una UI conectada en tiempo real a cada ambiente.

| Documento | Contenido |
| --- | --- |
| `10-fase-7-observabilidad.md` | Logs JSON hacia `/aegisvolt/<env>/<servicio>`, consultas de CloudWatch, Prefect 3 en el entorno de Python 3.12: flujo de salud y flujo de auditoría de sagas (huérfanas, compensadas, inconsistentes) |
| `11-fase-8-frontend.md` | React: panel de estaciones, flujo de reserva, visor de flags, historial de sagas; cliente `graphql-ws` con respaldo de sondeo; `public/config.js` por ambiente |

**Punto de control:**

- Prefect muestra la ejecución de los dos flujos.
- `aws logs filter-log-events` encuentra el `correlation_id` de una saga fallida.
- Cambiar una flag en `dev` cambia la UI de `dev` sin recargar la página y deja `prod` intacta.

---

### Bloque G — Cierre (día 14)

**Objetivo:** ensayar la sustentación completa.

| Documento | Contenido |
| --- | --- |
| `12-qa.md` | Pruebas unitarias, de integración y e2e (con código), matriz manual por ambiente, checklist por rúbrica |
| `13-roadmap-sustentacion.md` | Guion de la demo, respuesta a cada pregunta del banco 6.1–6.4 con su comando exacto, respuestas preparadas sobre T4 (retiro de ingress-nginx) y T7 (WSS fuera de API Gateway), planes B |

**Punto de control:** ensayo completo de la demo de principio a fin, sin improvisar comandos.
