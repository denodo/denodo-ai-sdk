"""
Contains request/response middleware for blueprints.
"""

from flask import request
from flask_login import current_user
from utils.utils import generate_transaction_id
from utils.logging_utils import transaction_id_var, username_var

def register_middleware(blueprint):
    """
    Register middleware on a blueprint.

    Args:
        blueprint: Flask Blueprint instance
    """

    @blueprint.before_request
    def set_logging_context():
        """Set transaction ID and username for the request context."""
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
