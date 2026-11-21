import type { Saga } from "../api/operations";

/** Pasos de una saga: hacia adelante (do) y, si falló algo, las compensaciones en reversa. */
export function SagaTimeline({ saga }: { saga: Saga }) {
  return (
    <div className="saga">
      <p>
        <code>{saga.sagaId.slice(0, 8)}</code> <span className={`status ${saga.status.toLowerCase()}`}>{saga.status}</span>{" "}
        {(saga.amountCents / 100).toFixed(2)} · {saga.powerKw} kW
      </p>
      {saga.errorCode && (
        <p className="error">
          {saga.errorCode}: {saga.errorMessage}
        </p>
      )}
      <ol>
        {saga.history.map((h, i) => (
          <li key={i} className={`${h.action} ${h.outcome}`}>
            {h.action === "compensate" ? "↩" : "→"} {h.step} · {h.outcome}
            {h.detail && <small> ({h.detail})</small>}
          </li>
        ))}
      </ol>
    </div>
  );
}
