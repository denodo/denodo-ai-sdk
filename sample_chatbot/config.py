import os
from utils.utils import normalize_root_path
from sample_chatbot.engine.prompts import CHATBOT_SYSTEM_PROMPT, DEEPQUERY_GUIDANCE

class ChatbotConfig:
    """Configuration class that loads and validates all environment variables."""

    def __init__(self):
        # LLM Configuration
        self.llm_provider = os.environ['CHATBOT_LLM_PROVIDER']
        self.llm_model = os.environ['CHATBOT_LLM_MODEL']
        self.llm_temperature = float(os.getenv('CHATBOT_LLM_TEMPERATURE', '0'))
        self.llm_max_tokens = int(os.getenv('CHATBOT_LLM_MAX_TOKENS', '4096'))
        self.llm_response_rows_limit = int(os.getenv('CHATBOT_LLM_RESPONSE_ROWS_LIMIT', '15'))

        # Embeddings Configuration
        self.embeddings_provider = os.environ['CHATBOT_EMBEDDINGS_PROVIDER']
        self.embeddings_model = os.environ['CHATBOT_EMBEDDINGS_MODEL']

        # Vector Store Configuration
        self.vector_store_provider = os.environ['CHATBOT_VECTOR_STORE_PROVIDER']

        # System Prompts (from engine/prompts.py)
        self.system_prompt = CHATBOT_SYSTEM_PROMPT
        self.deepquery_guidance = DEEPQUERY_GUIDANCE

        # Server Configuration
        self.host = os.getenv('CHATBOT_HOST', '0.0.0.0')
        self.port = int(os.getenv('CHATBOT_PORT', 9992))
        self.root_path = normalize_root_path(os.getenv("CHATBOT_ROOT_PATH", ""))
        self.ssl_cert = os.getenv('CHATBOT_SSL_CERT')
        self.ssl_key = os.getenv('CHATBOT_SSL_KEY')

        # Feature Flags
        self.deepquery_enabled = bool(int(os.getenv('CHATBOT_DEEPQUERY', '1')))
        self.reporting_enabled = bool(int(os.getenv('CHATBOT_REPORTING', '0')))
        self.feedback_enabled = bool(int(os.getenv('CHATBOT_FEEDBACK', '0')))
        self.unstructured_mode = bool(int(os.getenv('CHATBOT_UNSTRUCTURED_MODE', '1')))
        self.user_edit_llm = bool(int(os.getenv('CHATBOT_USER_EDIT_LLM', '0')))
        self.auto_graph = bool(int(os.getenv('CHATBOT_AUTO_GRAPH', '1')))
        self.allow_sync = bool(int(os.getenv('CHATBOT_ALLOW_SYNC', '1')))

        # Reporting Configuration
        self.report_max_size = int(os.getenv('CHATBOT_REPORT_MAX_SIZE', '10'))
        self.report_max_files = int(os.getenv('CHATBOT_REPORT_MAX_FILES', '10'))

        # Unstructured Data Configuration
        self.unstructured_index = os.getenv('CHATBOT_UNSTRUCTURED_INDEX')
        self.unstructured_description = os.getenv('CHATBOT_UNSTRUCTURED_DESCRIPTION')

        # Sync Configuration
        self.sync_vdbs_timeout = int(os.getenv('CHATBOT_SYNC_VDBS_TIMEOUT', '600000'))

        # AI SDK Configuration
        self.ai_sdk_host = os.getenv('AI_SDK_URL', 'http://localhost:8008')
        self.ai_sdk_username = os.getenv('AI_SDK_USERNAME')
        self.ai_sdk_password = os.getenv('AI_SDK_PASSWORD')
        self.ai_sdk_verify_ssl = bool(int(os.getenv('AI_SDK_VERIFY_SSL', '0')))

        # External Services
        self.data_marketplace_url = os.getenv("CHATBOT_DATA_MARKETPLACE_URL")

    @property
    def ssl_enabled(self):
        """Check if SSL is enabled."""
        return bool(self.ssl_cert and self.ssl_key)

    @property
    def has_ai_sdk_credentials(self):
        """Check if AI SDK credentials are configured."""
        return bool(self.ai_sdk_username and self.ai_sdk_password)

    @property
    def effective_feedback_enabled(self):
        """Feedback is only enabled if reporting is also enabled."""
        return self.feedback_enabled if self.reporting_enabled else False

    def log_config(self, logger):
        """Log the current configuration."""
        logger.info("Chatbot parameters:")
        logger.info(f"    - LLM Model: {self.llm_provider}/{self.llm_model} (temp={self.llm_temperature}, max_tokens={self.llm_max_tokens})")
        logger.info(f"    - Embeddings Model: {self.embeddings_provider}/{self.embeddings_model}")
        logger.info(f"    - Vector Store Provider: {self.vector_store_provider}")
        logger.info(f"    - AI SDK Host: {self.ai_sdk_host}")
        logger.info(f"    - Using SSL: {self.ssl_enabled}")
        logger.info(f"    - DeepQuery: {'enabled' if self.deepquery_enabled else 'disabled'}")
        logger.info(f"    - Reporting: {self.reporting_enabled}")
        logger.info(f"    - Report Max Size: {self.report_max_size}mb")
        logger.info(f"    - Report Max Files: {'unlimited' if self.report_max_files <= 0 else self.report_max_files}")
        logger.info(f"    - Feedback: {self.effective_feedback_enabled}")
        logger.info(f"    - Auto Graph: {self.auto_graph}")
        logger.info(f"    - User can edit LLM settings: {self.user_edit_llm}")
        logger.info(f"    - Data Marketplace URL (for direct view linking): {self.data_marketplace_url}")

# Singleton instance - initialized after config is loaded
_config = None

def get_config():
    """Get the singleton configuration instance."""
    global _config
    if _config is None:
        _config = ChatbotConfig()
    return _config

def init_config():
    """Initialize the configuration (call after loading env vars)."""
    global _config
    _config = ChatbotConfig()
    return _config
