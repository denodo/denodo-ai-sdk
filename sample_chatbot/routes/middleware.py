"""
Contains request/response middleware for the chatbot.
"""

import os

from flask import request
from flask_login import current_user
from utils.utils import generate_transaction_id
from utils.logging_utils import transaction_id_var, username_var
from utils.runtime_config import sync_runtime_config

# Applied to every chatbot response. Each entry is (header, env override, default).
# An empty environment value omits that header.
_SECURITY_HEADER_DEFAULTS = (
    (
        'Strict-Transport-Security',
        'CHATBOT_STRICT_TRANSPORT_SECURITY',
        'max-age=31536000; includeSubDomains',
    ),
    (
        'Content-Security-Policy',
        'CHATBOT_CONTENT_SECURITY_POLICY',
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; "
        "worker-src 'self' blob:; object-src 'none'; base-uri 'self'; "
        "form-action 'self'; frame-ancestors 'self'",
    ),
    (
        'Permissions-Policy',
        'CHATBOT_PERMISSIONS_POLICY',
        'camera=(), microphone=(), geolocation=()',
    ),
    (
        'X-Content-Type-Options',
        'CHATBOT_X_CONTENT_TYPE_OPTIONS',
        'nosniff',
    ),
)


def security_response_headers():
    """Resolve the security headers for a chatbot response."""
    headers = {}
    for name, env_name, default in _SECURITY_HEADER_DEFAULTS:
        value = os.getenv(env_name, default)
        if value is None:
            continue
        value = value.strip()
        if value:
            headers[name] = value
    return headers


def register_security_headers(app):
    """Add the chatbot security headers to every response."""
    
    headers_to_apply = security_response_headers()

    @app.after_request
    def add_security_headers(response):
        for name, value in headers_to_apply.items():
            response.headers[name] = value
        return response

def register_middleware(blueprint):
    """
    Register middleware on a blueprint.

    Args:
        blueprint: Flask Blueprint instance
    """

    @blueprint.before_request
    def set_logging_context():
        """Set transaction ID and username for the request context."""
        sync_runtime_config()

        transaction_id_var.set(generate_transaction_id())
        username = "anonymous"

        if current_user and current_user.is_authenticated:
            username = current_user.id

        elif request.path.endswith('/login') and request.is_json:
            data = request.json or {}
            if data.get('username'):
                username = data.get('username')

        username_var.set(username)

    @blueprint.after_request
    def add_transaction_id_after_request(response):
        """Add the transaction ID to the response headers."""
        response.headers['X-Transaction-ID'] = transaction_id_var.get()
        return response
