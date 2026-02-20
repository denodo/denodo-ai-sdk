"""
Contains request/response middleware for blueprints.
"""

from utils.utils import generate_transaction_id
from utils.logging_utils import transaction_id_var

def register_middleware(blueprint):
    """
    Register middleware on a blueprint.

    Args:
        blueprint: Flask Blueprint instance
    """

    @blueprint.before_request
    def add_transaction_id_before_request():
        """Generate and store a transaction ID for the request."""
        transaction_id_var.set(generate_transaction_id())

    @blueprint.after_request
    def add_transaction_id_after_request(response):
        """Add the transaction ID to the response headers."""
        response.headers['X-Transaction-ID'] = transaction_id_var.get()
        return response
