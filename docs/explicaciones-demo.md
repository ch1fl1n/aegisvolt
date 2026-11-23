# Explicaciones de la demo (teoría en el orden del guion) y preguntas

Acompaña a `guion-sustentacion.md`. El guion dice QUÉ hacer y una idea por bloque; aquí está
el contexto completo para explicarlo con tus palabras: qué es cada pieza, para qué la usamos y
qué hay adentro. Luego las preguntas difíciles, el banco de preguntas de la guía (§6) y, al
final (§11), los bloques de código reales que respaldan cada respuesta.

## 0. Preparación: qué se levantó y por qué

- **Docker Desktop:** motor de contenedores. Ahí viven Floci y el nodo de minikube.
- **Floci:** emulador local de AWS (puerto 4566). Nos da S3, DynamoDB, KMS, CloudWatch,
  API Gateway, VPC/EKS como API compatible, sin cuenta ni costo. Terraform y boto3 le hablan
  igual que a AWS, solo cambia el `endpoint_url`. Lo emulado (VPC Link, NLB, EKS) existe como
  registro: el tráfico real entra por el Ingress de minikube.
- **minikube (perfil `aegisvolt`):** un clúster Kubernetes de un nodo. Un namespace por
  ambiente (`aegisvolt-dev`, `-test`, `-prod`) y el addon `ingress` (NGINX).
- **Anti-tormenta:** al arrancar, Kubernetes intenta revivir todos los pods a la vez; en un
  nodo de 2 GB eso agota la RAM y los probes fallan en cadena. Por eso se escala todo a 0 y
  `deploy.py` sube los servicios de uno en uno, esperando `rollout status`.
- **Runner self-hosted:** el `deploy.yml` necesita llegar a minikube y a Floci, que solo
  existen en este PC. GitHub le manda el job al runner; sin runner, el merge en vivo no corre.
- **Port-forward 8080 + Chrome con `--host-resolver-rules`:** el Ingress decide el ambiente
  por el nombre del host (`dev.aegisvolt.local`, ...). En vez de editar el archivo hosts,
  Chrome resuelve `*.aegisvolt.local` a 127.0.0.1 y el port-forward lleva el 8080 al Ingress.
- **Prefect:** orquestador de flujos en Python (ver bloque 8). `PREFECT_HOME` apunta a una base
  propia del proyecto para no chocar con otra instalación.

## 1. Arquitectura (README)

Código para mostrar: §11.2.

Recorrido de una petición: navegador -> **API Gateway** (HTTP API, punto de entrada único,
throttling) -> **VPC Link** (conecta el API Gateway con recursos privados de la VPC) ->
**NLB interno** (sin IP pública, health check HTTP `/healthz`) -> **Ingress NGINX** (enruta
por host y reparte estable/canary) -> **graphql-gateway** -> 3 microservicios:
`station-reservation` (conectores), `billing-wallet` (cobros y reembolsos) y `energy-dispatch`
(entrega de energía). Cada servicio tiene SU tabla de DynamoDB (base de datos por servicio).

- **Por qué GraphQL en el borde:** el frontend pide exactamente lo que necesita en una sola
  llamada, y las suscripciones (WSS) empujan cambios en vivo (flags, estado de conectores).
- **Por qué microservicios:** cada dominio escala, falla y se despliega por separado. El
  costo es la consistencia distribuida, que resuelve la SAGA.
- **VPC Endpoints:** el tráfico interno a DynamoDB/S3 (Gateway) y a CloudWatch (Interface) no
  sale a internet.

## 2. IaC: Terraform con workspaces

Código para mostrar: §11.1.

- **Terraform:** describe la infraestructura como código declarativo; `plan` muestra la
  diferencia y `apply` la aplica. Es reproducible y revisable en un PR.
- **Workspaces:** el mismo código, un estado separado por ambiente (`dev`, `test`, `prod`).
  Los nombres llevan el sufijo del workspace (`aegisvolt-flags-dev`), así un apply de test no
  puede tocar prod.
- **Backend remoto:** el estado vive en S3 (`aegisvolt-tfstate`, clave `env:/<ws>/...`),
  **versionado** (se puede volver a una versión anterior), **cifrado con KMS propia** (el
  estado puede tener datos sensibles) y con **lock** en DynamoDB (dos applies a la vez no
  corrompen el estado).
- **`bootstrap`:** crea el bucket, la llave KMS y la tabla de lock. Es el huevo y la gallina:
  el backend no puede guardarse a sí mismo, por eso tiene estado local.
- **Módulos:** `network` (VPC, subredes públicas y privadas, NAT, tablas de rutas),
  `vpc_endpoints`, `api_gateway` (HTTP API, VPC Link, NLB y sus SG), `eks`, `dynamodb`,
  `observability` (log groups, metric filters, alarmas).
- **`plan_guard.py`:** lee el plan en JSON y bloquea cualquier `delete` de un recurso que no
  termine en `-<workspace>`: un plan de dev nunca destruye algo de otro ambiente.

## 3. SAGA por orquestación

Código para mostrar: §11.3 y §11.4.

- **El problema:** cargar un vehículo toca 3 servicios con 3 bases de datos. No hay una
  transacción ACID entre ellas.
- **SAGA:** una secuencia de transacciones locales; si una falla, se ejecutan
  **compensaciones** en orden inverso. Aquí: reservar conector -> cobrar -> despachar energía.
  Si el despacho falla: reembolsar -> liberar conector. Estado final `COMPENSATED`.
- **Orquestación (no coreografía):** el gateway dirige los pasos y guarda cada transición en
  la bitácora `aegisvolt-sagas-<env>`. Un solo lugar para ver y auditar la saga.
- **Idempotencia:** cada escritura usa `saga_id` + paso como clave y una condición
  `attribute_not_exists(sk)`: si un paso o compensación llega dos veces, la segunda no cobra ni
  reembolsa de nuevo.
