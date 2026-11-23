-- Iskra tenant document schema v2.
-- Apply with a migration/admin role. Runtime role must be NOSUPERUSER,
-- NOBYPASSRLS and must not own these tables.
CREATE TABLE IF NOT EXISTS iskra_tenant_documents (
    tenant_id TEXT NOT NULL CHECK (length(tenant_id) BETWEEN 1 AND 255),
    document_id UUID NOT NULL,
    filename TEXT NOT NULL CHECK (length(filename) BETWEEN 1 AND 255),
    extension TEXT NOT NULL CHECK (extension IN ('.txt', '.pdf', '.docx')),
    sha256 CHAR(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, document_id),
    UNIQUE (tenant_id, sha256)
);

CREATE TABLE IF NOT EXISTS iskra_tenant_document_chunks (
    tenant_id TEXT NOT NULL,
    document_id UUID NOT NULL,
    chunk_id UUID NOT NULL,
    chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
    content TEXT NOT NULL CHECK (length(content) BETWEEN 1 AND 1000),
    search_vector TSVECTOR GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED,
    PRIMARY KEY (tenant_id, chunk_id),
    UNIQUE (tenant_id, document_id, chunk_index),
    FOREIGN KEY (tenant_id, document_id)
        REFERENCES iskra_tenant_documents(tenant_id, document_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_iskra_tenant_documents_created
    ON iskra_tenant_documents(tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_iskra_tenant_document_chunks_search
    ON iskra_tenant_document_chunks USING GIN(search_vector);

CREATE INDEX IF NOT EXISTS idx_iskra_tenant_document_chunks_document
    ON iskra_tenant_document_chunks(tenant_id, document_id, chunk_index);

ALTER TABLE iskra_tenant_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE iskra_tenant_documents FORCE ROW LEVEL SECURITY;
ALTER TABLE iskra_tenant_document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE iskra_tenant_document_chunks FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = current_schema()
          AND tablename = 'iskra_tenant_documents'
          AND policyname = 'iskra_tenant_documents_tenant_policy'
    ) THEN
        CREATE POLICY iskra_tenant_documents_tenant_policy
            ON iskra_tenant_documents
            USING (tenant_id = current_setting('iskra.tenant_id', true))
            WITH CHECK (tenant_id = current_setting('iskra.tenant_id', true));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = current_schema()
          AND tablename = 'iskra_tenant_document_chunks'
          AND policyname = 'iskra_tenant_document_chunks_tenant_policy'
    ) THEN
        CREATE POLICY iskra_tenant_document_chunks_tenant_policy
            ON iskra_tenant_document_chunks
            USING (tenant_id = current_setting('iskra.tenant_id', true))
            WITH CHECK (tenant_id = current_setting('iskra.tenant_id', true));
    END IF;
END;
$$;

INSERT INTO iskra_schema_migrations(version) VALUES (2)
ON CONFLICT (version) DO NOTHING;
