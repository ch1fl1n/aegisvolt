export interface AegisConfig {
  env: "dev" | "test" | "prod";
  graphqlPath: string;
  pollMs: number;
}

declare global {
  interface Window {
    AEGIS_CONFIG?: Partial<AegisConfig>;
  }
}

// Se lee en tiempo de EJECUCIÓN (public/config.js), no en build: la misma imagen sirve a
// dev, test y prod. Nada secreto vive aquí (el navegador lo ve todo).
export const config: AegisConfig = {
  env: "dev",
  graphqlPath: "/graphql",
  pollMs: 2500,
  ...window.AEGIS_CONFIG,
};

export const httpUrl = config.graphqlPath;
export const wsUrl = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}${config.graphqlPath}`;
