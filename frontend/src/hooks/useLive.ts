import { useEffect, useState } from "react";

import { subscribe } from "../api/graphql";
import { usePolling } from "./usePolling";

export type LiveMode = "wss" | "polling";

/**
 * Tiempo real con respaldo (T7):
 *   1. Intenta la suscripción GraphQL por WebSocket (WSS detrás del Ingress).
 *   2. Si el WebSocket falla (proxy que no lo deja pasar, red), cae a sondeo HTTP.
 * La UI muestra en qué modo está, para que se vea en la demo.
 */
export function useLive<S, T>(opts: {
  subscription: string;
  variables: Record<string, unknown>;
  pick: (data: S) => T;
  poll: () => Promise<T>;
  key: string;
  enabled?: boolean;
}) {
  const { subscription, variables, pick, poll, key, enabled = true } = opts;
  const [mode, setMode] = useState<LiveMode>("wss");
  const [live, setLive] = useState<T | null>(null);

  useEffect(() => {
    if (!enabled) return;
    setMode("wss");
    setLive(null);
    const stop = subscribe<S>(
      subscription,
      variables,
      (data) => setLive(pick(data)),
      () => setMode("polling"),
    );
    return stop;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, enabled]);

  // Primera carga inmediata por HTTP y, si no hay WSS, sondeo continuo.
  const polled = usePolling(poll, [key], enabled && (mode === "polling" || live === null));
  return { data: live ?? polled.data, error: polled.error, mode };
}
