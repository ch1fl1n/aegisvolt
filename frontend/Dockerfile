# syntax=docker/dockerfile:1
# Frontend: build con Node, se sirve con nginx SIN root. Contexto: frontend/
#   docker build -t aegisvolt/frontend:v1 frontend

# ---------- etapa 1: build de Vite ----------
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

# ---------- etapa 2: nginx sin privilegios (puerto 8080, UID 101) ----------
FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
COPY --chmod=755 docker-entrypoint.sh /docker-entrypoint.d/40-aegis-config.sh
USER 101
EXPOSE 8080
