import { useState } from "react";

import { gql } from "../api/graphql";
import { type Flag, M_SET_FLAG, Q_FLAGS, S_FLAGS } from "../api/operations";
import { config } from "../config";
import { useLive } from "../hooks/useLive";
import { LiveBadge } from "./LiveBadge";
import { Skeleton } from "./Skeleton";

const HELP: Record<string, string> = {
  ENABLE_DYNAMIC_SURGE_PRICING: "Precio dinámico por demanda",
  ENABLE_FAST_CHARGE_BOOST: "Más potencia en la carga",
  SIMULATE_CHARGER_HARDWARE_FAULT: "Falla el cargador → la saga compensa",
};

/**
 * Panel 3: feature flags del ambiente. Cambian en vivo (suscripción) y cada ambiente tiene
 * SU tabla: cambiar dev no toca prod. El token de admin NO se guarda: se pide y vive en memoria.
 * Interruptores con role="switch" + aria-checked (patrón Switch del W3C APG).
 */
export function Flags() {
  const [token, setToken] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const { data, error, mode } = useLive<{ featureFlagsChanged: Flag[] }, Flag[]>({
    subscription: S_FLAGS,
    variables: {},
    pick: (d) => d.featureFlagsChanged,
    poll: async () => (await gql<{ flags: Flag[] }>(Q_FLAGS)).flags,
    key: "flags",
  });

  async function toggle(flag: Flag) {
    setMsg(null);
    setPending(flag.name);
    try {
      await gql(M_SET_FLAG, { n: flag.name, e: !flag.enabled }, { "x-admin-token": token });
      setMsg({ ok: true, text: `${flag.name} → ${!flag.enabled ? "ON" : "OFF"}` });
    } catch (err) {
      setMsg({ ok: false, text: err instanceof Error ? err.message : String(err) });
    } finally {
      setPending(null);
    }
  }

  return (
    <section className="panel">
      <header>
        <h2>
          Feature flags <small>({config.env})</small>
        </h2>
        <LiveBadge mode={mode} />
      </header>
      {error && <p className="error">{error}</p>}
      {!data && !error ? (
        <Skeleton rows={3} height={44} />
      ) : (
        <ul className="flags">
          {(data ?? []).map((f) => {
            const busy = pending === f.name;
            return (
              <li key={f.name}>
                <button
                  type="button"
                  role="switch"
                  aria-checked={f.enabled}
                  aria-busy={busy}
                  className={`switch ${f.enabled ? "on" : ""}`}
                  disabled={!token || pending !== null}
                  onClick={() => toggle(f)}
                  title={token ? "Cambiar" : "Pega el token para cambiar"}
                >
                  <span className="track" aria-hidden="true">
                    <span className="thumb">{busy && <span className="spinner small" />}</span>
                  </span>
                  <code>{f.name}</code>
                  <span className={`badge ${f.enabled ? "on" : "off"}`} aria-hidden="true">
                    {f.enabled ? "ON" : "OFF"}
                  </span>
                </button>
                <small>{HELP[f.name] ?? ""}</small>
              </li>
            );
          })}
        </ul>
      )}
      <input
        type="password"
        placeholder="x-admin-token para cambiar flags"
        aria-label="Token de administración"
        value={token}
        onChange={(e) => setToken(e.target.value)}
        autoComplete="off"
      />
      {!token && <p className="note">Pega el token para habilitar los interruptores.</p>}
      <p className={msg ? (msg.ok ? "note ok" : "error") : "note"} aria-live="polite">
        {msg?.text}
      </p>
    </section>
  );
}
