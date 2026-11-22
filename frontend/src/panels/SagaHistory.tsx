import { useState } from "react";

import { gql } from "../api/graphql";
import { Q_SAGAS, type Saga } from "../api/operations";
import { usePolling } from "../hooks/usePolling";
import { SagaTimeline } from "./SagaTimeline";

const STATUSES = ["COMPLETED", "COMPENSATED", "FAILED", "STARTED"];

/** Panel 4: historial de sagas por estado (GSI by-status), con sondeo. */
export function SagaHistory() {
  const [status, setStatus] = useState(STATUSES[0]);
  const { data, error } = usePolling(
    async () => (await gql<{ sagas: Saga[] }>(Q_SAGAS, { st: status })).sagas,
    [status],
  );

  return (
    <section className="panel wide">
      <header>
        <h2>Historial de sagas</h2>
        <span className="badge polling">↻ sondeo</span>
      </header>
      <div className="tabs">
        {STATUSES.map((s) => (
          <button key={s} className={s === status ? "active" : ""} onClick={() => setStatus(s)}>
            {s}
          </button>
        ))}
      </div>
      {error && <p className="error">{error}</p>}
      {data?.length === 0 && <p className="note">Sin sagas en {status}.</p>}
      <div className="history">
        {(data ?? []).map((s) => (
          <SagaTimeline key={s.sagaId} saga={s} />
        ))}
      </div>
    </section>
  );
}
