"""Local operator CLI for issuing, rotating, revoking and auditing API tokens.

No HTTP credential-management endpoint is exposed. Raw tokens are printed only
once by the explicit local issue/rotate command and are never written to logs.
"""
import argparse
from datetime import datetime, timezone
import json
import os
import sys
import time

from iskra.security.principal import Principal
from iskra.security.sqlite_credentials import (
    CredentialStoreUnavailable,
    SQLiteCredentialStore,
)


def _store_from_environment():
    path = os.environ.get("ISKRA_CREDENTIAL_DB_PATH", "").strip()
    if not path:
        raise RuntimeError("Ustaw ISKRA_CREDENTIAL_DB_PATH zgodnie z konfiguracją WSGI")
    return SQLiteCredentialStore(path)


def _parse_roles(value):
    roles = frozenset(part.strip() for part in value.split(",") if part.strip())
    if not roles:
        raise ValueError("Podaj co najmniej jedną rolę")
    return roles


def _expires_at(days):
    if days is None:
        return None
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 3650:
        raise ValueError("Okres ważności musi należeć do zakresu 1..3650 dni")
    return time.time() + days * 86400


def _require_confirmation(args, parser):
    if not args.confirm:
        parser.error("Operacja zmieniająca poświadczenia wymaga jawnego --confirm")


def _print_issued(issued, expires_at):
    print(json.dumps(
        {
            "credential_id": issued.credential_id,
            "token": issued.token,
            "expires_at": (
                datetime.fromtimestamp(expires_at, timezone.utc).isoformat()
                if expires_at is not None else None
            ),
            "warning": "Token pokazano tylko raz. Zapisz go w menedżerze sekretów; nie wysyłaj go do logów ani repozytorium.",
        },
        ensure_ascii=False,
        indent=2,
    ))


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    issue = subparsers.add_parser("issue", help="Wydaj nowy token tenantowy")
    issue.add_argument("--subject", required=True)
    issue.add_argument("--tenant-id", required=True)
    issue.add_argument("--roles", default="member")
    issue.add_argument("--expires-in-days", type=int, default=90)
    issue.add_argument("--actor", default=os.environ.get("ISKRA_OPERATOR_ID", "local-operator"))
    issue.add_argument("--allow-admin", action="store_true", help="Dodatkowe potwierdzenie wydania roli admin")
    issue.add_argument("--confirm", action="store_true")

    revoke = subparsers.add_parser("revoke", help="Unieważnij token")
    revoke.add_argument("--credential-id", required=True)
    revoke.add_argument("--actor", default=os.environ.get("ISKRA_OPERATOR_ID", "local-operator"))
    revoke.add_argument("--confirm", action="store_true")

    rotate = subparsers.add_parser("rotate", help="Atomowo wydaj nowy token i unieważnij stary")
    rotate.add_argument("--credential-id", required=True)
    rotate.add_argument("--expires-in-days", type=int)
    rotate.add_argument("--roles", help="Opcjonalnie ogranicz istniejące role; nie można ich podwyższyć")
    rotate.add_argument("--actor", default=os.environ.get("ISKRA_OPERATOR_ID", "local-operator"))
    rotate.add_argument("--confirm", action="store_true")

    audit = subparsers.add_parser("audit", help="Pokaż zdarzenia cyklu życia poświadczeń")
    audit.add_argument("--limit", type=int, default=100)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        store = _store_from_environment()

        if args.command == "issue":
            _require_confirmation(args, parser)
            if args.tenant_id == "system":
                raise ValueError("Nie wydawaj tenantowych tokenów dla system; użyj kontrolowanego API_TOKEN")
            roles = _parse_roles(args.roles)
            if "admin" in roles and not args.allow_admin:
                parser.error("Wydanie roli admin wymaga dodatkowego --allow-admin")
            principal = Principal(args.subject, args.tenant_id, roles)
            expiry = _expires_at(args.expires_in_days)
            issued = store.issue(principal, expires_at=expiry, actor=args.actor)
            _print_issued(issued, expiry)
            return 0

        if args.command == "revoke":
            _require_confirmation(args, parser)
            if not store.revoke(args.credential_id, actor=args.actor):
                raise ValueError("Token nie istnieje lub został już unieważniony")
            print(json.dumps({"status": "revoked", "credential_id": args.credential_id}))
            return 0

        if args.command == "rotate":
            _require_confirmation(args, parser)
            expiry = _expires_at(args.expires_in_days)
            roles = _parse_roles(args.roles) if args.roles is not None else None
            issued = store.rotate(
                args.credential_id,
                expires_at=expiry,
                roles=roles,
                actor=args.actor,
            )
            _print_issued(issued, issued.expires_at)
            return 0

        if args.command == "audit":
            events = store.list_audit_events(limit=args.limit)
            print(json.dumps(events, ensure_ascii=False, indent=2))
            return 0

        parser.error("Nieznana operacja")
    except (ValueError, RuntimeError, CredentialStoreUnavailable) as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