- **Flag de falla `SIMULATE_CHARGER_HARDWARE_FAULT`:** hace fallar el despacho a propósito para
  mostrar la compensación sin romper nada real.
- **`correlation_id`:** viaja en las cabeceras de gateway a micros y sale en cada log; con él se
  sigue una saga en los 4 servicios.

## 4. Feature flags por ambiente

Código para mostrar: §11.5.

- **Qué son:** interruptores para activar o desactivar comportamiento sin redesplegar.
- **Dónde viven:** tabla `aegisvolt-flags-<env>`; cada ambiente tiene la suya, así cambiar dev
  no toca prod. Si la tabla no tiene la fila, la flag vale el valor por defecto (apagada).
- **Cómo llegan al frontend:** el gateway las cachea 5 s y las empuja por una suscripción
  GraphQL sobre WSS; si el WebSocket cae, el panel sondea (badge `polling`).
- **Seguridad:** cambiar una flag exige `x-admin-token`; el token es distinto por ambiente y no
  se guarda en el navegador (solo en memoria).

## 5. Canary manual y rollback (`canary.py`)

Código para mostrar: §11.6.

- **Canary:** desplegar la versión nueva junto a la estable y mandarle solo una parte del
  tráfico (20 %). Si se porta mal, se retira sin que la mayoría de usuarios lo note.
- **Cómo se reparte:** dos Deployments (estable y canary) y dos Ingress; el del canary lleva
  `canary-weight: 20`. NGINX reparte por petición, no por pod.
- **Cómo decide:** lee de CloudWatch la tasa de 5xx **solo de la versión canary** (dimensión
  `Version`; cada respuesta trae `x-service-version`). Necesita >= 20 peticiones y <= 5 % de
  errores para promover; si no, rollback.
- **`--chaos 0.5`:** la versión de prueba devuelve 5xx en la mitad de las peticiones; el script
  ve ~50 % > 5 % y hace rollback: peso 0 y se borra el canary. El estable nunca se tocó.
- **Cuatro reglas de seguridad** (modelo Argo Rollouts):
  - fail-safe: si no se puede medir, rollback;
  - anti-dilución: si estable y canary tienen el mismo tag, se aborta;
  - promoción con red: si la promoción falla, `rollout undo`;
  - primer despliegue: sin versión previa, entra como estable y el canary se omite con aviso.

## 6. CI/CD: PR dev -> test y despliegue automático

Código para mostrar: §11.7.

- **Ramas = ambientes:** `dev`, `test`, `prod`. Se promueve con un PR `dev -> test`.
- **Rulesets:** en `test` y `prod` no se puede hacer push directo ni `--force` (GitHub
  responde `GH013`); solo entra código por PR con los checks requeridos en verde.
- **`pr-checks.yml` (antes del merge):** lint y build, unit, integración, e2e, `security-scan`
  (gitleaks y dependencias), `terraform-plan` (con `plan_guard`) y `promote-guard` (solo se
  promueve en orden dev -> test -> prod).
- **`deploy.yml` (después del merge, en el runner):**
  1. `ENV_NAME: ${{ github.ref_name }}`: la rama del merge ES el ambiente (detección dinámica
     del target branch);
  2. `terraform workspace select "$ENV_NAME"` + `apply`;
  3. ¿hay un gateway estable previo? (si no, primer despliegue sin canary);
  4. build de las imágenes con el sha corto como tag y despliegue;
  5. canary 20 % con métricas de CloudWatch -> promoción al 100 % o rollback automático.
- **Por qué dev se baja a 0 durante el run:** el nodo tiene 2 GB y el host 6 GB; con todo
  arriba el canary recibe 503 por falta de memoria y el fail-safe lo marca inconcluso. Bajar
  dev no cambia nada de lo que se evalúa: el run despliega en test.

## 7. Prod intacto

Código para mostrar: §11.5 (`DEFAULTS` y `graphql_ide`).

- La flag que se cambió en dev no aparece en `aegisvolt-flags-prod`: tabla distinta, workspace
  distinto, token distinto. Se muestra con un `scan` a ambas tablas (no requiere pods).
- Prod no expone GraphiQL (superficie mínima): en prod la consola de GraphQL está apagada.

## 8. Observabilidad: CloudWatch + Prefect

Código para mostrar: §11.8.

- **CloudWatch Logs:** cada servicio publica en `/aegisvolt/<env>/<servicio>` (JSON con
  `correlation_id`, versión, status). Los metric filters convierten logs en métricas.
- **Prefect:** orquestador de flujos en Python: tareas con reintentos, programación (cada X
  min con `serve.py`), UI con historial de corridas, logs y artifacts.
- **`environment-health`:** comprueba Floci, que existan las tablas del ambiente y la tasa de
  errores por servicio en los últimos minutos.
- **`saga-audit`:** cruza la bitácora de sagas con reservas y cobros y marca:
  - huérfanas: estado intermedio viejo, el gateway murió a mitad;
  - inconsistentes: COMPLETED sin cobro, o COMPENSATED sin reembolso;
  - fallidas: falló una compensación.
  Solo lee; publica un artifact markdown y termina en rojo si encuentra algo. Que hoy salga
  Failed con 6 huérfanas es esperado: son sagas de pruebas interrumpidas a propósito.
- **Por qué Prefect además de la SAGA:** la SAGA compensa lo que sabe que falló; lo que no
  puede ver (un proceso muerto a mitad) lo detecta la auditoría.

## 9. Preguntas difíciles probables (respuesta corta)

- **¿Por qué orquestación y no coreografía?** Un solo lugar con el estado de la saga
  (bitácora), compensaciones explícitas y trazables; con 3 servicios la coreografía dispersa
  la lógica y dificulta auditar.
