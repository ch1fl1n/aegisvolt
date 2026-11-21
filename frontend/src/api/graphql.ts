import { createClient, type Client } from "graphql-ws";

import { httpUrl, wsUrl } from "../config";

export class GraphQLError extends Error {
  constructor(
    message: string,
    public code?: string,
  ) {
    super(message);
  }
}

interface GqlResponse<T> {
  data?: T;
  errors?: { message: string; extensions?: { code?: string } }[];
}

/** Query o mutación por HTTP POST (nunca GET: las consultas no van en la URL). */
export async function gql<T>(
  query: string,
  variables: Record<string, unknown> = {},
  headers: Record<string, string> = {},
): Promise<T> {
  const resp = await fetch(httpUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify({ query, variables }),
  });
  if (!resp.ok && resp.status !== 400) throw new GraphQLError(`HTTP ${resp.status}`);
  const body = (await resp.json()) as GqlResponse<T>;
  if (body.errors?.length) {
    const first = body.errors[0];
    throw new GraphQLError(first.message, first.extensions?.code);
  }
  return body.data as T;
}

// Un solo WebSocket para todas las suscripciones (protocolo graphql-transport-ws).
let wsClient: Client | null = null;
export function ws(): Client {
  wsClient ??= createClient({ url: wsUrl, retryAttempts: 5, lazy: true });
  return wsClient;
}

/** Suscripción GraphQL. Devuelve la función para cancelarla. */
export function subscribe<T>(
  query: string,
  variables: Record<string, unknown>,
  onData: (data: T) => void,
  onError: (err: unknown) => void,
): () => void {
  return ws().subscribe<T>(
    { query, variables },
    {
      next: (msg) => msg.data && onData(msg.data as T),
      error: onError,
      complete: () => undefined,
    },
  );
}
