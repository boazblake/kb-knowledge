CREATE TABLE IF NOT EXISTS purge_intents (
  purge_id text PRIMARY KEY, idempotency_key text UNIQUE NOT NULL, target text NOT NULL,
  actor text NOT NULL, correlation_id text NOT NULL, data_class text NOT NULL,
  retain_until timestamptz, legal_hold boolean NOT NULL DEFAULT false,
  status text NOT NULL DEFAULT 'pending', created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS purge_receipts (
  purge_id text NOT NULL REFERENCES purge_intents(purge_id), store text NOT NULL,
  status text NOT NULL, detail text NOT NULL DEFAULT '', correlation_id text NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(purge_id, store)
);
CREATE INDEX IF NOT EXISTS purge_receipts_status_idx ON purge_receipts(status);
CREATE TABLE IF NOT EXISTS purge_tombstones (
  purge_id text NOT NULL REFERENCES purge_intents(purge_id), object_key text PRIMARY KEY,
  actor text NOT NULL, correlation_id text NOT NULL, recorded_at timestamptz NOT NULL DEFAULT now()
);