- **¿Serviría en una empresa real?** Sí: es el problema de cualquier operador de carga (o de
  reservas de hotel + vuelo, o apps de transporte): una operación de negocio toca varios
  servicios con su propia base, no hay transacción ACID entre ellos y no se puede dejar al
  cliente cobrado sin carga ni un conector bloqueado. Lo que ya es "de producción": estado
  persistido en cada paso, compensaciones idempotentes, saga_id como llave de idempotencia,
  correlation_id para soporte ("¿se le cobró a este cliente?" -> `trace_saga.py`) y auditoría
  periódica de huérfanas. Lo que agregaría en real: preautorización (retener el saldo y capturar
  al terminar la carga, como hacen las pasarelas de pago), reanudación automática de huérfanas
  y alertas del run de auditoría hacia el equipo de guardia.
- **¿Por qué en la traza sale "Detener carga" antes del reembolso?** Se compensa también el paso
  que falló (pudo arrancar el cargador antes de reportar el error); detener es idempotente.
  Orden inverso: detener -> reembolsar -> liberar.
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
- **¿Si el canary no recibe suficiente tráfico?** Inconcluso => rollback igual (fail-safe, como
  Argo Rollouts "Inconclusive"); en CI no hay humano para decidir.
- **¿Y el primer despliegue de un ambiente?** No hay versión anterior contra la cual medir: entra
  directo como estable y el canary se omite con aviso (como Argo Rollouts con la primera
  revisión). Se detecta con `--ignore-not-found`: una API caída falla el job, no salta el canary.
- **¿Por qué bajaste dev antes del merge?** Recursos del portátil (6 GB): el nodo de 2 GB no
  aguanta dev completo + test + canary. En AWS real cada ambiente tendría su clúster o nodos.
- **¿Por qué la versión va dentro de la imagen?** Imágenes inmutables: el tag identifica el
  contenido; la métrica se filtra por versión. Y el ARG va al final para no romper la caché.
- **¿Por qué los checks omitidos no cuentan?** Un job saltado reporta "skipped" y GitHub lo
  toma como aprobado: por eso en forks `terraform-plan` corre y falla a propósito (R1).
- **¿Cómo se protege el runner self-hosted de un fork?** Aprobación obligatoria para todo
  contribuidor externo, y los jobs de fork van a ubuntu-latest, nunca al runner.
- **¿Secretos?** `.env` fuera del repo; en CI secretos de environment, uno por ambiente;
  gitleaks en cada PR; se rotó el token tras imprimirse una vez.
- **¿Por qué FilterLogEvents?** Floci no genera datapoints de metric filters (R5): plan A
  métricas, plan B logs, misma condición de decisión.

## 10. Banco de preguntas de la guía (§6) -> respuesta y demostración

| § | Pregunta | Demostración / respuesta |
| --- | --- | --- |
| 6.1 | ¿apply en test no pisa prod? | `workspace list`; tablas `aegisvolt-<t>-<ws>`; estado en `env:/<ws>/`; `plan_guard.py` (R7) |
| 6.1 | Versiones del tfstate de dev y cómo restaurar | ver "Restaurar el tfstate" abajo |
| 6.1 | Recorrido del paquete API GW -> pod | ver "Recorrido del paquete" abajo |
| 6.2 | `push --force` / push directo a test | `git push origin HEAD:test` y `git push --force origin HEAD:test` -> `GH013` (ruleset) |
| 6.2 | ¿Cómo elige el YAML el ambiente del apply? | `deploy.yml`: `ENV_NAME: ${{ github.ref_name }}` -> `terraform workspace select "$ENV_NAME"` |
| 6.2 | ¿Qué evalúa el canary antes de 20 % -> 100 %? | canary Ready + >= 20 peticiones + 5xx <= 5 % de ESA versión en CloudWatch |
| 6.3 | Flag de falla + mutación + tablas DynamoDB | ver "SAGA y tablas" abajo |
| 6.3 | ¿Idempotencia si una compensación llega 2 veces? | clave = `saga_id` + paso (`sk`): escritura condicional, la 2a no cobra/reembolsa de nuevo |
| 6.4 | Prefect + `correlation_id` de una saga fallida | Prefect UI; `filter-log-events` (runbook §5) -> copiar `correlation_id` -> buscarlo en los 3 servicios |
| 6.4 | Flag en dev sin redesplegar; prod intacto | frontend dev cambia en vivo (WSS); `scan` de `aegisvolt-flags-prod` |

### Restaurar el tfstate (6.1)

```powershell
aws --endpoint-url http://localhost:4566 s3api list-object-versions --bucket aegisvolt-tfstate `
  --prefix env:/dev/ --query "Versions[].[VersionId,LastModified,IsLatest]" --output table
```

Restaurar = copiar la versión buena encima (queda como la más nueva; no se borra historia):
`aws s3api copy-object --bucket aegisvolt-tfstate --key env:/dev/terraform.tfstate --copy-source
"aegisvolt-tfstate/env:/dev/terraform.tfstate?versionId=<ID>"` y luego `terraform plan` para ver
la deriva. No se ejecuta en vivo (solo se explica). Fuente: AWS S3 "Restoring previous versions".

### Recorrido del paquete (6.1)

Cliente -> API Gateway (HTTP API) -> ruta `$default` -> integración privada por **VPC Link**
(interfaces en subredes privadas, SG `apigw-vpclink-sg`: solo sale TCP al puerto del ingress
dentro del CIDR de la VPC) -> **NLB interno** sin IP pública (SG `nlb-sg`: solo entra desde la
VPC) -> target group con health check HTTP `/healthz` -> nodos del clúster -> Ingress NGINX
(reparte 80/20 estable/canary) -> Service -> pod. Las subredes privadas usan su tabla de rutas
privada (salida por NAT); el tráfico a S3/DynamoDB va por **VPCE Gateway** (entrada en esa tabla
de rutas) y a CloudWatch/API por **VPCE Interface** (ENI + SG de 443 desde la VPC): nada interno
sale a internet.

### SAGA y tablas (6.3)

La guía dice "en test"; el profe aprobó el modo liviano (SAGA completa en dev, test/prod solo
gateway). Si lo pide en test, tras el run del merge (no durante): `.\scripts\saga_test.ps1`
(~4,5 min). Evidencia en DynamoDB (dev):

```powershell
aws --endpoint-url http://localhost:4566 dynamodb scan `
  --table-name aegisvolt-billing-dev --max-items 5
