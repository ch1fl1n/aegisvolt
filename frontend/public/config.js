// Valores para desarrollo local. En el contenedor, docker-entrypoint.sh REESCRIBE este archivo
// con las variables de entorno del Deployment (AEGIS_ENV, GRAPHQL_PATH, POLL_MS).
window.AEGIS_CONFIG = {
  env: "dev",
  graphqlPath: "/graphql",
  pollMs: 2500,
};
