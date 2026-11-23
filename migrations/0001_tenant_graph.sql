-- Iskra tenant graph schema v1.
-- Apply with a migration/admin role. Runtime role must be NOSUPERUSER,
-- NOBYPASSRLS and must not own these tables.
CREATE TABLE IF NOT EXISTS iskra_schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS iskra_graph_neurons (
    tenant_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    label TEXT NOT NULL,
    weight DOUBLE PRECISION NOT NULL CHECK (weight >= 0 AND weight <= 1),
    created DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (tenant_id, node_id)
);

CREATE TABLE IF NOT EXISTS iskra_graph_synapses (
    tenant_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    strength DOUBLE PRECISION NOT NULL CHECK (strength >= 0 AND strength <= 1),
    PRIMARY KEY (tenant_id, source_id, target_id),
    FOREIGN KEY (tenant_id, source_id)
        REFERENCES iskra_graph_neurons(tenant_id, node_id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, target_id)
        REFERENCES iskra_graph_neurons(tenant_id, node_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_iskra_graph_synapses_tenant
    ON iskra_graph_synapses(tenant_id);

ALTER TABLE iskra_graph_neurons ENABLE ROW LEVEL SECURITY;
ALTER TABLE iskra_graph_neurons FORCE ROW LEVEL SECURITY;
ALTER TABLE iskra_graph_synapses ENABLE ROW LEVEL SECURITY;
ALTER TABLE iskra_graph_synapses FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = current_schema()
          AND tablename = 'iskra_graph_neurons'
          AND policyname = 'iskra_graph_neurons_tenant_policy'
    ) THEN
        CREATE POLICY iskra_graph_neurons_tenant_policy
            ON iskra_graph_neurons
            USING (tenant_id = current_setting('iskra.tenant_id', true))
            WITH CHECK (tenant_id = current_setting('iskra.tenant_id', true));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = current_schema()
          AND tablename = 'iskra_graph_synapses'
          AND policyname = 'iskra_graph_synapses_tenant_policy'
    ) THEN
        CREATE POLICY iskra_graph_synapses_tenant_policy
            ON iskra_graph_synapses
            USING (tenant_id = current_setting('iskra.tenant_id', true))
            WITH CHECK (tenant_id = current_setting('iskra.tenant_id', true));
    END IF;
END;
$$;

INSERT INTO iskra_schema_migrations(version) VALUES (1)
ON CONFLICT (version) DO NOTHING;
