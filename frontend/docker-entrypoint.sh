#!/bin/sh
# Lo ejecuta la imagen de nginx al arrancar (/docker-entrypoint.d/). Escribe config.js con las
# variables del ambiente: UNA imagen sirve a dev, test y prod (12-factor).
# Con readOnlyRootFilesystem, /usr/share/nginx/html/runtime es un emptyDir escribible.
set -eu
case "${AEGIS_ENV:-dev}" in dev|test|prod) ;; *) echo "AEGIS_ENV inválido"; exit 1 ;; esac
case "${POLL_MS:-2500}" in *[!0-9]*) echo "POLL_MS inválido"; exit 1 ;; esac

mkdir -p /usr/share/nginx/html/runtime
cat > /usr/share/nginx/html/runtime/config.js <<EOF
window.AEGIS_CONFIG = { env: "${AEGIS_ENV:-dev}", graphqlPath: "/graphql", pollMs: ${POLL_MS:-2500} };
EOF
