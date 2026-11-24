import { useState } from "react";

import { gql } from "../api/graphql";
import { M_START, Q_SAGA, Q_WALLET, type Saga, S_SAGA } from "../api/operations";
import { useLive } from "../hooks/useLive";
import { usePolling } from "../hooks/usePolling";
import { LiveBadge } from "./LiveBadge";
import { SagaTimeline } from "./SagaTimeline";
import { Skeleton } from "./Skeleton";

const ACCOUNTS = ["acc-demo", "acc-pobre"];

/**
 * UUID v4 para el saga_id. crypto.randomUUID() solo existe en contextos seguros (HTTPS o
 * localhost; MDN) y la demo entra por http://dev.aegisvolt.local: sin este respaldo el clic
 * fallaba en silencio. getRandomValues() sí está disponible en HTTP.
 */
function newSagaId(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40; // versión 4
  b[8] = (b[8] & 0x3f) | 0x80; // variante RFC 4122
  const h = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

/**
 * Panel 2: iniciar una carga = lanzar la SAGA (reservar → cobrar → arrancar).
 * El saga_id lo genera el navegador: sirve de llave de idempotencia (un doble clic o un
 * reintento NO crea dos cobros) y permite suscribirse antes de que la saga termine.
 */
export function StartCharge({ station }: { station: string }) {
  const [connector, setConnector] = useState("c1");
  const [account, setAccount] = useState(ACCOUNTS[0]);
  const [kwh, setKwh] = useState(20);
  const [sagaId, setSagaId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const wallet = usePolling(
    async () =>
      (await gql<{ wallet: { balanceCents: number } }>(Q_WALLET, { a: account })).wallet,
    [account],
  );

  const live = useLive<{ sagaUpdates: Saga }, Saga | null>({
    subscription: S_SAGA,
    variables: { id: sagaId },
    pick: (d) => d.sagaUpdates,
    poll: async () => (await gql<{ saga: Saga | null }>(Q_SAGA, { id: sagaId })).saga,
    key: sagaId ?? "none",
    enabled: sagaId !== null,
  });

  async function start() {
    setError(null);
    setBusy(true);
    try {
      const id = newSagaId(); // dentro del try: cualquier fallo se muestra, nunca es silencioso
      setSagaId(id);
      await gql(M_START, {
        i: {
          sagaId: id,
          stationId: station,
          connectorId: connector,
          vehicleId: "ev-demo-1",
          accountId: account,
          energyKwh: kwh,
        },
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err)); // la saga compensó o falló
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <header>
        <h2>Iniciar carga</h2>
        {sagaId && <LiveBadge mode={live.mode} />}
      </header>
      <div className="form">
        <label>
          Estación <input value={station} readOnly />
        </label>
        <label>
          Conector <input value={connector} onChange={(e) => setConnector(e.target.value)} />
        </label>
        <label>
          Cuenta
          <select value={account} onChange={(e) => setAccount(e.target.value)}>
            {ACCOUNTS.map((a) => (
              <option key={a}>{a}</option>
            ))}
          </select>
        </label>
        <label>
          kWh <input type="number" min={1} max={200} value={kwh} onChange={(e) => setKwh(+e.target.value)} />
        </label>
        <p className="note">
          Saldo:{" "}
          {wallet.data ? (
            (wallet.data.balanceCents / 100).toFixed(2)
          ) : (
            <span className="skeleton inline" aria-label="Cargando saldo" />
          )}
        </p>
        <button onClick={start} disabled={busy} aria-busy={busy} className="primary">
          {busy && <span className="spinner" aria-hidden="true" />}
          {busy ? "Procesando saga…" : "Iniciar carga"}
        </button>
      </div>
      <div aria-live="polite">
        {error && <p className="error">{error}</p>}
        {busy && !live.data && <Skeleton rows={3} height={18} />}
        {live.data && <SagaTimeline saga={live.data} />}
      </div>
    </section>
  );
}
