"""Construct the selected credential backend for WSGI and the local operator."""
def credential_store_from_env(env, *, operator=False):
    backend = env.get("ISKRA_CREDENTIAL_STORE_BACKEND", "sqlite").strip().lower()
    secret = env.get("ISKRA_CSRF_HMAC_SECRET", "")
    if backend == "sqlite":
        from iskra.security.sqlite_credentials import SQLiteCredentialStore

        path = str(env.get("ISKRA_CREDENTIAL_DB_PATH") or "").strip()
        return SQLiteCredentialStore(path, csrf_secret=secret) if path else None
    if backend == "postgres":
        from iskra.security.postgres_credentials import PostgresCredentialStore

        key = "ISKRA_CREDENTIAL_OPERATOR_DSN" if operator else "ISKRA_CREDENTIAL_POSTGRES_DSN"
        return PostgresCredentialStore((env.get(key) or "").strip(), secret, operator=operator)
    raise ValueError("Unknown ISKRA_CREDENTIAL_STORE_BACKEND")
