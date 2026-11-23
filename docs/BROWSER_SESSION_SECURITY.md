# Browser session security

## Scope

The /assistant browser UI exchanges a persistent tenant API credential for a short-lived server-side browser session. The raw API credential is sent once in an Authorization: Bearer header and is not retained in JavaScript state after the exchange.

## Session lifecycle

- The session cookie is named __Host-iskra_session.
- Cookie attributes: Secure, HttpOnly, SameSite=Strict, Path=/, with no Domain attribute.
- The cookie value is a high-entropy opaque token; only its SHA-256 digest is stored.
- The session expires after at most eight hours and is tied to the originating persistent credential ID.
- Every browser-session request rechecks that the underlying credential remains active and unexpired. Revoking or rotating the credential therefore invalidates its browser sessions.
- Logout revokes the server-side session and expires the cookie.
- Browser sessions require the persistent credential registry. Static API_TOKEN and static JSON credentials remain usable for direct API access but cannot be exchanged for a browser session.

## CSRF and request boundaries

- Cookie-authenticated state-changing requests require X-CSRF-Token.
- The CSRF token is random, tied to the session, and stored with its digest in the private credential database. Keeping it stable across page refreshes supports multiple tabs without invalidating another tab's token.
- Cookie-authenticated mutations reject cross-site Fetch Metadata and mismatched Origin hosts.
- Basic-authenticated state-changing browser requests require a matching same-origin Origin; cross-origin or origin-less Basic mutations are rejected.
- Bearer and explicit API-token-header clients remain supported for non-browser integrations. Do not place bearer credentials in browser storage or URLs.
- The public GET /assistant shell and its two static assets contain no tenant data. All tenant APIs remain behind authentication.

## Operational requirements and limitations

- Serve the browser UI over HTTPS. The __Host- cookie is intentionally Secure-only.
- If TLS terminates at a reverse proxy (as on Render), enable `ISKRA_TRUST_PROXY_HEADERS=true` only when exactly one trusted proxy strips/replaces client-supplied forwarded headers. The WSGI entry point then trusts only one `X-Forwarded-Proto` hop; leave this disabled for direct deployments.
- Configure ISKRA_CREDENTIAL_DB_PATH on durable private storage with the existing owner-only directory/file protections. Ephemeral filesystems are not suitable for production sessions.
- SQLite credential/session storage is single-instance. Multi-instance production requires the reviewed shared PostgreSQL session/credential backend and concurrency testing.
- This is not a complete identity product: no public signup, password login, MFA, email verification, recovery, invitation workflow or billing is included.
- This control does not replace independent security review, CSP/XSS defenses, provider privacy review, monitoring, backup/restore drills or incident response.