aws --endpoint-url http://localhost:4566 dynamodb scan `
  --table-name aegisvolt-reservations-dev --max-items 5
```

Debe verse el cargo y su reembolso con el mismo `saga_id`, y el conector de vuelta en `AVAILABLE`.

## 11. Código para mostrar (si piden "muéstrame dónde está")

Bloques reales del repo, en el orden de la demo. Se abren en GitHub (pestaña del repo) con la
ruta indicada; ahí se busca con `t` (buscar archivo) y luego Ctrl+F.

### 11.1 IaC: estado remoto versionado, cifrado y con lock

`infra/envs/versions.tf` (un estado por workspace; el lock es nativo de S3):

```hcl
  backend "s3" {
    key                  = "terraform.tfstate"
    workspace_key_prefix = "env:" # => env:/dev/..., env:/test/..., env:/prod/...
    encrypt              = true
    use_lockfile         = true # bloqueo nativo en S3 (Terraform >= 1.10)
  }
```

`infra/bootstrap/main.tf` (bucket con versiones + KMS propia):

```hcl
resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  versioning_configuration {
    status = "Enabled" # cada escritura del tfstate crea una versión recuperable
  }
}

# Llave KMS PROPIA (customer managed) para el estado: control de acceso y auditoría de quién
# descifra el tfstate, que puede contener datos sensibles. Rotación anual automática.
resource "aws_kms_key" "tfstate" {
  description             = "Cifrado del estado de Terraform de ${var.project}"
  enable_key_rotation     = true
  deletion_window_in_days = 7

  lifecycle {
    prevent_destroy = true # sin la llave, el estado cifrado no se puede leer
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.tfstate.arn
    }
    bucket_key_enabled = true # una llave por bucket: hasta 99 % menos llamadas (y costo) a KMS
  }
}
```

`scripts/plan_guard.py` (un plan nunca destruye recursos de otro ambiente):

```python
def foreign_deletes(plan: dict, workspace: str) -> list[str]:
    bad = []
    for change in plan.get("resource_changes", []):
        if "delete" not in change.get("change", {}).get("actions", []):
            continue
        name = resource_name(change)
        if not name.endswith(f"-{workspace}"):
            bad.append(f"{change['address']} ({name})")
    return bad
```

### 11.2 Recorrido del paquete: API Gateway -> VPC Link -> NLB interno

`infra/modules/api_gateway/main.tf`:

```hcl
resource "aws_lb" "internal" {
  name               = "${var.name_prefix}-nlb"
  internal           = true
  load_balancer_type = "network"
  subnets            = var.private_subnet_ids
  security_groups    = [aws_security_group.nlb.id]
}

resource "aws_lb_target_group" "ingress" {
  # ...
  # HTTP y no TCP: confirma que el ingress-nginx RESPONDE (no solo que el puerto abre).
  health_check {
    protocol            = "HTTP"
    port                = "traffic-port"
    path                = "/healthz"
    matcher             = "200"
    healthy_threshold   = 2
    unhealthy_threshold = 2
    interval            = 10
  }
}

resource "aws_apigatewayv2_vpc_link" "this" {
  name               = "${var.name_prefix}-vpclink"
  subnet_ids         = var.private_subnet_ids
  security_group_ids = [aws_security_group.vpc_link.id]
}

resource "aws_apigatewayv2_integration" "cluster" {
  api_id             = aws_apigatewayv2_api.this.id
  integration_type   = "HTTP_PROXY"
  integration_method = "ANY"
  connection_type    = "VPC_LINK"
  connection_id      = aws_apigatewayv2_vpc_link.this.id
  integration_uri    = aws_lb_listener.ingress.arn # el VPC Link entrega al listener del NLB
  # ...
}

resource "aws_apigatewayv2_route" "default" {
  api_id    = aws_apigatewayv2_api.this.id
  route_key = "$default" # todo lo que llegue (p. ej. POST /graphql) va al clúster
  target    = "integrations/${aws_apigatewayv2_integration.cluster.id}"
}
```

`infra/modules/vpc_endpoints/main.tf` (tráfico interno sin salir a internet):

```hcl
resource "aws_vpc_endpoint" "dynamodb" {
  vpc_id            = var.vpc_id
  service_name      = "com.amazonaws.${var.region}.dynamodb"
  vpc_endpoint_type = "Gateway"                 # entrada en la tabla de rutas privada
  route_table_ids   = var.private_route_table_ids
  # Mínimo privilegio: desde la red de este ambiente solo se tocan SUS tablas (policy).
}

resource "aws_vpc_endpoint" "interface" {
  for_each = toset(var.interface_services)     # logs, monitoring, ...

  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${var.region}.${each.key}"
  vpc_endpoint_type   = "Interface"             # ENI en subredes privadas + SG de 443
  subnet_ids          = var.private_subnet_ids
  security_group_ids  = [aws_security_group.endpoints.id]
  private_dns_enabled = var.private_dns_enabled
}
```

### 11.3 SAGA: pasos, compensaciones y orden inverso

`services/graphql-gateway/app/saga/steps.py` (cada paso con su compensación):

```python
STEPS: tuple[Step, ...] = (
    Step(StepName.RESERVE_CONNECTOR, SagaStatus.RESERVED, _reserve, _release),
    Step(StepName.CHARGE_WALLET, SagaStatus.CHARGED, _charge, _refund),
    Step(StepName.START_CHARGING, SagaStatus.COMPLETED, _start, _stop),
)
```

La flag de falla viaja al servicio de despacho (mismo archivo):

```python
async def _start(r: SagaRecord, c: Clients) -> Any:
    fault = r.flags.get(Flag.SIMULATE_CHARGER_HARDWARE_FAULT.value, False)
    return await c.dispatch.start(
        r.saga_id, r.station_id, r.connector_id, r.vehicle_id, r.power_kw, fault
    )
