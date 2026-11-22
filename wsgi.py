"""WSGI compatibility entry point.

This module intentionally does not claim to authenticate requests. Until the
application-level authentication and authorization layer is implemented and
tested, deployments must not expose private or customer data through this app.
"""
from app import app
