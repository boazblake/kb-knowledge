CREATE TABLE IF NOT EXISTS ingestion_raw_objects (
  uri text PRIMARY KEY, provider text NOT NULL, tenant text NOT NULL,
  connector text NOT NULL, source_instance text NOT NULL, object_id text NOT NULL,
  revision text NOT NULL, content_hash text NOT NULL,
  status text NOT NULL DEFAULT 'staged', staged_at timestamptz NOT NULL DEFAULT now(),
  committed_at timestamptz, orphaned_at timestamptz, last_error text
);
CREATE INDEX IF NOT EXISTS ingestion_raw_orphan_idx ON ingestion_raw_objects(status, staged_at, tenant);
ALTER TABLE ingestion_outbox ADD COLUMN IF NOT EXISTS last_error text;
ALTER TABLE ingestion_outbox ADD COLUMN IF NOT EXISTS retry_at timestamptz;
ALTER TABLE ingestion_outbox ADD COLUMN IF NOT EXISTS last_retry_delay_seconds integer;
ALTER TABLE ingestion_outbox ADD COLUMN IF NOT EXISTS last_retry_jitter_seconds integer;
ALTER TABLE ingestion_outbox ADD COLUMN IF NOT EXISTS completed_by text;
CREATE INDEX IF NOT EXISTS ingestion_outbox_queue_age_idx ON ingestion_outbox(status, available_at, tenant, workload);