```

`services/graphql-gateway/app/saga/orchestrator.py`:

```python
    async def _run(self, record: SagaRecord) -> None:
        attempted: list[Step] = []
        for step in self._steps:
            attempted.append(step)
            try:
                await step.action(record, self._clients)
            except DownstreamError as err:
                self._note(record, step, "do", "error", f"{err.status} {err.code}")
                record.error_code, record.error_message = err.code, err.message
                await self._compensate(record, attempted)
                return
            self._note(record, step, "do", "ok")
            record.status = step.done_status
            await self._save(record)  # cada transición queda en la bitácora

    async def _compensate(self, record: SagaRecord, attempted: list[Step]) -> None:
        """Deshace TODO lo intentado (incluido el paso que falló: pudo aplicarse
        antes de un timeout). Es seguro porque cada compensación es idempotente."""
        record.status = SagaStatus.COMPENSATING
        await self._save(record)
        all_ok = True
        for step in reversed(attempted):  # ORDEN INVERSO
            try:
                await step.compensation(record, self._clients)
            except DownstreamError as err:
                all_ok = False
                self._note(record, step, "compensate", "error", f"{err.status} {err.code}")
            else:
                self._note(record, step, "compensate", "ok")
        record.status = SagaStatus.COMPENSATED if all_ok else SagaStatus.FAILED
        await self._save(record)
```

Idempotencia de la saga completa (mismo archivo, `start_charge`):

```python
        if data.saga_id:
            existing = await self._repo.get(data.saga_id)
            if existing:
                return existing  # mismo saga_id = misma saga, no se repite nada
```

### 11.4 Idempotencia del cobro y del reembolso (pregunta 6.3)

`services/billing-wallet-service/app/repository.py`: descuento y registro del cobro en UNA
transacción; la clave `sk = TX#<saga_id>#CHARGE` solo se puede escribir una vez:

```python
            self._client.transact_write_items(
                TransactItems=[
                    {
                        "Update": {
                            "TableName": self._name,
                            "Key": {"account_id": req.account_id, "sk": WALLET_SK},
                            "UpdateExpression": (
                                "SET balance_cents = balance_cents - :amt, updated_at = :now"
                            ),
                            "ConditionExpression": (
                                "attribute_exists(account_id) AND balance_cents >= :amt"
                            ),
                            "ExpressionAttributeValues": {":amt": req.amount_cents, ":now": now},
                        }
                    },
                    {
                        "Put": {
                            "TableName": self._name,
                            "Item": tx_item,
                            "ConditionExpression": "attribute_not_exists(sk)",
                        }
                    },
                ]
            )
```

Reembolso: devuelve EXACTAMENTE lo cobrado, una sola vez:

```python
    def refund(self, req: RefundRequest) -> RefundResult:
        """Compensación idempotente. Devuelve EXACTAMENTE lo cobrado, una sola vez."""
        charge = self.get_tx(req.account_id, req.saga_id, TxType.CHARGE)
        if charge is None:
            return RefundResult(saga_id=req.saga_id, refunded=False)  # nada que devolver
        if self.get_tx(req.account_id, req.saga_id, TxType.REFUND):
            return RefundResult(
                saga_id=req.saga_id, refunded=False, amount_cents=charge.amount_cents
            )
        # ... Put del REFUND con attribute_not_exists(sk) + suma al saldo, en una transacción
```

### 11.5 Feature flags: tabla por ambiente, caché 5 s, token

`services/graphql-gateway/app/flags.py`:

```python
# Flag ausente en la tabla = apagada (el comportamiento seguro por defecto).
DEFAULTS: dict[Flag, bool] = dict.fromkeys(Flag, False)

    async def all(self) -> dict[Flag, bool]:
        fresh = self._cache is not None and self._clock() - self._loaded_at < self._ttl_s
        if not fresh:
            # boto3 bloquea: se ejecuta en un hilo para no congelar el event loop.
            self._cache = await anyio.to_thread.run_sync(self._load)
            self._loaded_at = self._clock()
        return dict(self._cache)

    async def set(self, flag: Flag, enabled: bool, *, updated_by: str) -> None:
        item = {
            "flag_name": flag.value,
            "enabled": enabled,
            "updated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "updated_by": updated_by,
        }
        await anyio.to_thread.run_sync(lambda: self._table.put_item(Item=item))
        self._cache = None  # esta réplica lo ve al instante; las demás en <= ttl_s
```

`services/graphql-gateway/app/security.py` (cambiar una flag exige el token del ambiente):

```python
def require_admin(headers: Mapping[str, str], settings: GatewaySettings) -> str:
    """Valida el header x-admin-token. compare_digest: tiempo constante (sin timing attack)."""
    expected = settings.admin_token
    received = headers.get("x-admin-token", "")
    if expected is None or not hmac.compare_digest(
        received.encode(), expected.get_secret_value().encode()
    ):
        raise PublicError("FORBIDDEN", "Se requiere un token de administración válido")
    return "admin"
```

`services/graphql-gateway/app/main.py` (prod sin consola GraphiQL):

```python
        graphql_ide=None if settings.env == "prod" else "graphiql",
```

### 11.6 Canary: reparto 80/20 en el Ingress y decisión con métricas

`k8s/base/ingress.yaml` (segundo Ingress marcado como canary, peso inicial 0):

