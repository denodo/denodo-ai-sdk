import os

from sample_chatbot.engine.prompts import CHATBOT_SYSTEM_PROMPT, DEEPQUERY_GUIDANCE
from sample_chatbot.utils.helpers import get_config_value
from sample_chatbot.utils.helpers import setup_directory, get_icon_as_base64
from utils.uniformLLM import UniformLLM
from utils.utils import normalize_root_path


class ChatbotConfig:
    """
    Configuration class that loads and validates settings from a dictionary
    with a fallback to environment variables.
    """

    def __init__(self, config_dict=None):
        config_dict = config_dict or {}
        settings = config_dict.get("settings", {})

        self.name = config_dict.get('name', 'General Chat')
        self.id = config_dict.get('id', 'global')
        self.is_global = True if self.id == 'global' else False
        default_description = 'The general assistant, ready to answer any questions about your data.' if self.is_global else ''
        self.description = config_dict.get('description', default_description)
        self.icon = get_icon_as_base64(config_dict.get('icon_file_name', None))

        # Access control
        self.allowed_users = config_dict.get('allowed_users', None)

        # Centralized Data Directory
        self.data_dir = os.getenv("AI_SDK_DATA_DIR", ".")

        # LLM Configuration
        self.llm_provider = get_config_value(settings, 'llm_provider', 'CHATBOT_LLM_PROVIDER')
        self.llm_model = get_config_value(settings, 'llm_model', 'CHATBOT_LLM_MODEL')
        self.llm_temperature = get_config_value(settings, 'llm_temperature', 'CHATBOT_LLM_TEMPERATURE', '0', float)
        self.llm_max_tokens = get_config_value(settings, 'llm_max_tokens', 'CHATBOT_LLM_MAX_TOKENS', '4096', int)
        self.llm_response_rows_limit = get_config_value(settings, 'llm_response_rows_limit', 'CHATBOT_LLM_RESPONSE_ROWS_LIMIT', '15', int)

        # Initialize LLM
        self.llm = UniformLLM(
            self.llm_provider,
            self.llm_model,
            self.llm_temperature,
            self.llm_max_tokens
        )

        # AI SDK LLM Settings
        ai_sdk_llm_settings = settings.get('ai_sdk_llm_settings', {})

        thinking_llm = ai_sdk_llm_settings.get('thinking_llm', {})
        self.ai_sdk_thinking_llm_provider = thinking_llm.get('llm_provider')
        self.ai_sdk_thinking_llm_model = thinking_llm.get('llm_model')
        self.ai_sdk_thinking_llm_temperature = thinking_llm.get('llm_temperature')
        self.ai_sdk_thinking_llm_max_tokens = thinking_llm.get('llm_max_tokens')

        base_llm = ai_sdk_llm_settings.get('base_llm', {})
        self.ai_sdk_base_llm_provider = base_llm.get('llm_provider')
        self.ai_sdk_base_llm_model = base_llm.get('llm_model')
        self.ai_sdk_base_llm_temperature = base_llm.get('llm_temperature')
        self.ai_sdk_base_llm_max_tokens = base_llm.get('llm_max_tokens')

        self.use_base_llm_for_execution = ai_sdk_llm_settings.get('use_base_llm_for_execution', False)

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
        self.deepquery_enabled = get_config_value(settings, 'deepquery_enabled', 'CHATBOT_DEEPQUERY', '1', bool)
        self.reporting_enabled = get_config_value(settings, 'reporting_enabled', 'CHATBOT_REPORTING', '0', bool)
        self.feedback_enabled = get_config_value(settings, 'feedback_enabled', 'CHATBOT_FEEDBACK', '0', bool)
        self.unstructured_mode = get_config_value(settings, 'unstructured_mode', 'CHATBOT_UNSTRUCTURED_MODE', '1', bool)
        self.user_edit_llm = get_config_value(settings, 'user_edit_llm', 'CHATBOT_USER_EDIT_LLM', '0', bool)
        self.auto_graph = get_config_value(settings, 'auto_graph', 'CHATBOT_AUTO_GRAPH', '1', bool)
        self.allow_sync = bool(int(os.getenv('CHATBOT_ALLOW_SYNC', '1')))
        self.filters_enabled = settings.get('filters_enabled', True)

        # Reporting Configuration
        if self.data_dir != ".":
            self.reports_folder = os.path.join(self.data_dir, "reports", self.id)
        else:
            self.reports_folder = f"reports/{self.id}"

        self.report_max_size = get_config_value(settings, 'report_max_size', 'CHATBOT_REPORT_MAX_SIZE', '10', int)
        self.report_max_files = get_config_value(settings, 'report_max_files', 'CHATBOT_REPORT_MAX_FILES', '10', int)

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

        # Custom instructions
        self.custom_instructions = get_config_value(settings, 'custom_intructions', 'CHATBOT_CUSTOM_INTRUCTIONS', '')
        self.user_add_custom_instructions = get_config_value(settings, 'user_add_custom_instructions','CHATBOT_USER_ADD_CUSTOM_INTRUCTIONS', '1', bool)

        # Check ambiguity
        self.check_ambiguity = get_config_value(settings, 'check_ambiguity', 'CHATBOT_CHECK_AMBIGUITY', '1', bool)

        # Agent metadata
        self.databases = settings.get('databases', [])
        self.tags = settings.get('tags', [])

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
        logger.info(f"Chatbot parameters for agent: {self.name}")
        logger.info(
            f"    - LLM Model: {self.llm_provider}/{self.llm_model} (temp={self.llm_temperature}, max_tokens={self.llm_max_tokens})")

        # Log AI SDK LLM Settings if configured
        if self.ai_sdk_thinking_llm_model:
            logger.info(
                f"    - AI SDK Thinking LLM: {self.ai_sdk_thinking_llm_provider}/{self.ai_sdk_thinking_llm_model} (temp={self.ai_sdk_thinking_llm_temperature})")
        if self.ai_sdk_base_llm_model:
            logger.info(
                f"    - AI SDK Base LLM: {self.ai_sdk_base_llm_provider}/{self.ai_sdk_base_llm_model} (temp={self.ai_sdk_base_llm_temperature})")
        if self.use_base_llm_for_execution is not None:
            logger.info(f"    - AI SDK Use Base LLM for Execution: {self.use_base_llm_for_execution}")

        logger.info(f"    - Embeddings Model: {self.embeddings_provider}/{self.embeddings_model}")
        logger.info(f"    - Vector Store Provider: {self.vector_store_provider}")
        logger.info(f"    - AI SDK Host: {self.ai_sdk_host}")
        logger.info(f"    - AI SDK Data Dir (logs, cache, reports...): {self.data_dir}")
        logger.info(f"    - Using SSL: {self.ssl_enabled}")
        logger.info(f"    - DeepQuery: {'enabled' if self.deepquery_enabled else 'disabled'}")
        logger.info(f"    - Reporting: {self.reporting_enabled}")
        logger.info(f"    - Report Max Size: {self.report_max_size}mb")
        logger.info(f"    - Report Max Files: {'unlimited' if self.report_max_files <= 0 else self.report_max_files}")
        logger.info(f"    - Feedback: {self.effective_feedback_enabled}")
        logger.info(f"    - Auto Graph: {self.auto_graph}")
        logger.info(f"    - User can edit LLM settings: {self.user_edit_llm}")
        logger.info(f"    - Data Marketplace URL (for direct view linking): {self.data_marketplace_url}")


