-- Apply in ONE transaction as a migration operator with membership in iskra_auth_owner.
-- Provision the three NOLOGIN group roles and owner-controlled schema first.
SET LOCAL ROLE iskra_auth_owner;
SET LOCAL search_path = pg_catalog, iskra_auth, pg_temp;

DO $$
BEGIN
    IF (SELECT count(*) FROM pg_roles
        WHERE rolname IN ('iskra_auth_owner','iskra_auth_runtime','iskra_auth_operator')
          AND NOT (rolsuper OR rolbypassrls OR rolcanlogin OR rolcreaterole OR rolcreatedb))
        <> 3 OR (SELECT nspowner FROM pg_namespace WHERE nspname='iskra_auth')
              IS DISTINCT FROM 'iskra_auth_owner'::regrole::oid THEN
        RAISE EXCEPTION 'Incorrect Iskra auth role or schema ownership';
    END IF;
END $$;

CREATE TABLE iskra_auth.schema_version (version integer PRIMARY KEY);
CREATE TABLE iskra_auth.api_credentials (
    credential_id text PRIMARY KEY,
    token_digest text UNIQUE NOT NULL CHECK (token_digest ~ '^[0-9a-f]{64}$'),
    subject text NOT NULL CHECK (length(btrim(subject)) BETWEEN 1 AND 255),
    tenant_id text NOT NULL CHECK (tenant_id <> 'system' AND length(btrim(tenant_id)) BETWEEN 1 AND 255),
    roles_json text NOT NULL CHECK (roles_json IN ('["admin"]','["member"]','["admin","member"]')),
    created_at double precision NOT NULL,
    expires_at double precision CHECK (expires_at > created_at),
    revoked_at double precision
);
CREATE INDEX ON iskra_auth.api_credentials(tenant_id, created_at DESC);
CREATE TABLE iskra_auth.browser_sessions (
    session_digest text PRIMARY KEY CHECK (session_digest ~ '^[0-9a-f]{64}$'),
    credential_id text NOT NULL REFERENCES iskra_auth.api_credentials,
    csrf_digest text NOT NULL CHECK (csrf_digest ~ '^[0-9a-f]{64}$'),
    created_at double precision NOT NULL,
    expires_at double precision NOT NULL CHECK (expires_at > created_at),
    revoked_at double precision
);
CREATE INDEX ON iskra_auth.browser_sessions(credential_id, expires_at);
CREATE TABLE iskra_auth.credential_audit_events (
    event_id text PRIMARY KEY,
    event_type text NOT NULL CHECK (event_type IN ('credential_issued','credential_rotated','credential_revoked')),
    credential_id text NOT NULL REFERENCES iskra_auth.api_credentials,
    related_credential_id text REFERENCES iskra_auth.api_credentials,
    subject text NOT NULL,
    tenant_id text NOT NULL,
    actor text NOT NULL,
    occurred_at double precision NOT NULL
);
CREATE INDEX ON iskra_auth.credential_audit_events(occurred_at DESC);

ALTER TABLE iskra_auth.api_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE iskra_auth.browser_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE iskra_auth.credential_audit_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY credential_tenant ON iskra_auth.api_credentials TO iskra_auth_runtime
    USING (tenant_id = current_setting('iskra.tenant_id', true));
CREATE POLICY session_tenant ON iskra_auth.browser_sessions TO iskra_auth_runtime
    USING (EXISTS (SELECT 1 FROM iskra_auth.api_credentials c
                   WHERE c.credential_id = browser_sessions.credential_id
                     AND c.tenant_id = current_setting('iskra.tenant_id', true)));
CREATE POLICY audit_tenant ON iskra_auth.credential_audit_events FOR INSERT TO iskra_auth_runtime
    WITH CHECK (tenant_id = current_setting('iskra.tenant_id', true));
CREATE POLICY credential_operator ON iskra_auth.api_credentials TO iskra_auth_operator USING (true);
CREATE POLICY audit_operator ON iskra_auth.credential_audit_events TO iskra_auth_operator USING (true);

-- Bootstrap runs before a tenant is known. Only the two digest lookups run as the
-- non-login table owner. Never grant owner membership or DDL to a service login.
CREATE FUNCTION iskra_auth.lookup_credential(digest text)
RETURNS TABLE (credential_id text, subject text, tenant_id text, roles_json text,
               expires_at double precision, revoked_at double precision)
LANGUAGE sql STABLE STRICT SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    SELECT c.credential_id, c.subject, c.tenant_id, c.roles_json, c.expires_at, c.revoked_at
    FROM iskra_auth.api_credentials c WHERE c.token_digest = digest AND c.revoked_at IS NULL
      AND (c.expires_at IS NULL OR c.expires_at > extract(epoch FROM statement_timestamp()))
$$;
CREATE FUNCTION iskra_auth.lookup_session(digest text)
RETURNS TABLE (credential_id text, csrf_digest text, session_expires_at double precision,
               session_revoked_at double precision, subject text, tenant_id text,
               roles_json text, credential_expires_at double precision, credential_revoked_at double precision)
LANGUAGE sql STABLE STRICT SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    SELECT c.credential_id, s.csrf_digest, s.expires_at, s.revoked_at,
           c.subject, c.tenant_id, c.roles_json, c.expires_at, c.revoked_at
      FROM iskra_auth.browser_sessions s JOIN iskra_auth.api_credentials c USING (credential_id)
     WHERE s.session_digest = digest AND s.revoked_at IS NULL AND c.revoked_at IS NULL
       AND s.expires_at > extract(epoch FROM statement_timestamp())
       AND (c.expires_at IS NULL OR c.expires_at > extract(epoch FROM statement_timestamp()))
$$;

REVOKE ALL ON SCHEMA iskra_auth FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA iskra_auth FROM PUBLIC;
GRANT USAGE ON SCHEMA iskra_auth TO iskra_auth_runtime, iskra_auth_operator;
GRANT SELECT ON iskra_auth.schema_version TO iskra_auth_runtime, iskra_auth_operator;
GRANT SELECT, INSERT, UPDATE(revoked_at) ON iskra_auth.api_credentials TO iskra_auth_runtime, iskra_auth_operator;
GRANT SELECT, INSERT, DELETE, UPDATE(csrf_digest, revoked_at) ON iskra_auth.browser_sessions TO iskra_auth_runtime;
GRANT INSERT ON iskra_auth.credential_audit_events TO iskra_auth_runtime, iskra_auth_operator;
GRANT SELECT ON iskra_auth.credential_audit_events TO iskra_auth_operator;
GRANT EXECUTE ON FUNCTION iskra_auth.lookup_credential(text), iskra_auth.lookup_session(text)
    TO iskra_auth_runtime;
INSERT INTO iskra_auth.schema_version VALUES (3);