```yaml
kind: Ingress
metadata:
  name: graphql-gateway-canary
  annotations:
    nginx.ingress.kubernetes.io/canary: "true"
    nginx.ingress.kubernetes.io/canary-weight: "0"
    nginx.ingress.kubernetes.io/canary-by-header: x-canary
```

`scripts/canary.py`, anti-dilución (antes de tocar nada):

```python
    if stable_image.endswith(f":{args.tag}"):
        print(
            f"ABORTADO (inconcluso): el estable ya es {args.tag}; usa un tag NUEVO para el canary"
        )
        return 2
```

Métrica por VERSIÓN en CloudWatch (plan A; el plan B lee los logs, R5):

```python
def metric_sum(cw, namespace: str, name: str, version: str, since: datetime) -> float | None:
    resp = cw.get_metric_statistics(
        Namespace=namespace,
        MetricName=name,
        Dimensions=[
            {"Name": "Service", "Value": "graphql-gateway"},
            {"Name": "Version", "Value": version},
        ],
        StartTime=since,
        EndTime=datetime.now(UTC),
        Period=60,
        Statistics=["Sum"],
    )
    points = resp.get("Datapoints", [])
    return sum(p["Sum"] for p in points) if points else None
```

Los 4 pasos, fail-safe y decisión:

```python
    try:
        print(f"[1/4] Canary {args.tag} (chaos={args.chaos})")
        deploy_canary(kube, args.tag, args.chaos)

        print(f"[2/4] {args.weight}% del tráfico al canary")
        kube.set_weight(args.weight)
        time.sleep(3)  # ingress-nginx recarga la configuración

        print(f"[3/4] {args.traffic} peticiones por el Ingress")
        seen = generate_traffic(args.context, f"{args.env}.aegisvolt.local", args.traffic)
        # ...
        print("[4/4] Evaluación con datos del servidor")
        total, errors, source = evaluate(args.env, args.tag, since)
    except (Exception, SystemExit) as exc:  # noqa: BLE001
        print(f"ROLLBACK (inconcluso): el canary no se pudo evaluar ({exc})")
        rollback(kube)
        return 2
    rate = errors / total if total else 1.0

    if total < args.min_requests:
        print(f"ROLLBACK (inconcluso): solo {total} peticiones (< {args.min_requests})")
        rollback(kube)
        return 2
    if rate > args.max_error_rate:
        print(f"ROLLBACK: tasa de error {rate:.1%} > {args.max_error_rate:.0%}")
        rollback(kube)
        return 1
    print(f"PROMOCIÓN: {rate:.1%} <= {args.max_error_rate:.0%}; {args.tag} pasa a estable")
    promoted = promote(kube, args.tag)
```

Promoción con red y rollback:

```python
def promote(kube: Kube, tag: str) -> bool:
    kube.set_weight(100)  # todo el tráfico al canary (ya validado) mientras cambia el estable
    try:
        kube("set", "image", "deployment/graphql-gateway", f"app=aegisvolt/graphql-gateway:{tag}")
        kube("rollout", "status", "deployment/graphql-gateway", "--timeout=300s")
    except SystemExit as exc:
        print(f"PROMOCIÓN FALLIDA ({exc}): se revierte el estable a la versión anterior")
        kube("rollout", "undo", "deployment/graphql-gateway", check=False)
        rollback(kube)
        return False
    kube.set_weight(0)
    kube("scale", "deployment/graphql-gateway-canary", "--replicas=0")
    return True


def rollback(kube: Kube) -> None:
    # check=False: el rollback intenta TODO aunque un paso falle (nunca se queda a medias).
    kube(
        "annotate", "ingress/graphql-gateway-canary",
        "nginx.ingress.kubernetes.io/canary-weight=0", "--overwrite", check=False,
    )  # primero se corta el tráfico, después se apaga
    kube("scale", "deployment/graphql-gateway-canary", "--replicas=0", check=False)
```

### 11.7 CI/CD: rama = ambiente, apply, canary (pregunta 6.2)

`.github/workflows/deploy.yml` (resumido: se quitaron `shell:` y comentarios):

```yaml
on:
  push:
    branches: [dev, test, prod]

concurrency: # nunca dos despliegues del mismo ambiente a la vez (ni dos applies del mismo estado)
  group: deploy-${{ github.ref_name }}
  cancel-in-progress: false

jobs:
  deploy:
    name: deploy-${{ github.ref_name }}
    runs-on: [self-hosted, aegisvolt]
    environment: ${{ github.ref_name }} # historial de despliegues por ambiente en GitHub
    env:
      ENV_NAME: ${{ github.ref_name }} # DETECCIÓN DINÁMICA del target branch
    steps:
      - name: terraform apply (workspace ${{ env.ENV_NAME }})
        working-directory: infra/envs
        run: |
          terraform init -input=false -backend-config=backend-floci.hcl
          terraform workspace select "$ENV_NAME"
          terraform plan -input=false -lock-timeout=120s -var-file=floci.tfvars -out=plan.out
          terraform show -json plan.out > plan.json
          uv run --no-project python ../../scripts/plan_guard.py plan.json --workspace "$ENV_NAME"
          terraform apply -input=false -lock-timeout=120s plan.out

      - name: ¿Hay un gateway estable previo?
        id: prev
        run: |
          found=$(kubectl --context aegisvolt -n "aegisvolt-$ENV_NAME" \
            get deployment/graphql-gateway --ignore-not-found -o name)
          # vacío = primer despliegue: entra como estable, sin canary (::notice::)

      - name: Build + despliegue en minikube
        run: |
          only=()
          [[ "$ENV_NAME" == "dev" ]] || only=(--only graphql-gateway)
          uv run python scripts/deploy.py --env "$ENV_NAME" \
            --tag ${{ steps.ver.outputs.tag }} "${only[@]}"

      - name: Canary del gateway (20 % -> promoción o rollback automático)
        if: steps.prev.outputs.exists == 'true'
        run: >-
          uv run python scripts/canary.py --env "$ENV_NAME"
          --tag ${{ steps.ver.outputs.tag }} --weight 20 --chaos "$CHAOS"
```

