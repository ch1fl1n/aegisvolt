import { useState } from "react";

import { gql } from "../api/graphql";
import { type Flag, M_SET_FLAG, Q_FLAGS, S_FLAGS } from "../api/operations";
import { config } from "../config";
import { useLive } from "../hooks/useLive";
import { LiveBadge } from "./LiveBadge";

const HELP: Record<string, string> = {
  ENABLE_DYNAMIC_SURGE_PRICING: "Precio dinámico por demanda",
  ENABLE_FAST_CHARGE_BOOST: "Más potencia en la carga",
  SIMULATE_CHARGER_HARDWARE_FAULT: "Falla el cargador → la saga compensa",
};

/**
 * Panel 3: feature flags del ambiente. Cambian en vivo (suscripción) y cada ambiente tiene
 * SU tabla: cambiar dev no toca prod. El token de admin NO se guarda: se pide y vive en memoria.
 */
export function Flags() {
  const [token, setToken] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const { data, error, mode } = useLive<{ featureFlagsChanged: Flag[] }, Flag[]>({
    subscription: S_FLAGS,
    variables: {},
    pick: (d) => d.featureFlagsChanged,
    poll: async () => (await gql<{ flags: Flag[] }>(Q_FLAGS)).flags,
    key: "flags",
  });

  async function toggle(flag: Flag) {
    setMsg(null);
    try {
      await gql(M_SET_FLAG, { n: flag.name, e: !flag.enabled }, { "x-admin-token": token });
      setMsg(`${flag.name} → ${!flag.enabled ? "ON" : "OFF"}`);
    } catch (err) {
      setMsg(err instanceof Error ? err.message : String(err));
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
      <ul className="flags">
        {(data ?? []).map((f) => (
          <li key={f.name}>
            <label>
              <input type="checkbox" checked={f.enabled} disabled={!token} onChange={() => toggle(f)} />
              <code>{f.name}</code>
            </label>
            <small>{HELP[f.name] ?? ""}</small>
          </li>
        ))}
      </ul>
      <input
        type="password"
        placeholder="x-admin-token para cambiar flags"
        value={token}
        onChange={(e) => setToken(e.target.value)}
        autoComplete="off"
      />
      {msg && <p className="note">{msg}</p>}
    </section>
  );
}
