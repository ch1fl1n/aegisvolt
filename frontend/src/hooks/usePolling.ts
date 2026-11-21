import { useEffect, useRef, useState } from "react";

import { config } from "../config";

/** Llama a `fetcher` cada `intervalMs` mientras el componente esté montado y `enabled`. */
export function usePolling<T>(
  fetcher: () => Promise<T>,
  deps: unknown[],
  enabled = true,
  intervalMs = config.pollMs,
) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const saved = useRef(fetcher);
  saved.current = fetcher;

  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    const tick = async () => {
      try {
        const value = await saved.current();
        if (alive) {
          setData(value);
          setError(null);
        }
      } catch (err) {
        if (alive) setError(err instanceof Error ? err.message : String(err));
      }
    };
    void tick();
    const id = setInterval(tick, intervalMs);
    return () => {
      alive = false;
      clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, intervalMs, ...deps]);

  return { data, error, setData };
}