`.github/workflows/pr-checks.yml`, `promote-guard` (solo dev -> test -> prod):

```bash
case "$BASE" in
  dev)  [[ "$HEAD" != "test" && "$HEAD" != "prod" ]] || bad=1 ;;
  test) [[ "$HEAD" == "dev" ]] || bad=1 ;;
  prod) [[ "$HEAD" == "test" ]] || bad=1 ;;
esac
if [[ -n "${bad:-}" ]]; then
  echo "BLOQUEADO: '$HEAD' -> '$BASE' rompe el orden dev -> test -> prod"; exit 1
fi
```

`.github/rulesets/protected-branches.json` (resumido; por qué el push da GH013):

```json
"rules": [
  { "type": "deletion" },
  { "type": "non_fast_forward" },
  { "type": "pull_request", "parameters": { "allowed_merge_methods": ["merge"] } },
  {
    "type": "required_status_checks",
    "parameters": {
      "strict_required_status_checks_policy": true,
      "required_status_checks": [
        { "context": "lint-build" }, { "context": "unit-tests" },
        { "context": "integration-tests" }, { "context": "e2e-tests" },
        { "context": "terraform-plan" }, { "context": "promote-guard" }
      ]
    }
  }
]
```

`non_fast_forward` bloquea el `--force`; `pull_request` bloquea el push directo; `deletion`
impide borrar la rama.

### 11.8 Observabilidad: correlation_id, versión y auditoría

`libs/aegis_common/src/aegis_common/middleware.py` (cada petición lleva su correlation_id y
cada respuesta dice qué versión la atendió; el log `http_request` alimenta el canary):

```python
        correlation_id = sanitize_id(headers.get("x-correlation-id"))
        # ...
        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                response_headers = MutableHeaders(scope=message)
                response_headers.append("x-correlation-id", correlation_id)
                if self.version:
                    response_headers.append("x-service-version", self.version)
            await send(message)
```

`services/graphql-gateway/app/clients.py` (el gateway propaga el id a los micros):

```python
        headers = {"x-correlation-id": get_correlation_id()}
        if saga_id:
            headers["x-saga-id"] = saga_id
```

`observability/prefect/audit_rules.py` (lo que la SAGA sola no puede ver):

```python
def is_orphan(saga: dict, now: datetime, max_age: timedelta) -> bool:
    if saga["status"] in TERMINAL:
        return False
    updated = datetime.fromisoformat(saga["updated_at"])
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=UTC)
    return now - updated > max_age


def inconsistency(saga: dict, fx: Effects) -> str | None:
    """Devuelve el motivo si los efectos no cuadran con el estado final, o None."""
    status = saga["status"]
    if status == "COMPLETED":
        if not fx.reservation_held:
            return "COMPLETED sin reserva del conector"
        if not fx.charged or fx.refunded:
            return "COMPLETED sin cobro vigente"
    if status == "COMPENSATED":
        if fx.reservation_held:
            return "COMPENSATED pero el conector sigue reservado"
        if fx.charged and not fx.refunded:
            return "COMPENSATED con cobro sin reembolso"
    return None
```

### 11.9 Frontend: el bug de hoy y los estados de carga

`frontend/src/api/operations.ts` (el tipo debe llamarse como en el esquema: `FlagName`):

```ts
export const M_SET_FLAG = `mutation($n: FlagName!, $e: Boolean!) { setFlag(name: $n, enabled: $e) { name enabled } }`;
```

`frontend/src/panels/Flags.tsx` (interruptor accesible, patrón Switch del W3C APG):

```tsx
<button
  type="button"
  role="switch"
  aria-checked={f.enabled}
  aria-busy={busy}
  className={`switch ${f.enabled ? "on" : ""}`}
  disabled={!token || pending !== null}
  onClick={() => toggle(f)}
>
```

## 12. Preguntas de código probables (para estudiar)

Respuesta corta + dónde está (abrir el bloque de §11 si piden verlo).

### SAGA y backend

- **¿Dónde se decide compensar?** `orchestrator.py::_run`: si un paso lanza `DownstreamError`
  se llama `_compensate(record, attempted)`. `attempted` incluye el paso que falló porque pudo
  aplicarse antes de un timeout; compensarlo es seguro porque cada compensación es idempotente.
- **¿Por qué `reversed(attempted)`?** Deshacer en orden inverso respeta las dependencias: no se
  libera el conector mientras haya un cobro vivo asociado a esa reserva.
- **¿Qué pasa si falla una compensación?** La saga queda `FAILED` (no COMPENSATED), se loguea en
  ERROR y la auditoría de Prefect la reporta: requiere revisión humana.
- **¿Cómo se ve la idempotencia en el cobro?** `transact_write_items` con dos operaciones
  atómicas: descontar saldo (condición `balance_cents >= :amt`) y crear `TX#<saga>#CHARGE`
  (condición `attribute_not_exists(sk)`). Si llega dos veces, la condición cancela la
  transacción y `_after_failed_charge` devuelve el cobro existente. Visto en vivo el 22-nov:
  3 reintentos del gateway -> 1 CHARGE + 1 REFUND.
- **¿Y si llega el reembolso dos veces?** `refund` primero busca el REFUND; si existe, devuelve
  `refunded=False` sin tocar el saldo. El Put del REFUND también tiene `attribute_not_exists(sk)`
  por si dos réplicas compiten.
- **¿Fondos insuficientes (paso 2)?** La condición `balance_cents >= :amt` falla ->
  `InsufficientFundsError` -> el gateway compensa SOLO la reserva. Probar: cuenta `acc-pobre`
  (saldo 1,00) en el frontend.
