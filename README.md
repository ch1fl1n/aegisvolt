<div align="center">

# ⚡ AegisVolt

**Plataforma cloud-native de gestión de carga para flotas eléctricas y electrolineras**

Proyecto final individual · Patrones Arquitectónicos Avanzados

`SAGA orquestada` · `GraphQL` · `Microservicios en Kubernetes` · `Terraform por workspace` ·
`Canary con rollback automático` · `Feature flags por ambiente` · `CloudWatch + Prefect`

</div>

---

Tres microservicios de dominio detrás de un gateway GraphQL que orquesta una SAGA "Reservar y
activar carga". Infraestructura como código con un workspace por ambiente estático (`dev`,
`test`, `prod`), promoción por PR con checks obligatorios y despliegue canary automático tras
cada merge. AWS se emula en local con **Floci**; Kubernetes corre en **minikube** (un namespace
por ambiente).

## Contenido

1. [Vista para la presentación](#vista-para-la-presentación)
2. [C4 nivel 1: contexto](#c4-nivel-1-contexto)
3. [C4 nivel 2: contenedores](#c4-nivel-2-contenedores)
4. [C4 nivel 3: componentes del gateway](#c4-nivel-3-componentes-del-gateway)
5. [SAGA: camino feliz y compensación](#saga-camino-feliz-y-compensación)
6. [Despliegue y promoción entre ambientes](#despliegue-y-promoción-entre-ambientes)
7. [Stack, estructura y cómo correrlo](#stack)

## Vista para la presentación

Un solo diagrama con las 5 capas que evalúa la rúbrica y el recorrido de una petición.

```mermaid
flowchart TB
  UI["<b>5 · Presentación</b><br/>Panel React: flags y sagas en vivo (WSS)"]
  subgraph RED["1 · IaC · red privada"]
    direction LR
    APIGW["API Gateway"] -->|VPC Link| NLB["NLB interno<br/>health check /healthz"]
  end
  subgraph K8S["3 · Backend · Kubernetes"]
    direction LR
    ING["Ingress NGINX<br/>80 % estable · 20 % canary"] --> GW["graphql-gateway<br/>orquestador SAGA + flags"]
    GW --> SR["1 · reservar<br/>station-reservation"]
    GW --> BW["2 · cobrar<br/>billing-wallet"]
    GW --> ED["3 · activar carga<br/>energy-dispatch"]
  end
  subgraph DATA["1 · IaC · datos y estado"]
    direction LR
    DDB[("DynamoDB<br/>tabla por servicio y ambiente")]
    S3[("S3 tfstate<br/>versionado + KMS + lock")]
  end
  subgraph OBS["4 · Observabilidad"]
    direction LR
    CW["CloudWatch<br/>logs con correlation_id"]
    PF["Prefect<br/>health + auditoría de sagas"]
  end
  subgraph CICD["2 · CI/CD y gobernanza"]
    direction TB
    PR["PR + 6 checks<br/>ruleset sin bypass"] -->|merge| GA["deploy.yml<br/>rama → workspace → apply → canary"]
  end
  UI -->|HTTPS / WSS| APIGW
  NLB --> ING
  K8S -->|VPCE Gateway| DDB
  K8S -.->|VPCE Interface| CW
  PF -.->|lee| DDB
  GA -->|terraform apply| S3
  GA -->|canary 20 %| ING
```

## C4 nivel 1: contexto

```mermaid
flowchart TB
  OP(["👤 Operador de flota<br/>inicia cargas y ve su saldo"])
  ADM(["👤 Administrador de plataforma<br/>activa feature flags por ambiente"])
  DEV(["👤 Equipo de desarrollo<br/>propone cambios por PR"])
  AV["<b>AegisVolt</b><br/>reserva conectores, cobra la carga y activa<br/>el cargador con consistencia SAGA"]
  CH["Cargadores de las electrolineras<br/>(simulados en energy-dispatch)"]
  AWS["AWS: API Gateway, DynamoDB, CloudWatch, S3, KMS<br/>(emulado con Floci)"]
  GH["GitHub<br/>rulesets + Actions con runner self-hosted"]

  OP -->|panel web: GraphQL| AV
  ADM -->|panel web con token| AV
  AV -->|inicia y detiene sesiones| CH
  AV -->|persiste estado, logs y métricas| AWS
  DEV -->|PR -> merge| GH
  GH -->|terraform apply + despliegue canary| AV

  classDef person fill:#08427b,color:#fff,stroke:#052e56
  classDef system fill:#1168bd,color:#fff,stroke:#0b4884
  classDef ext fill:#999,color:#fff,stroke:#6b6b6b
  class OP,ADM,DEV person
  class AV system
  class CH,AWS,GH ext
```

## C4 nivel 2: contenedores

```mermaid
flowchart TB
  U(["👤 Operador / Administrador"])
  subgraph AV["AegisVolt · un ambiente"]
    FE["<b>frontend</b><br/>React + Vite, servido por NGINX<br/>queries, mutations y subscriptions"]
    APIGW["<b>API Gateway HTTP</b><br/>VPC Link hacia la red privada"]
    NLB["<b>NLB interno</b><br/>health check HTTP /healthz"]
    ING["<b>Ingress NGINX</b><br/>canary-weight 20 %"]
    GW["<b>graphql-gateway</b><br/>Python · FastAPI + Strawberry<br/>orquestador SAGA, flags, seguridad"]
    SR["<b>station-reservation-service</b><br/>FastAPI · conectores"]
    BW["<b>billing-wallet-service</b><br/>FastAPI · saldo, cobro, reembolso"]
    ED["<b>energy-dispatch-service</b><br/>FastAPI · sesiones de carga"]
    T1[("reservations")]
    T2[("billing")]
    T3[("dispatch")]
    T4[("sagas · bitácora")]
    T5[("flags")]
  end
  CW["CloudWatch Logs / Metrics<br/>/aegisvolt/&lt;env&gt;/&lt;servicio&gt;"]
  PF["Prefect<br/>environment-health · saga-audit"]

  U --> FE
  U -->|HTTPS / WSS| APIGW --> NLB --> ING --> GW
  ING -.-> FE
  GW -->|REST + x-correlation-id| SR & BW & ED
  SR --> T1
  BW --> T2
  ED --> T3
  GW --> T4 & T5
  GW & SR & BW & ED -.->|logs JSON| CW
  PF -.->|lee| T4 & CW

  classDef c fill:#438dd5,color:#fff,stroke:#2e6295
  classDef db fill:#2f6f9f,color:#fff,stroke:#1f4a6b
  classDef ext fill:#999,color:#fff,stroke:#6b6b6b
  class FE,APIGW,NLB,ING,GW,SR,BW,ED c
  class T1,T2,T3,T4,T5 db
  class CW,PF,U ext
```

Las tablas llevan el sufijo del ambiente (`aegisvolt-sagas-dev`, `aegisvolt-flags-prod`, …):
cada microservicio es dueño de su tabla y nadie lee la de otro.

## C4 nivel 3: componentes del gateway

```mermaid
flowchart LR
  REQ["Petición GraphQL<br/>HTTP / WebSocket"]
  subgraph GW["graphql-gateway"]
    MW["Middleware ASGI<br/>(aegis_common)<br/>correlation_id + log http_request"]
    SCH["schema.py<br/>tipos, enum FlagName"]
    RES["resolvers.py<br/>queries, mutations,<br/>subscriptions por sondeo"]
    SEC["security.py<br/>token admin<br/>hmac.compare_digest"]
    FL["flags.py<br/>caché 5 s, ausente = OFF"]
    ORC["saga/orchestrator.py<br/>ejecuta pasos y compensa<br/>en orden inverso"]
    ST["saga/steps.py<br/>quote, reserve, charge, start"]
    REP["saga/repository.py<br/>guarda cada transición"]
    CLI["clients.py<br/>httpx, timeout 20 s,<br/>reintentos de red"]
  end
  REQ --> MW --> SCH --> RES
  RES --> SEC & FL & ORC
  ORC --> ST --> CLI
  ORC --> REP
  CLI --> MS["3 microservicios"]
  REP --> T[("aegisvolt-sagas-&lt;env&gt;")]
  FL --> F[("aegisvolt-flags-&lt;env&gt;")]
```

## SAGA: camino feliz y compensación

```mermaid
sequenceDiagram
  autonumber
  participant UI as Panel React
  participant GW as graphql-gateway (orquestador)
  participant SR as station-reservation
  participant BW as billing-wallet
  participant ED as energy-dispatch
  UI->>GW: startCharge(sagaId, estación, conector, cuenta, kWh)
  GW->>SR: reservar conector (RESERVED)
  GW->>BW: cobrar (transacción condicional, idempotente por sagaId)
  GW->>ED: iniciar carga
  alt carga iniciada
    ED-->>GW: 200
    GW-->>UI: COMPLETED
  else falla física o flag SIMULATE_CHARGER_HARDWARE_FAULT
    ED-->>GW: 422 CHARGER_FAULT
    GW->>ED: detener carga (compensa el paso que falló)
    GW->>BW: reembolsar (registra REFUND)
    GW->>SR: liberar conector (AVAILABLE)
    GW-->>UI: COMPENSATED
  end
  Note over GW,BW: Si falla el cobro (fondos insuficientes) solo se libera el conector.
```

Cada transición se guarda en `aegisvolt-sagas-<env>`; si una compensación falla la saga queda
`FAILED` y la auditoría de Prefect la reporta. El `correlation_id` viaja en `x-correlation-id`
a los 4 servicios: `scripts/trace_saga.py` reconstruye la línea de tiempo desde CloudWatch.

## Despliegue y promoción entre ambientes

```mermaid
flowchart LR
  F["feature/*"] -->|PR + 6 checks| D["dev"]
  D -->|PR + 6 checks<br/>+ promote-guard| T["test"]
  T -->|PR + 6 checks<br/>+ promote-guard| P["prod"]
  D & T & P -->|push del merge| PIPE
  subgraph PIPE["deploy.yml (runner self-hosted)"]
    direction TB
    A["ENV_NAME = rama destino"] --> B["terraform workspace select<br/>+ apply (plan_guard)"]
    B --> C["build de imágenes<br/>tag = sha corto"]
    C --> K["canary 20 %<br/>5xx de la versión nueva > 5 %?"]
    K -->|no| OK["promoción"]
    K -->|sí o sin datos| RB["rollback automático"]
  end
```

- **Ruleset `protected-branches`** en `dev`, `test` y `prod`: sin push directo ni force push, sin
  borrado, PR obligatorio con los 6 checks (`lint-build`, `unit-tests`, `integration-tests`,
  `e2e-tests`, `terraform-plan`, `promote-guard`) y sin bypass.
- **Estado de Terraform** en S3 versionado (`env:/<workspace>/terraform.tfstate`), cifrado con KMS
  propia y lock en DynamoDB; `plan_guard.py` bloquea borrados fuera del workspace.

## Stack

| Capa | Tecnología |
| --- | --- |
| Frontend | React 18 + Vite + TypeScript, `graphql-ws` |
| Backend | Python 3.12, FastAPI, Strawberry GraphQL, httpx, boto3 |
| Datos | DynamoDB (una tabla por servicio y ambiente) |
| Contenedores | Docker, Kubernetes (minikube), Kustomize, Ingress NGINX |
| IaC | Terraform (workspaces), S3 + KMS + DynamoDB lock; módulos `network`, `vpc_endpoints`, `api_gateway`, `eks`, `dynamodb`, `observability` |
| CI/CD | GitHub Actions (`pr-checks.yml`, `deploy.yml`), runner self-hosted, rulesets |
| Observabilidad | CloudWatch Logs/Metrics (JSON con `correlation_id`), Prefect 3 |
| AWS local | Floci (puerto 4566) |

## Estructura

| Carpeta | Contenido |
| --- | --- |
| `services/` | `graphql-gateway` y los 3 microservicios |
| `libs/aegis_common/` | logging a CloudWatch, middleware de `correlation_id` |
| `frontend/` | panel React (estaciones, iniciar carga, flags, historial de sagas) |
| `infra/` | `bootstrap` (bucket del estado + KMS + lock), `envs` y `modules` |
| `k8s/` | manifiestos base + overlays por ambiente (Kustomize) |
| `scripts/` | `deploy.py`, `canary.py`, `plan_guard.py`, `reset_demo.py`, `trace_saga.py`, `saga_test.ps1` |
| `observability/prefect/` | flujos `environment-health` y `saga-audit` |
| `docs/` | plan, runbook, guion de la sustentación y explicaciones |

## Cómo correrlo (resumen)

Requisitos: Docker Desktop, minikube, `uv`, Terraform, AWS CLI, `gh`. Detalle en
[`docs/runbook-demo.md`](docs/runbook-demo.md).

```powershell
docker compose up -d                                        # Floci (AWS local, puerto 4566)
minikube start -p aegisvolt                                 # clúster con addon ingress
uv run python scripts/deploy.py --env dev --tag local1      # build + despliegue escalonado
kubectl -n ingress-nginx port-forward svc/ingress-nginx-controller 8080:80
```

Frontend: `http://dev.aegisvolt.local:8080` (resolver `*.aegisvolt.local` a 127.0.0.1).

## Documentación

- [`docs/guion-sustentacion.md`](docs/guion-sustentacion.md): preparación y guion de la demo.
- [`docs/explicaciones-demo.md`](docs/explicaciones-demo.md): teoría por bloque y preguntas.
- [`docs/runbook-demo.md`](docs/runbook-demo.md): comandos detallados y qué hacer si algo falla.
- [`docs/plan/`](docs/plan/): plan original, fases y plan definitivo.
