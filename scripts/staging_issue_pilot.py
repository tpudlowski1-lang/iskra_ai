"""One-shot staging credential registration; receives only a token digest."""
import os
import re
import time
import secrets
import psycopg

def main():
    digest = os.environ["ISKRA_PILOT_DIGEST"]
    cid = os.environ["ISKRA_PILOT_ID"]
    expiry = float(os.environ["ISKRA_PILOT_EXPIRY"])
    now = time.time()
    if not re.fullmatch(r"[0-9a-f]{64}", digest) or not re.fullmatch(r"cred_[0-9a-f]{32}", cid) or not now < expiry <= now + 31*86400:
        raise ValueError("Invalid pilot metadata")
    with psycopg.connect(os.environ["ISKRA_PILOT_OPERATOR_DSN"]) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_user")
            if cur.fetchone() != ("iskra_ai_staging_db", "iskra_staging_operator"):
                raise RuntimeError("Wrong target")
            cur.execute("SELECT rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb OR pg_has_role(current_user,'iskra_auth_owner','MEMBER'), pg_has_role(current_user,'iskra_auth_operator','MEMBER') FROM pg_roles WHERE rolname=current_user")
            if cur.fetchone() != (False, True):
                raise RuntimeError("Unsafe role")
            cur.execute("INSERT INTO iskra_auth.api_credentials (credential_id,token_digest,subject,tenant_id,roles_json,created_at,expires_at) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (credential_id) DO NOTHING RETURNING credential_id", (cid,digest,"iskra","iskra-test",'["admin"]',now,expiry))
            if cur.fetchone():
                cur.execute("INSERT INTO iskra_auth.credential_audit_events (event_id,event_type,credential_id,subject,tenant_id,actor,occurred_at) VALUES (%s,'credential_issued',%s,'iskra','iskra-test','staging-operator',%s)", (secrets.token_urlsafe(18),cid,now))
            else:
                cur.execute("SELECT token_digest,subject,tenant_id,roles_json,expires_at,revoked_at FROM iskra_auth.api_credentials WHERE credential_id=%s",(cid,))
                if cur.fetchone() != (digest,"iskra","iskra-test",'["admin"]',expiry,None):
                    raise RuntimeError("Credential mismatch")
    print("ISKRA_PILOT_CREDENTIAL_COMMITTED",flush=True)

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("ISKRA_PILOT_FAILED: "+type(exc).__name__,flush=True)
        raise SystemExit(1) from None
