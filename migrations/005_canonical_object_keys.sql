-- ObjectKey uses protocol JSON serialization. json_build_array is not
-- immutable, so object_key is maintained by the same transaction as writes.
ALTER TABLE ingestion_authority DROP COLUMN IF EXISTS object_key;
ALTER TABLE ingestion_authority ADD COLUMN object_key text;
UPDATE ingestion_authority
SET object_key = json_build_array(provider, tenant, connector, source_instance, object_id)::text;
ALTER TABLE ingestion_authority ALTER COLUMN object_key SET NOT NULL;
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'ingestion_authority'::regclass
      AND conname = 'ingestion_authority_object_key_key'
  ) THEN
    ALTER TABLE ingestion_authority
      ADD CONSTRAINT ingestion_authority_object_key_key UNIQUE (object_key);
  END IF;
END $$;
