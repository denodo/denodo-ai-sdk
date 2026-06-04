"""
Sample chatbot utilities package.
"""

# AI SDK client functions
from sample_chatbot.utils.ai_sdk_client import (
    ai_sdk_health_check,
    get_user_access_info,
    connect_to_ai_sdk,
    get_synced_resources,
    get_ai_sdk_info,
    filter_synced_resources,
    filter_partial_resources
)

# CSV utilities
from sample_chatbot.utils.csv_utils import (
    detect_csv_delimiter,
    get_csv_preview,
    generate_csv_description,
    validate_csv_path,
    csv_to_documents,
    get_safe_source_name,
)

# Helper utilities
from sample_chatbot.utils.helpers import (
    setup_user_details,
    check_env_variables,
    setup_directories,
    get_config_value,
)

__all__ = [
    # AI SDK client
    'ai_sdk_health_check',
    'get_user_access_info',
    'connect_to_ai_sdk',
    'get_synced_resources',
    'get_ai_sdk_info',
    'filter_synced_resources',
    'filter_partial_resources',
    # CSV utilities
    'detect_csv_delimiter',
    'get_csv_preview',
    'generate_csv_description',
    'validate_csv_path',
    'csv_to_documents',
    'get_safe_source_name',
    # Helpers
    'setup_user_details',
    'check_env_variables',
    'setup_directories',
    'get_config_value'
]
