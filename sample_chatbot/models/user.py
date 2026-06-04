"""
Contains the User class for Flask-Login integration and user state management.
"""

from flask_login import UserMixin

from utils.uniformLLM import UniformLLM
from sample_chatbot.engine.chatbot import ChatbotEngine
from sample_chatbot.extensions import get_unstructured_vector_store
from sample_chatbot.services.kb_registry import get_registry_for

def _normalize_instruction_entry(val):
    if isinstance(val, str):
        return {'ai_sdk': val.strip(), 'chatbot': ''}
    if isinstance(val, dict):
        return {
            'ai_sdk': (val.get('ai_sdk') or '').strip(),
            'chatbot': (val.get('chatbot') or '').strip(),
        }
    return {'ai_sdk': '', 'chatbot': ''}


def _normalize_instruction_map(payload):
    if payload is None:
        return {}
    if isinstance(payload, str):
        return {'global': _normalize_instruction_entry(payload)}
    if not isinstance(payload, dict):
        return {}
    keys = set(payload.keys())
    if keys <= {'ai_sdk', 'chatbot'}:
        return {'global': _normalize_instruction_entry(payload)}
    out = {}
    for agent_id, val in payload.items():
        out[agent_id] = _normalize_instruction_entry(val)
    return out

class User(UserMixin):
    """User model for Flask-Login integration."""

    def __init__(self, username, password, config):
        self.id = username
        self.password = password
        self._config = config

        # Security and access
        self.roles = []
        self.is_admin = False
        self.legacy_permissions_endpoint = False

        # Chatbot
        self.agent_id = config.id
        self.chatbot = None
        self.custom_instructions_map = {}
        self.user_details = ""
        self.thread_id = None

        # Synced resources
        self.synced_resources = {}
        self.partial_resources = {}
        self.user_sync_permissions = True

        # LLM preferences for different components
        self.chatbot_llm_preferences = {}
        self.ai_sdk_base_llm_preferences = {}
        self.ai_sdk_thinking_llm_preferences = {}
        self.use_base_llm_for_execution = config.use_base_llm_for_execution

        # General AI SDK preferences
        self.check_ambiguity = config.check_ambiguity

        # Cached AI SDK configuration (populated at login from /getAISDKInfo)
        self.ai_sdk_info = None

    # ---------- KB accessors (registry-backed) ----------

    def _registry(self):
        return get_registry_for(self._config)

    @property
    def chatbot_vector_store(self):
        """The single shared chatbot vector store."""
        return get_unstructured_vector_store(self._config)

    # Legacy alias used by some downstream code paths.
    @property
    def unstructured_vector_store(self):
        return self.chatbot_vector_store

    @property
    def active_csv_sources(self):
        """Collections this user has switched on for the *current* agent."""
        return self._registry().active_for_user(self.id, self._config.id)

    @property
    def unstructured_vector_store_description(self):
        registry = self._registry()
        lines = []
        for name in self.active_csv_sources:
            meta = registry.get_collection(name) or {}
            lines.append(f"   - {name} => {meta.get('description', '')}")
        return "\n".join(lines) + ("\n" if lines else "")

    @property
    def kb_collections_map(self):
        """{collection_name: description} for the collections this user has active."""
        registry = self._registry()
        out = {}
        for name in self.active_csv_sources:
            meta = registry.get_collection(name) or {}
            out[name] = meta.get("description", "")
        return out

    def set_active_csvs(self, active_csvs):
        """Replace this (user, current-agent)'s full active-collection set.

        The cached chatbot is intentionally left in place so the user's current
        conversation (history, system prompt, kb snapshot) keeps working.
        The updated collection set will be picked up the next time the chatbot
        is rebuilt (e.g. when the user starts a new chat via set_agent_config).
        """
        if active_csvs is None:
            return
        self._registry().set_active_set(self.id, self._config.id, active_csvs)

    # ---------- the rest of the user model ----------

    def _effective_ai_sdk_instructions(self):
        if self.agent_id in self.custom_instructions_map:
            return (
                (self.custom_instructions_map[self.agent_id].get("ai_sdk") or "").strip()
            )
        return (getattr(self._config, "custom_instructions_ai_sdk", None) or "").strip()

    def _effective_chatbot_instructions(self):
        if self.agent_id in self.custom_instructions_map:
            return (
                (self.custom_instructions_map[self.agent_id].get("chatbot") or "").strip()
            )
        return (getattr(self._config, "custom_instructions_chatbot", None) or "").strip()

    def set_custom_instructions(self, user_details='', custom_instructions=None):
        """Update user profile details and optional per-agent custom instruction map."""
        self.user_details = user_details
        if custom_instructions is not None:
            self.custom_instructions_map = _normalize_instruction_map(custom_instructions)
        self.chatbot = None

    def merge_custom_instructions_for_agent(self, agent_id, patch):
        """Merge a single agent's ai_sdk / chatbot overlay (used when switching agents)."""
        if patch is None:
            return
        entry = _normalize_instruction_entry(patch)
        merged = dict(self.custom_instructions_map)
        merged[agent_id] = entry
        self.custom_instructions_map = merged
        self.chatbot = None

    def update_llm_preferences(self, llm_settings):
        """Updates LLM preferences from a dictionary containing the configurations."""
        def validate_temperature(temp):
            if temp is not None and temp != '':
                temp_float = float(temp)
                if not (0.0 <= temp_float <= 2.0):
                    raise ValueError("Temperature must be between 0.0 and 2.0")
                return temp_float
            return None

        def validate_max_tokens(tokens):
            if tokens is not None and tokens != '':
                tokens_int = int(tokens)
                if not (1024 <= tokens_int <= 20000):
                    raise ValueError("Max tokens must be between 1024 and 20000")
                return tokens_int
            return None

        def parse_and_validate(llm_data):
            if not llm_data or not any(llm_data.values()):
                return None
            prefs = {
                'provider': llm_data.get('provider') or None,
                'model': llm_data.get('model') or None,
                'temperature': validate_temperature(llm_data.get('temperature')),
                'max_tokens': validate_max_tokens(llm_data.get('max_tokens'))
            }
            return {k: v for k, v in prefs.items() if v is not None}

        chatbot_prefs = parse_and_validate(llm_settings.get('chatbot_llm'))
        if chatbot_prefs is not None:
            self.chatbot_llm_preferences = chatbot_prefs

        base_prefs = parse_and_validate(llm_settings.get('ai_sdk_base_llm'))
        if base_prefs is not None:
            self.ai_sdk_base_llm_preferences = base_prefs

        thinking_prefs = parse_and_validate(llm_settings.get('ai_sdk_thinking_llm'))
        if thinking_prefs is not None:
            self.ai_sdk_thinking_llm_preferences = thinking_prefs

        check_ambiguity = llm_settings.get('check_ambiguity')
        if check_ambiguity is not None:
           self.check_ambiguity = bool(check_ambiguity)

        use_base_llm_for_execution = llm_settings.get('use_base_llm_for_execution')
        if use_base_llm_for_execution is not None:
            self.use_base_llm_for_execution = bool(use_base_llm_for_execution)


    def get_or_create_chatbot(self):
        if not self.chatbot:
            chatbot_llm = self.get_chatbot_llm()

            base_prefs = self.ai_sdk_base_llm_preferences or {}
            base_provider = base_prefs.get('provider') or getattr(self._config, 'ai_sdk_base_llm_provider', None)
            base_model = base_prefs.get('model') or getattr(self._config, 'ai_sdk_base_llm_model', None)
            base_temp = base_prefs.get('temperature') if base_prefs.get('temperature') is not None else getattr(
                self._config, 'ai_sdk_base_llm_temperature', None)
            base_tokens = base_prefs.get('max_tokens') or getattr(self._config, 'ai_sdk_base_llm_max_tokens', None)

            ai_sdk_llm_params = {}
            if base_provider:
                ai_sdk_llm_params['llm_provider'] = base_provider
            if base_model:
                ai_sdk_llm_params['llm_model'] = base_model
            if base_temp is not None:
                ai_sdk_llm_params['llm_temperature'] = base_temp
            if base_tokens:
                ai_sdk_llm_params['llm_max_tokens'] = base_tokens

            thinking_prefs = self.ai_sdk_thinking_llm_preferences or {}
            thinking_provider = thinking_prefs.get('provider') or getattr(self._config, 'ai_sdk_thinking_llm_provider', None)
            thinking_model = thinking_prefs.get('model') or getattr(self._config, 'ai_sdk_thinking_llm_model', None)
            thinking_temp = thinking_prefs.get('temperature') if thinking_prefs.get(
                'temperature') is not None else getattr(self._config, 'ai_sdk_thinking_llm_temperature', None)
            thinking_tokens = thinking_prefs.get('max_tokens') or getattr(self._config, 'ai_sdk_thinking_llm_max_tokens', None)

            thinking_llm_params = {}
            if thinking_provider:
                thinking_llm_params['thinking_llm_provider'] = thinking_provider
            if thinking_model:
                thinking_llm_params['thinking_llm_model'] = thinking_model
            if thinking_temp is not None:
                thinking_llm_params['thinking_llm_temperature'] = thinking_temp
            if thinking_tokens:
                thinking_llm_params['thinking_llm_max_tokens'] = thinking_tokens

            ai_sdk_params = {
                **ai_sdk_llm_params,
                **thinking_llm_params,
                'check_ambiguity': self.check_ambiguity,
                'execution_model': 'base' if self._config.use_base_llm_for_execution else 'thinking'
            }

            data_agent_limit_max = self.ai_sdk_info['vql_execute_rows_limit'] if self.ai_sdk_info else 10000
            ai_sdk_params['vql_execute_rows_limit'] = data_agent_limit_max
            deep_query_allowed = self.ai_sdk_info.get("can_use_deepquery", True) if self.ai_sdk_info else True
            deepquery_enabled = self._config.deepquery_enabled and deep_query_allowed

            unstructured_mode_allowed = self._config.is_unstructured_mode_allowed_for_user(
                username=self.id,
                roles=self.roles,
                is_admin=self.is_admin,
                legacy_permissions_endpoint=self.legacy_permissions_endpoint
            )

            self.chatbot = ChatbotEngine(
                llm=chatbot_llm,
                system_prompt=self._config.system_prompt,
                api_host=self._config.ai_sdk_host,
                username=self.id,
                password=self.password,
                vector_store_provider=self._config.vector_store_provider if unstructured_mode_allowed else None,
                vector_store=self.chatbot_vector_store if unstructured_mode_allowed else None,
                user_details=self.user_details,
                enable_deepquery=deepquery_enabled,
                deep_query_guidance=self._config.deepquery_guidance,
                ai_sdk_custom_instructions=self._effective_ai_sdk_instructions(),
                chatbot_custom_instructions=self._effective_chatbot_instructions(),
                thread_id=self.thread_id,
                verify_ssl=self._config.ai_sdk_verify_ssl,
                ai_sdk_params=ai_sdk_params,
                data_agent_limit_max=data_agent_limit_max,
                auto_graph=self._config.auto_graph,
                kb_description=self.unstructured_vector_store_description if unstructured_mode_allowed else "",
                active_csv_sources=self.active_csv_sources if unstructured_mode_allowed else None,
                kb_collections=self.kb_collections_map if unstructured_mode_allowed else None,
                timeout=self._config.chatbot_timeout,
            )
        return self.chatbot

    def get_chatbot_llm(self):
        """Get LLM instance for chatbot based on user preferences or global defaults."""
        if self.chatbot_llm_preferences:
            provider = self.chatbot_llm_preferences.get('provider', self._config.llm_provider)
            model = self.chatbot_llm_preferences.get('model', self._config.llm_model)
            temperature = self.chatbot_llm_preferences.get('temperature', self._config.llm_temperature)
            max_tokens = self.chatbot_llm_preferences.get('max_tokens', self._config.llm_max_tokens)

            return UniformLLM(
                provider,
                model,
                temperature=temperature,
                max_tokens=max_tokens
            )
        else:
            return self._config.llm

    def set_agent_config(self, config):
        self._config = config

        self.agent_id = config.id
        self.chatbot = None
        self.user_details = ""
        self.thread_id = None

        self.chatbot_llm_preferences = {}
        self.ai_sdk_base_llm_preferences = {}
        self.ai_sdk_thinking_llm_preferences = {}

        self.check_ambiguity = config.check_ambiguity
        self.use_base_llm_for_execution = config.use_base_llm_for_execution
