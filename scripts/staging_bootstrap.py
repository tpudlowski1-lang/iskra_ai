"""One-shot staging bootstrap; never run in the application process."""
import os
from pathlib import Path
import psycopg
from psycopg import sql

def main():
    if os.environ.get("ISKRA_BOOTSTRAP_TARGET") != "iskra_ai_staging_db":
        raise RuntimeError("Staging guard")
    with psycopg.connect(os.environ["ISKRA_BOOTSTRAP_DSN"]) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_user")
            db, admin = cur.fetchone()
            if db != "iskra_ai_staging_db":
                raise RuntimeError("Wrong database")
            cur.execute("SELECT pg_advisory_xact_lock(839503)")
            for role in ("iskra_auth_owner", "iskra_auth_runtime", "iskra_auth_operator"):
                cur.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,))
                if not cur.fetchone():
                    cur.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB").format(sql.Identifier(role)))
            cur.execute(sql.SQL("GRANT iskra_auth_owner TO {}").format(sql.Identifier(admin)))
            cur.execute("CREATE SCHEMA IF NOT EXISTS iskra_auth AUTHORIZATION iskra_auth_owner")
            for role, env, group in (
                ("iskra_staging_runtime", "ISKRA_BOOTSTRAP_RUNTIME_PASSWORD", "iskra_auth_runtime"),
                ("iskra_staging_graph", "ISKRA_BOOTSTRAP_GRAPH_PASSWORD", None),
                ("iskra_staging_operator", "ISKRA_BOOTSTRAP_OPERATOR_PASSWORD", "iskra_auth_operator"),
            ):
                password = os.environ[env]
                if len(password) < 32:
                    raise RuntimeError("Weak password")
                cur.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,))
                verb = "ALTER" if cur.fetchone() else "CREATE"
                cur.execute(sql.SQL(verb + " ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB PASSWORD {}").format(sql.Identifier(role), sql.Literal(password)))
                if group:
                    cur.execute(sql.SQL("GRANT {} TO {}").format(sql.Identifier(group), sql.Identifier(role)))
            root = Path(__file__).resolve().parents[1] / "migrations"
            cur.execute("SET LOCAL search_path = public, pg_catalog")
            for name in ("0001_tenant_graph.sql", "0002_tenant_documents.sql"):
                cur.execute((root / name).read_text())
            cur.execute("SELECT to_regclass('iskra_auth.schema_version')")
            if cur.fetchone()[0] is None:
                cur.execute((root / "0003_credential_store.sql").read_text())
            cur.execute("RESET ROLE")
            cur.execute("SELECT version FROM iskra_auth.schema_version")
            if cur.fetchall() != [(3,)]:
                raise RuntimeError("Unexpected auth schema")
            cur.execute("GRANT USAGE ON SCHEMA public TO iskra_staging_graph")
            cur.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON public.iskra_graph_neurons, public.iskra_graph_synapses, public.iskra_tenant_documents, public.iskra_tenant_document_chunks TO iskra_staging_graph")
            cur.execute("GRANT SELECT ON public.iskra_schema_migrations TO iskra_staging_graph")
    print("ISKRA_STAGING_MIGRATION_COMMITTED", flush=True)

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("ISKRA_STAGING_MIGRATION_FAILED: " + type(exc).__name__, flush=True)
        raise SystemExit(1) from None
