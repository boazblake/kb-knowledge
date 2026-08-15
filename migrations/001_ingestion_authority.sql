-- PostgreSQL authority schema. Raw bytes remain in S3-compatible storage.
CREATE TABLE IF NOT EXISTS ingestion_checkpoints (
  provider text NOT NULL DEFAULT 'unknown', tenant text NOT NULL DEFAULT 'default',
  connector text NOT NULL, source_instance text NOT NULL DEFAULT '',
  value text NOT NULL, complete boolean NOT NULL,
  PRIMARY KEY(provider, tenant, connector, source_instance),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS ingestion_outbox (
  sequence bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  idempotency_key text NOT NULL UNIQUE, object_key text NOT NULL, tenant text NOT NULL, workload text NOT NULL, payload jsonb NOT NULL,
  status text NOT NULL DEFAULT 'pending', attempts integer NOT NULL DEFAULT 0,
  lease_owner text, lease_expires_at timestamptz,
  available_at timestamptz NOT NULL DEFAULT now(), created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS ingestion_authority (
  provider text NOT NULL, tenant text NOT NULL, connector text NOT NULL,
  source_instance text NOT NULL, object_id text NOT NULL,
  object_key text GENERATED ALWAYS AS
    (provider || ':' || tenant || ':' || connector || ':' || source_instance || ':' || object_id) STORED,
  revision bigint NOT NULL, operation text NOT NULL,
  payload jsonb, raw_object_uri text NOT NULL, content_hash text NOT NULL,
  observed_at timestamptz NOT NULL, updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(provider, tenant, connector, source_instance, object_id),
  UNIQUE(object_key)
);
CREATE TABLE IF NOT EXISTS ingestion_audit (
  event_id text PRIMARY KEY, action text NOT NULL, actor text NOT NULL,
  target text NOT NULL, tenant text NOT NULL, occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS ingestion_idempotency (
  idempotency_key text PRIMARY KEY, object_key text NOT NULL, revision bigint NOT NULL, fingerprint text NOT NULL,
  accepted_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS ingestion_dead_letters (
  sequence bigint PRIMARY KEY, reason text NOT NULL, failed_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS ingestion_gaps (
  object_key text NOT NULL, expected_revision bigint NOT NULL, received_revision bigint NOT NULL,
  idempotency_key text PRIMARY KEY, payload jsonb NOT NULL, detected_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS schema_migrations (
  version integer PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now()
);
