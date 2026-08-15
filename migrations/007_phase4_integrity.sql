-- Explicit namespace aliases reject ambiguous empty provenance.
ALTER TABLE p4_identity_aliases
  ADD CONSTRAINT p4_identity_aliases_nonempty
  CHECK (tenant <> '' AND source <> '' AND source_id <> '' AND provider <> ''
         AND connector <> '' AND source_instance <> '');
