import { useState } from "react";

import { config } from "./config";
import { Flags } from "./panels/Flags";
import { SagaHistory } from "./panels/SagaHistory";
import { StartCharge } from "./panels/StartCharge";
import { STATIONS, Stations } from "./panels/Stations";

export function App() {
  const [station, setStation] = useState(STATIONS[0]);
  return (
    <>
      <header className={`top env-${config.env}`}>
        <h1>⚡ AegisVolt</h1>
        <span className="env">{config.env.toUpperCase()}</span>
      </header>
      <main className="grid">
        <Stations station={station} onStation={setStation} />
        <StartCharge station={station} />
        <Flags />
        <SagaHistory />
      </main>
    </>
  );
}
