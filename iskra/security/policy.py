"""Small deny-by-default authorization primitives for Flask endpoints."""
from functools import wraps

from flask import jsonify, request

from iskra.security.principal import principal_from_environ


def require_roles(*required_roles):
    """Require an authenticated server-derived principal with one allowed role."""
    required = frozenset(required_roles)
    if not required:
        raise ValueError("Wymagana jest co najmniej jedna rola")

    def decorate(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            principal = principal_from_environ(request.environ)
            if principal is None:
                return jsonify({"error": "unauthorized"}), 401
            if not principal.roles.intersection(required):
                return jsonify({"error": "forbidden"}), 403
            return view(*args, **kwargs)
        return wrapped
    return decorate
