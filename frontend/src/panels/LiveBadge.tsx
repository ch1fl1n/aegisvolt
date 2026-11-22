import type { LiveMode } from "../hooks/useLive";

/** Muestra si el panel recibe datos por WebSocket o por sondeo (respaldo). */
export function LiveBadge({ mode }: { mode: LiveMode }) {
  return (
    <span className={`badge ${mode}`} title="Canal de actualización">
      {mode === "wss" ? "● en vivo (WSS)" : "↻ sondeo"}
    </span>
  );
}
