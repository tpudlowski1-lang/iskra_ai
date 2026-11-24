-- Fresh, dedicated staging database. Run once with psql -X -1 -v ON_ERROR_STOP=1.
-- The migration account provisions group roles. Service logins are provisioned separately.
CREATE ROLE iskra_auth_owner NOLOGIN;
CREATE ROLE iskra_auth_runtime NOLOGIN;
CREATE ROLE iskra_auth_operator NOLOGIN;
CREATE ROLE iskra_stage_data_runtime NOLOGIN;
GRANT iskra_auth_owner TO CURRENT_USER;

CREATE SCHEMA iskra_stage_data;
REVOKE ALL ON SCHEMA iskra_stage_data FROM PUBLIC;
SET LOCAL search_path = iskra_stage_data, pg_catalog;
\ir ../migrations/0001_tenant_graph.sql
\ir ../migrations/0002_tenant_documents.sql
GRANT USAGE ON SCHEMA iskra_stage_data TO iskra_stage_data_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON
    iskra_stage_data.iskra_graph_neurons, iskra_stage_data.iskra_graph_synapses,
    iskra_stage_data.iskra_tenant_documents, iskra_stage_data.iskra_tenant_document_chunks
    TO iskra_stage_data_runtime;

CREATE SCHEMA iskra_auth AUTHORIZATION iskra_auth_owner;
\ir ../migrations/0003_credential_store.sql
RESET ROLE;