# --- Management of Multiple Configurations ---

# Dictionary to store configuration instances by name
_configs = {}


def get_config(chatbot_name="global", config_dict=None):
    """
    Get or create a specific configuration instance.
    If config_dict is provided, it updates/re-initializes that specific instance.
    """
    global _configs
    if chatbot_name not in _configs or config_dict is not None:
        _configs[chatbot_name] = ChatbotConfig(config_dict)
    return _configs[chatbot_name]


def init_agents(agents_config=None):
    """
    Initializes multiple configurations if a list is provided.
    If the list is empty or None, it initializes the 'global' config from environment variables.
    """
    if agents_config is None:
        agents_config = []

    global _configs

    _configs["global"] = ChatbotConfig()
    for cfg_dict in agents_config:
        agent_id = cfg_dict.get("id")
        _configs[agent_id] = ChatbotConfig(cfg_dict)

    return _configs.get("global") or next(iter(_configs.values()))


def setup_agents_directories():
    global _configs

    for chatbot in _configs.values():
        setup_directory(chatbot.reports_folder)


def get_llm(chatbot_id):
    """
    Get the initialized LLM model for a chatbot configuration.
    """
    global _configs
    _configs.get(chatbot_id)
    return _configs.get(chatbot_id).llm


def log_agents_config(logger):
    global _configs
    for chatbot in _configs.values():
        chatbot.log_config(logger)


def get_config_reports_directory(chatbot_id):
    global _configs
    return _configs.get(chatbot_id).reports_folder


def get_agents_metadata_by_user(username) -> list:
    """
    Returns a list of dictionaries containing the basic metadata
    for the initialized chatbots that a user has access to.

    Args:
        username (str): The identifier of the user.

    Returns:
        list: A list of dicts with the metadata of the allowed agents.
    """
    global _configs
    metadata_list = []

    for bot_id, config in _configs.items():
        if config.allowed_users is None or username in config.allowed_users:
            metadata_list.append({
                "id": config.id,
                "name": config.name,
                "description": config.description,
                "isGlobal": config.is_global,
                "icon": config.icon
            })

    return metadata_list
