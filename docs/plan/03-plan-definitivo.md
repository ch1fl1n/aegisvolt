# Plan definitivo — AegisVolt, desarrollo guiado paso a paso en el chat

## Contexto

Proyecto final individual de Patrones Arquitectónicos Avanzados (14 días; sustentación por
preguntas Correcto/Incorrecto por capa). El usuario construye todo a mano en su IDE. Claude
guía en el chat, un paso a la vez: teoría corta → decisión → archivo (ruta + bloque completo) →
punto de control. Las pruebas con Docker, Kubernetes y CI van al final. Fuente de verdad:
la guía PDF + `FASES-DESARROLLO.md` del usuario (decisiones E1–E3, T1–T7, bloques A–G),
con los ajustes R1–R8 de abajo.

## Decisiones base (de FASES-DESARROLLO.md, aceptadas)

Linux CachyOS + Bash · Floci 2.4 en Compose (puerto 4566) · Python 3.12 (`uv` en el host,
`python:3.12-slim` en contenedores) · FastAPI + Strawberry + boto3 · React + Vite + TS ·
EKS por workspace en Floci (plano de control) + un minikube con namespace por ambiente y addon
`ingress` · SAGA por orquestación en la capa GraphQL con bitácora en DynamoDB · flags propias en
DynamoDB (caché 5 s) · canary con Ingress `canary-weight` 20 → 100 · suscripciones GraphQL sobre WSS
con sondeo de respaldo · GitHub Actions (runners de GitHub + self-hosted) · repo público con rulesets.

## Ajustes de la revisión (se integran al plan)

- **R1. Checks omitidos cuentan como aprobados.** Un job saltado por `if:` reporta *skipped*, y un
  check requerido en *skipped* no bloquea el merge. `terraform-plan` no se salta en PR de fork: corre
  un job ligero que falla con "plan no permitido desde forks". Así T3 no abre un hueco en T6.
- **R2. Texto exacto del ajuste de GitHub (T3).** *Settings → Actions → General → "Approval for
  running fork pull request workflows from contributors" → "Require approval for all external
  contributors"*.
- **R3. Red entre Floci y minikube.** Son dos redes Docker distintas. Hace falta
  `docker network connect minikube floci` y la integración de API Gateway apunta a la IP del Ingress
  de minikube. Va en `scripts/dev.sh`. En la explicación del paquete se distingue lo emulado (VPC
  Link/NLB como registro en Floci) de lo real en AWS.
- **R4. Logs hacia CloudWatch.** Los pods no envían logs solos. Se añade a `aegis_common` un handler
  que publica en CloudWatch Logs vía boto3 (`/aegisvolt/<env>/<servicio>`) además de stdout.
- **R5. Riesgo del canary en Floci.** No está verificado que Floci genere métricas a partir de un
  metric filter. Plan principal: `canary.py` lee la métrica `ErrorCount` / `RequestCount` por
  `version`. Plan B ya escrito en el mismo script: calcular la tasa con `FilterLogEvents` sobre los
  logs de la versión canary. La respuesta en la sustentación es la misma condición.
- **R6. WSS y canary.** Las suscripciones también pasan por el Ingress. Se fija la afinidad
  (`canary-by-header` para pruebas) y se explica que un WebSocket queda pegado a la versión en la que
  se abrió.
- **R7. Guardia del plan (T1).** "Destruye recursos de otro ambiente" se implementa con
  `terraform show -json plan.out | jq` sobre `resource_changes[].change.actions` que contengan
  `delete` y cuyo nombre no termine en `-<workspace>`.
- **R8. Equipo: Windows 11** (corregido por el usuario). Comandos en PowerShell, scripts de
  automatización en Python (`dev.py`, `setup_rulesets.py`), CI en runners Ubuntu con bash,
  `.gitattributes` con `eol=lf`. Sustituye E1/E2 de FASES-DESARROLLO.md.

## Cómo se ejecuta

Bloques A → G de FASES-DESARROLLO.md, en orden. En cada mensaje del chat: un paso con
1. teoría mínima y la pregunta de la rúbrica que responde,
2. archivo(s): ruta exacta + bloque de código completo,
3. punto de control (comando + salida esperada).
El usuario responde "listo" o pega el error. No se avanza de bloque sin su punto de control.
Docker, minikube, canary y CI en vivo se prueban al final (bloques D, E y G).

Primer paso: Bloque B, Fase 0 → estructura del repo, `.gitignore`, `pyproject.toml`
(`requires-python = ">=3.12,<3.13"`), `compose.yaml` de Floci. La teoría del Bloque A se da por
partes al inicio de cada fase en lugar de un documento aparte.

## Verificación

Puntos de control de FASES-DESARROLLO.md por bloque, más `12-qa` (unit/integración/e2e) y el
ensayo completo de la demo del bloque G.
