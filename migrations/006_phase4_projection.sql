-- P4 dev/mock projection and replay state. ingestion_authority remains source of truth.
ALTER TABLE ingestion_outbox ADD COLUMN IF NOT EXISTS envelope jsonb;
ALTER TABLE ingestion_outbox ADD COLUMN IF NOT EXISTS correlation_id text NOT NULL DEFAULT '';
ALTER TABLE ingestion_outbox ADD COLUMN IF NOT EXISTS event_id text;

CREATE TABLE IF NOT EXISTS p4_document (
  tenant text NOT NULL, source text NOT NULL, source_id text NOT NULL,
  semantic_key text NOT NULL, revision bigint NOT NULL, operation text NOT NULL,
  title text NOT NULL DEFAULT '', body text NOT NULL DEFAULT '',
  raw_reference jsonb NOT NULL DEFAULT '{}'::jsonb, content_hash text NOT NULL DEFAULT '',
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb, readers text[], admins text[] NOT NULL DEFAULT '{}',
  tombstoned boolean NOT NULL DEFAULT false,
  search_vector tsvector GENERATED ALWAYS AS (to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(body,''))) STORED,
  updated_at timestamptz NOT NULL,
  PRIMARY KEY (tenant, source, source_id), UNIQUE (semantic_key)
);
CREATE INDEX IF NOT EXISTS p4_document_fts_idx ON p4_document USING gin(search_vector);
CREATE INDEX IF NOT EXISTS p4_document_acl_idx ON p4_document(tenant, source, tombstoned);

CREATE TABLE IF NOT EXISTS p4_projection_checkpoints (
  projection text PRIMARY KEY, sequence bigint NOT NULL DEFAULT 0,
  state text NOT NULL DEFAULT 'fresh', last_error text, updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS p4_identity_aliases (
  tenant text NOT NULL, source text NOT NULL, source_id text NOT NULL,
  provider text NOT NULL, connector text NOT NULL, source_instance text NOT NULL,
  PRIMARY KEY (tenant, source, source_id),
  UNIQUE (tenant, source, source_id, provider, connector, source_instance)
);
