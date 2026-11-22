# syntax=docker/dockerfile:1
# graphql-gateway — contexto de build: RAÍZ del repo (necesita libs/aegis_common).
#   docker build -f services/graphql-gateway/Dockerfile -t aegisvolt/graphql-gateway:v1 .

# ---------- etapa 1: dependencias en un venv (con herramientas de build) ----------
FROM python:3.12-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
COPY services/graphql-gateway/requirements.txt /tmp/requirements.txt
COPY libs/aegis_common /tmp/aegis_common
RUN /opt/venv/bin/pip install -r /tmp/requirements.txt /tmp/aegis_common

# ---------- etapa 2: imagen final mínima, sin compiladores ni pip cache ----------
FROM python:3.12-slim
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SERVICE_NAME=graphql-gateway
# Usuario sin privilegios con UID fijo (Pod Security "restricted" exige runAsNonRoot).
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app
COPY --from=build /opt/venv /opt/venv
WORKDIR /srv
COPY --chown=root:root services/graphql-gateway/app ./app
# La versión viaja DENTRO de la imagen (--build-arg SERVICE_VERSION=<tag>). Va al FINAL:
# cambia en cada deploy y todo lo de abajo de un ARG pierde la caché (doc de Docker).
ARG SERVICE_VERSION=v1
ENV SERVICE_VERSION=${SERVICE_VERSION}
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status == 200 else 1)"]
CMD ["uvicorn", "app.main:build", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--proxy-headers"]
