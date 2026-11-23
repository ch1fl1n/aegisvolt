import { gql } from "../api/graphql";
import { type Connector, Q_CONNECTORS, S_STATION } from "../api/operations";
import { useLive } from "../hooks/useLive";
import { LiveBadge } from "./LiveBadge";
import { Skeleton } from "./Skeleton";

export const STATIONS = ["st-norte", "st-centro", "st-sur"];

/** Panel 1: conectores de una estación en tiempo real (libre / reservado). */
export function Stations({
  station,
  onStation,
}: {
  station: string;
  onStation: (s: string) => void;
}) {
  const { data, error, mode } = useLive<{ stationUpdates: Connector[] }, Connector[]>({
    subscription: S_STATION,
    variables: { s: station },
    pick: (d) => d.stationUpdates,
    poll: async () => (await gql<{ connectors: Connector[] }>(Q_CONNECTORS, { s: station })).connectors,
    key: station,
  });

  return (
    <section className="panel">
      <header>
        <h2>Estaciones</h2>
        <LiveBadge mode={mode} />
      </header>
      <div className="tabs">
        {STATIONS.map((s) => (
          <button key={s} className={s === station ? "active" : ""} onClick={() => onStation(s)}>
            {s}
          </button>
        ))}
      </div>
      {error && <p className="error">{error}</p>}
      {!data && !error && <Skeleton rows={2} height={42} />}
      <ul className="connectors">
        {(data ?? []).map((c) => (
          <li key={c.connectorId} className={`connector ${c.status.toLowerCase()}`}>
            <strong>{c.connectorId}</strong>
            <span>{c.powerKw} kW</span>
            <span className="status">{c.status}</span>
            {c.sagaId && <code title="saga que lo reservó">{c.sagaId.slice(0, 8)}</code>}
          </li>
        ))}
      </ul>
    </section>
  );
}
