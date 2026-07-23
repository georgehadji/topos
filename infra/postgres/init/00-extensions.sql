-- Extensions. Everything Topos needs lives in one database (ADR-002).
CREATE EXTENSION IF NOT EXISTS postgis;       -- geometry, spatial indexes
CREATE EXTENSION IF NOT EXISTS vector;        -- pgvector: halfvec + HNSW
CREATE EXTENSION IF NOT EXISTS pg_trgm;       -- fuzzy Greek toponym matching
CREATE EXTENSION IF NOT EXISTS unaccent;      -- accent folding (τόνοι)
CREATE EXTENSION IF NOT EXISTS btree_gin;     -- composite GIN for filtered FTS
CREATE EXTENSION IF NOT EXISTS pgcrypto;      -- gen_random_uuid, digest

-- Sanity: fail loudly at container start rather than at migration time.
DO $$
BEGIN
  IF current_setting('server_version_num')::int < 160000 THEN
    RAISE EXCEPTION 'PostgreSQL 16+ required';
  END IF;
END $$;
