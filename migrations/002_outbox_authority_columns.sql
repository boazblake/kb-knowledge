ALTER TABLE ingestion_outbox ADD COLUMN IF NOT EXISTS tenant text NOT NULL DEFAULT '';
ALTER TABLE ingestion_outbox ADD COLUMN IF NOT EXISTS workload text NOT NULL DEFAULT '';
ALTER TABLE ingestion_outbox ADD COLUMN IF NOT EXISTS lease_owner text;
ALTER TABLE ingestion_outbox ADD COLUMN IF NOT EXISTS lease_expires_at timestamptz;
ALTER TABLE ingestion_idempotency ADD COLUMN IF NOT EXISTS fingerprint text NOT NULL DEFAULT '';
