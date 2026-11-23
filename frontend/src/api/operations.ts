// Operaciones GraphQL de la UI (Strawberry expone los campos en camelCase).

export interface Connector {
  stationId: string;
  connectorId: string;
  powerKw: number;
  status: string;
  sagaId: string | null;
}

export interface Flag {
  name: string;
  enabled: boolean;
}

export interface StepEvent {
  step: string;
  action: string;
  outcome: string;
  at: string;
  detail: string | null;
}

export interface Saga {
  sagaId: string;
  status: string;
  stationId: string;
  connectorId: string;
  accountId: string;
  energyKwh: number;
  amountCents: number;
  powerKw: number;
  errorCode: string | null;
  errorMessage: string | null;
  updatedAt: string;
  history: StepEvent[];
}

const CONNECTOR = "stationId connectorId powerKw status sagaId";
const SAGA = `sagaId status stationId connectorId accountId energyKwh amountCents powerKw
  errorCode errorMessage updatedAt history { step action outcome at detail }`;

export const Q_CONNECTORS = `query($s: String!) { connectors(stationId: $s) { ${CONNECTOR} } }`;
export const S_STATION = `subscription($s: String!) { stationUpdates(stationId: $s) { ${CONNECTOR} } }`;

export const Q_FLAGS = `{ flags { name enabled } }`;
export const S_FLAGS = `subscription { featureFlagsChanged { name enabled } }`;
export const M_SET_FLAG = `mutation($n: FlagName!, $e: Boolean!) { setFlag(name: $n, enabled: $e) { name enabled } }`;

export const Q_WALLET = `query($a: String!) { wallet(accountId: $a) { accountId balanceCents } }`;

export const M_START = `mutation($i: StartChargeInput!) { startCharge(input: $i) { ${SAGA} } }`;
export const Q_SAGA = `query($id: ID!) { saga(sagaId: $id) { ${SAGA} } }`;
export const S_SAGA = `subscription($id: ID!) { sagaUpdates(sagaId: $id) { ${SAGA} } }`;
export const Q_SAGAS = `query($st: SagaStatus!) { sagas(status: $st, limit: 10) { ${SAGA} } }`;