- **¿Quién genera el saga_id y por qué?** El navegador (UUID v4): es la llave de idempotencia de
  toda la saga (`start_charge` devuelve la existente si el id ya está) y permite suscribirse
  antes de que termine. En HTTP se usa `getRandomValues` porque `randomUUID` exige contexto
  seguro (bug real del 22-nov).
- **¿Timeouts y reintentos?** `clients.py`: httpx con `HTTP_TIMEOUT_S` (20 s en el manifiesto) y
  2 reintentos solo en errores de transporte; seguros por la idempotencia.
- **¿Cómo se calcula precio/potencia?** `steps.py::quote`: 80 centavos/kWh, x1,5 con
  `ENABLE_DYNAMIC_SURGE_PRICING`; 150 kW con `ENABLE_FAST_CHARGE_BOOST`, si no 50 kW. Las flags se
  congelan en el registro de la saga al iniciarla (`record.flags`): un cambio a mitad no la
  vuelve inconsistente.
- **¿Por qué el estado de la saga se guarda en cada paso?** `_save` después de cada transición:
  si el gateway muere, la bitácora dice hasta dónde llegó (huérfana detectable).

### GraphQL

- **¿Queries, mutations y subscriptions?** `schema.py`: `connectors`, `flags`, `wallet`, `saga`,
  `sagas`; `startCharge`, `setFlag`; `stationUpdates`, `featureFlagsChanged`, `sagaUpdates`.
- **¿Cómo funcionan las suscripciones con varias réplicas?** `resolvers.py`: cada suscripción
  consulta DynamoDB cada `poll_interval_s` (1 s) y emite solo si cambió; sin pub/sub, así
  cualquier réplica sirve (decisión T7). Si el WebSocket cae, el frontend sondea.
- **¿Por qué `FlagName` como enum y no String?** El esquema rechaza nombres inválidos antes de
  ejecutar (validación). Fue el bug del panel: el frontend declaraba `Flag!`.
- **¿Errores?** `PublicError` con `extensions.code` (`FORBIDDEN`, `VALIDATION_ERROR`); nunca se
  filtra el stack al cliente.

### Feature flags

- **¿Por qué ausente = apagada?** `DEFAULTS = dict.fromkeys(Flag, False)`: lo seguro por defecto;
  por eso la tabla de prod vacía significa todo apagado.
- **¿Cuánto tarda en verse un cambio?** La réplica que escribe borra su caché (instantáneo); las
  demás en <= 5 s (`ttl_s`).
- **¿Por qué `hmac.compare_digest` para el token?** Comparación en tiempo constante: evita
  adivinar el token midiendo tiempos de respuesta.

### IaC

- **¿Dónde se usa `terraform.workspace`?** En `locals.tf` (sufijo de nombres) y en el backend
  `workspace_key_prefix = "env:"` -> `env:/<ws>/terraform.tfstate`.
- **¿Qué impide que `apply` de test toque prod?** Estado distinto por workspace + nombres con
  sufijo + `plan_guard.py` (falla si un `delete` no termina en `-<workspace>`) + `concurrency`
  por rama en el pipeline + lock del estado.
- **¿Por qué `prevent_destroy` en el bucket y la KMS?** Perderlos = perder el estado de todos
  los ambientes o no poder descifrarlo.
- **¿Por qué el health check del NLB es HTTP `/healthz`?** Confirma que NGINX responde, no solo
  que el puerto está abierto.
- **¿VPCE Gateway vs Interface?** Gateway (S3, DynamoDB): entrada en la tabla de rutas privada,
  sin costo por hora. Interface (CloudWatch Logs/Monitoring): ENI en subredes privadas con SG de
  443 y DNS privado.

### CI/CD y canary

- **¿Cómo sabe el pipeline el ambiente?** `ENV_NAME: ${{ github.ref_name }}` (rama del push que
  dejó el merge) -> `terraform workspace select "$ENV_NAME"`.
- **¿Por qué `concurrency` con `cancel-in-progress: false`?** Nunca dos applies del mismo estado
  a la vez, y no se cancela un despliegue a medias (quedaría inconsistente).
- **¿Por qué los checks requeridos no incluyen `security-scan`?** Es informativo; los 6
  requeridos son los que pide la guía (+ promote-guard).
- **¿Exit codes de `canary.py`?** 0 promovido; 1 falló (error > 5 %); 2 inconcluso (pocas
  peticiones o no se pudo medir) -> rollback igual. El job falla si no es 0.
- **¿Qué hace `promote` si el rollout del estable se cuelga?** `rollout undo` + peso 0 + canary
  a 0: nunca queda a medias.
- **¿Por qué la imagen lleva la versión adentro (ARG al final del Dockerfile)?** Imagen
  inmutable por tag; el ARG al final no invalida la caché de dependencias.
- **¿Por qué el primer despliegue no hace canary?** No hay versión anterior contra la cual
  comparar; `--ignore-not-found` distingue "no existe" de "API caída" (esta última falla).

### Observabilidad

- **¿Cómo llega el `correlation_id` a los 4 servicios?** Middleware ASGI (`aegis_common`) lo lee
  o genera, lo guarda en un `ContextVar` (cada log lo incluye) y el gateway lo reenvía en
  `x-correlation-id` a los micros (`clients.py`). Demostrar: `scripts/trace_saga.py`.
- **¿Por qué los probes no se loguean?** `_NOT_LOGGED = {"/healthz", "/readyz"}`: inflarían el
  conteo de peticiones del canary.
- **¿Qué es una huérfana para la auditoría?** Estado no terminal con `updated_at` más viejo que
  el umbral (5 min). Inconsistente: el estado final no cuadra con reservas/cobros.
- **¿Por qué la auditoría solo lee?** Corregir dinero automáticamente sin contexto es peligroso;
  la auditoría avisa (artifact + run en rojo) y decide una persona.
