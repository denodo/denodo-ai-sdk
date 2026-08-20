import os

from sample_chatbot.engine.prompts import CHATBOT_SYSTEM_PROMPT
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
        self.allowed_roles = config_dict.get('allowed_roles', None)

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

        # Database Configuration
        self.database_provider = os.getenv('CHATBOT_DATABASE_PROVIDER', 'SQLite').upper()

        # System Prompts (from engine/prompts.py)
        self.system_prompt = CHATBOT_SYSTEM_PROMPT

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

        # Default input method for the question form: 'enter' submits on Enter,
        # 'ctrl_enter' submits on Ctrl+Enter (plain Enter is ignored), which is
        # convenient for IME-based languages where Enter confirms the conversion.
        # Users can override this default from the User Profile modal.
        input_method = os.getenv('CHATBOT_INPUT_METHOD', 'enter').strip().lower()
        self.input_method = input_method if input_method in ('enter', 'ctrl_enter') else 'enter'

        # Parse allowed users/roles for unstructured mode from environment variables
        allowed_csv_users_env = os.getenv('CHATBOT_ALLOWED_UNSTRUCTURED_USERS', '')
        allowed_csv_roles_env = os.getenv('CHATBOT_ALLOWED_UNSTRUCTURED_ROLES', '')

        self.allowed_unstructured_users = [
            u.strip() for u in allowed_csv_users_env.split(',') if u.strip()
        ] if allowed_csv_users_env else []

        self.allowed_unstructured_roles = [
            r.strip() for r in allowed_csv_roles_env.split(',') if r.strip()
        ] if allowed_csv_roles_env else []

        # Parse allowed users/roles for skill management (create/edit). Reading
        # skills is open to everyone; creating and editing them is restricted.
        # By default (no users/roles configured) only global admins may manage skills.
        allowed_skill_users_env = os.getenv('CHATBOT_ALLOWED_SKILL_USERS', '')
        allowed_skill_roles_env = os.getenv('CHATBOT_ALLOWED_SKILL_ROLES', '')

        self.allowed_skill_users = [
            u.strip() for u in allowed_skill_users_env.split(',') if u.strip()
        ] if allowed_skill_users_env else []

        self.allowed_skill_roles = [
            r.strip() for r in allowed_skill_roles_env.split(',') if r.strip()
        ] if allowed_skill_roles_env else []

        # System skills that apply to this agent. Specialized agents can list
        # skill names in their YAML (settings.skills); None means all system
        # skills apply (the global agent's default). Personal skills always apply.
        agent_skills = settings.get('skills', None)
        self.agent_skills = list(agent_skills) if agent_skills is not None else None

        # Skills force-deactivated by feature flags. When DeepQuery is disabled
        # for this agent (settings.deepquery_enabled / CHATBOT_DEEPQUERY), its
        # skill is permanently deactivated: excluded from the agent context,
        # not user-toggleable, and not readable via the read_skill tool.
        self.disabled_skills = set() if self.deepquery_enabled else {"deepquery"}

        # Knowledge base collection names declared by this agent's YAML
        # (like `skills`, a plain list of names). They are always active for
        # every user of the agent and must already exist in the vector store;
        # the agent is not usable while any is missing. Descriptions come from
        # the collections themselves (set in the Knowledge Base Manager).
        self.knowledge_bases = [str(name) for name in settings.get('knowledge_bases', []) or []]

        # Reporting Configuration
        if self.data_dir != ".":
            self.reports_folder = os.path.join(self.data_dir, "reports", self.id)
        else:
            self.reports_folder = f"reports/{self.id}"

        self.report_max_size = get_config_value(settings, 'report_max_size', 'CHATBOT_REPORT_MAX_SIZE', '10', int)
        self.report_max_files = get_config_value(settings, 'report_max_files', 'CHATBOT_REPORT_MAX_FILES', '10', int)

        # AI SDK Configuration
        self.ai_sdk_host = os.getenv('AI_SDK_URL', 'http://localhost:8008')
        self.ai_sdk_username = os.getenv('AI_SDK_USERNAME')
        self.ai_sdk_password = os.getenv('AI_SDK_PASSWORD')
        self.ai_sdk_verify_ssl = bool(int(os.getenv('AI_SDK_VERIFY_SSL', '0')))
        self.chatbot_timeout = int(os.getenv('CHATBOT_TIMEOUT', '1200'))

        # External Services
        self.data_marketplace_url = os.getenv("CHATBOT_DATA_MARKETPLACE_URL")

        # custom_instructions: custom agents read chatbot/ai_sdk from YAML. General Chat reads env variable CHATBOT_CUSTOM_INSTRUCTIONS.
        ci = settings.get('custom_instructions')
        if not isinstance(ci, dict):
            ci = {}
        self.custom_instructions_ai_sdk = (ci.get('ai_sdk') or '').strip()
        yaml_chatbot = (ci.get('chatbot') or '').strip()
        env_general_chatbot = (os.getenv('CHATBOT_CUSTOM_INSTRUCTIONS') or '').strip()
        if self.is_global:
            self.custom_instructions_chatbot = yaml_chatbot or env_general_chatbot
        else:
            self.custom_instructions_chatbot = yaml_chatbot

        user_edit_instructions = settings.get("user_edit_instructions")
        if user_edit_instructions is None:
            user_edit_instructions = os.getenv("CHATBOT_USER_EDIT_INSTRUCTIONS", "1")
        if isinstance(user_edit_instructions, bool):
            self.user_edit_instructions = user_edit_instructions
        else:
            self.user_edit_instructions = bool(int(user_edit_instructions))

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

    def _evaluate_restrictions(self, username, roles, is_admin, legacy_permissions_endpoint, allowed_users, allowed_roles):
        """
        Internal generic helper to evaluate user and role access restrictions.
        """
        if roles is None:
            roles = []

        if not legacy_permissions_endpoint and is_admin:
            return True

        # Check if restrictions are explicitly configured
        has_user_restriction = allowed_users is not None and len(allowed_users) > 0
        has_role_restriction = allowed_roles is not None and len(allowed_roles) > 0

        # If no specific restrictions are set, everyone is allowed
        if not has_user_restriction and not has_role_restriction:
            return True

        # User-based whitelist check
        if has_user_restriction and username in allowed_users:
            return True

        # Role-based whitelist check
        if not legacy_permissions_endpoint and has_role_restriction:
            if any(r in allowed_roles for r in roles):
                return True

        # Default deny if restrictions exist but no match was found
        return False

    def is_user_allowed(self, username, roles=None, is_admin=False, legacy_permissions_endpoint=False):
        """
        Evaluates if a user has access to this agent.
        """
        return self._evaluate_restrictions(
            username=username,
            roles=roles,
            is_admin=is_admin,
            legacy_permissions_endpoint=legacy_permissions_endpoint,
            allowed_users=self.allowed_users,
            allowed_roles=self.allowed_roles
        )

    def is_unstructured_mode_allowed_for_user(self, username, roles=None, is_admin=False, legacy_permissions_endpoint=False):
        """
        Evaluates if a specific user has permission to use the unstructured (CSV upload) mode.
        """
        # If unstructured mode is fully disabled, deny access to everyone.
        if not self.unstructured_mode:
            return False

        return self._evaluate_restrictions(
            username=username,
            roles=roles,
            is_admin=is_admin,
            legacy_permissions_endpoint=legacy_permissions_endpoint,
            allowed_users=self.allowed_unstructured_users,
            allowed_roles=self.allowed_unstructured_roles
        )

    def is_skill_management_allowed_for_user(self, username, roles=None, is_admin=False, legacy_permissions_endpoint=False):
        """
        Evaluates if a user may create or edit skills.

        Reading skills is open to everyone; managing (creating/editing) them is
        restricted. Global admins are always allowed. If specific users/roles are
        configured, they are allowed too. If nothing is configured, only admins
        are allowed (admin-only default).
        """
        if roles is None:
            roles = []

        if not legacy_permissions_endpoint and is_admin:
            return True

        if self.allowed_skill_users and username in self.allowed_skill_users:
            return True

        if not legacy_permissions_endpoint and self.allowed_skill_roles:
            if any(r in self.allowed_skill_roles for r in roles):
                return True

        return False

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
        logger.info(f"    - Database Provider (History): {self.database_provider}")
        logger.info(f"    - AI SDK Host: {self.ai_sdk_host}")
        logger.info(f"    - AI SDK Data Dir (logs, cache, reports...): {self.data_dir}")
        logger.info(f"    - Chatbot Timeout: {self.chatbot_timeout}s")
        logger.info(f"    - Using SSL: {self.ssl_enabled}")
        logger.info(f"    - DeepQuery: {'enabled' if self.deepquery_enabled else 'disabled'}")
        logger.info(f"    - Reporting: {self.reporting_enabled}")
        logger.info(f"    - Report Max Size: {self.report_max_size}mb")
        logger.info(f"    - Report Max Files: {'unlimited' if self.report_max_files <= 0 else self.report_max_files}")
        logger.info(f"    - Feedback: {self.effective_feedback_enabled}")
        logger.info(f"    - Auto Graph: {self.auto_graph}")
        logger.info(f"    - Input Method: {self.input_method}")
        logger.info(f"    - User can edit LLM settings: {self.user_edit_llm}")
        logger.info(f"    - Data Marketplace URL (for direct view linking): {self.data_marketplace_url}")

        skill_access_msg = []
        if self.allowed_skill_roles:
            skill_access_msg.append(f"Roles: {self.allowed_skill_roles}")
        if self.allowed_skill_users:
            skill_access_msg.append(f"Users: {self.allowed_skill_users}")
        if skill_access_msg:
            logger.info(f"    - Skill Management: Admins + [{', '.join(skill_access_msg)}]")
        else:
            logger.info("    - Skill Management: Admins only")

        if self.agent_skills is not None:
            logger.info(f"    - Agent System Skills: {self.agent_skills}")

        if self.knowledge_bases:
            logger.info(f"    - Agent Knowledge Bases (always active): {self.knowledge_bases}")

        if not self.unstructured_mode:
            logger.info("    - Unstructured Mode (CSV): Disabled globally")
        else:
            access_msg = []
            if self.allowed_unstructured_roles:
                access_msg.append(f"Roles: {self.allowed_unstructured_roles}")
            if self.allowed_unstructured_users:
                access_msg.append(f"Users: {self.allowed_unstructured_users}")

            if access_msg:
                logger.info(f"    - Unstructured Mode (CSV): Enabled for [{', '.join(access_msg)}]")
            else:
                logger.info("    - Unstructured Mode (CSV): Enabled globally (no restrictions)")

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

def get_agents_metadata_by_user(username, roles=None, is_admin=False, legacy_permissions_endpoint=False):
    """
    Returns a list of dictionaries containing the basic metadata
    for the initialized chatbots that a user has access to.

    Args:
        username (str): The identifier of the user.
        roles (list): List of roles of the user.
        is_admin (bool): Whether the user is a global administrator.
        legacy_permissions_endpoint (bool): True if the connected Data Marketplace is <= 9.4.1.
                                If True, role-based and admin checks are ignored.

    Returns:
        list: A list of dicts with the metadata of the allowed agents.
    """
    global _configs
    metadata_list = []

    for _, config in _configs.items():
        if config.is_user_allowed(username, roles, is_admin, legacy_permissions_endpoint):
            metadata_list.append({
                "id": config.id,
                "name": config.name,
                "description": config.description,
                "isGlobal": config.is_global,
                "icon": config.icon
            })

    return metadata_list
