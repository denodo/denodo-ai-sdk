"""
Contains the User class for Flask-Login integration and user state management.
"""

import time
import logging
import os

from flask_login import UserMixin

from utils.uniformLLM import UniformLLM
from utils.uniformEmbeddings import UniformEmbeddings
from utils.uniformVectorStore import UniformVectorStore
from utils.utils import delete_documents_by_database_name
from sample_chatbot.engine import ChatbotEngine
from sample_chatbot.utils.helpers import setup_user_details
from sample_chatbot.utils.csv_utils import csv_to_documents, validate_csv_path, get_safe_source_name


class User(UserMixin):
    """
    User model for Flask-Login integration.

    Manages user state including:
    - Authentication credentials
    - CSV/knowledge base sources
    - Chatbot instance
    - LLM preferences
    """

    def __init__(self, username, password, config):
        """
        Initialize a new User.

        Args:
            username: User's username
            password: User's password
            config: ChatbotConfig instance
        """
        self.id = username
        self.password = password
        self._config = config

        # Knowledge base (one per user)
        self.unstructured_vector_store = None
        self.unstructured_vector_store_description = ""
        self.csv_sources = {}
        self.active_csv_sources = []
        safe_username = get_safe_source_name(username)
        self._unstructured_index_name = f"unstructured_{safe_username}_chatbot"

        # Chatbot
        self.agent_id = config.id
        self.chatbot = None
        self.denodo_tables = None  # Preview of some of the views the user has access to
        self.custom_instructions = config.custom_instructions
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

        # Initialize custom knowledge base if configured
        self._check_custom_kb()

    def _check_custom_kb(self):
        """Check if custom knowledge base has been configured via environment with CHATBOT_UNSTRUCTURED_INDEX"""
        if self._config.unstructured_index and self._config.unstructured_description:
            self.unstructured_vector_store_description = self._config.unstructured_description
            embeddings = UniformEmbeddings(
                self._config.embeddings_provider,
                self._config.embeddings_model
            ).model
            self.unstructured_vector_store = UniformVectorStore(
                index_name=self._config.unstructured_index,
                provider=self._config.vector_store_provider,
                embeddings=embeddings
            )

    def _get_or_create_unstructured_vector_store(self):
        """
        Get or create the shared unstructured vector store for this user.

        All CSV sources are stored in a single vector store per user,
        with documents filtered by database_name metadata.

        Returns:
            UniformVectorStore instance
        """
        if self.unstructured_vector_store is None:
            logging.info(
                f"[User] Creating unstructured vector store for user '{self.id}': {self._unstructured_index_name}")
            embeddings = UniformEmbeddings(
                self._config.embeddings_provider,
                self._config.embeddings_model
            ).model
            self.unstructured_vector_store = UniformVectorStore(
                provider=self._config.vector_store_provider,
                embeddings=embeddings,
                index_name=self._unstructured_index_name
            )
        return self.unstructured_vector_store

    def add_csv_source(self, source_name, csv_file_path, description, delimiter=";", auto_activate=True):
        """
        Add a new CSV source to the user's knowledge base.

        All CSV sources are stored in a single vector store per user.
        Documents are tagged with database_name = source_name for filtering.

        Args:
            source_name: Name identifier for this CSV source
            csv_file_path: Path to the CSV file
            description: Description of the CSV contents
            delimiter: CSV delimiter character
            auto_activate: Whether to activate the source immediately

        Returns:
            dict with success status and metadata, or error message
        """
        # Validate the CSV path
        valid, error = validate_csv_path(csv_file_path)
        if not valid:
            return {"success": False, "error": error}

        # Convert CSV to documents (with source_name as database_name for filtering)
        csv_documents = csv_to_documents(csv_file_path, delimiter, source_name=source_name)
        if not csv_documents:
            return {"success": False, "error": "Failed to create documents from CSV"}

        vector_store = self._get_or_create_unstructured_vector_store()

        # If source already exists, delete old documents first
        if source_name in self.csv_sources:
            logging.info(f"[User] Replacing existing CSV source '{source_name}', deleting old documents")
            delete_documents_by_database_name(vector_store, [source_name])

        logging.info(f"[User] Adding {len(csv_documents)} documents from '{source_name}' to vector store")
        vector_store.add_views(csv_documents, parallel=True)

        # Store the metadata
        csv_metadata = {
            "source_name": source_name,
            "path": csv_file_path,
            "description": description,
            "delimiter": delimiter,
            "document_count": len(csv_documents),
            "last_vectorized": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "active": auto_activate
        }

        self.csv_sources[source_name] = csv_metadata

        # Update active sources list
        if auto_activate and source_name not in self.active_csv_sources:
            self.active_csv_sources.append(source_name)

        # Update combined description
        self._update_csv_description()

        # Reset chatbot to pick up new knowledge base
        self.chatbot = None

        return {
            "success": True,
            "source_name": source_name,
            "metadata": {
                "source_name": source_name,
                "path": csv_file_path,
                "description": description,
                "delimiter": delimiter,
                "document_count": len(csv_documents),
                "last_vectorized": csv_metadata["last_vectorized"],
                "active": csv_metadata["active"]
            }
        }

    def remove_csv_source(self, source_name, delete_file=False):
        """
        Remove a CSV source from the user's knowledge base.

        Deletes documents from the vector store by database_name filter.
        """
        if source_name not in self.csv_sources:
            return {"success": False, "error": f"Source '{source_name}' not found"}

        csv_meta = self.csv_sources[source_name]

        if self.unstructured_vector_store:
            logging.info(f"[User] Deleting documents for source '{source_name}' from vector store")
            deleted_count = delete_documents_by_database_name(self.unstructured_vector_store, [source_name])
            logging.info(f"[User] Deleted {deleted_count} documents for source '{source_name}'")

        # Optionally delete the file
        if delete_file and csv_meta.get("path"):
            try:
                if os.path.exists(csv_meta["path"]):
                    os.remove(csv_meta["path"])
            except Exception as e:
                logging.warning(f"Could not delete CSV file: {e}")

        # Remove from sources
        del self.csv_sources[source_name]

        # Remove from active sources
        if source_name in self.active_csv_sources:
            self.active_csv_sources.remove(source_name)

        # Update combined description
        self._update_csv_description()

        # Reset chatbot
        self.chatbot = None

        return {"success": True}

    def set_csv_active(self, source_name, active):
        """
        Activate or deactivate a CSV source.

        Active sources are included in knowledge_query searches via database_name filter.
        """
        if source_name not in self.csv_sources:
            return {"success": False, "error": f"Source '{source_name}' not found"}

        self.csv_sources[source_name]["active"] = active

        if active and source_name not in self.active_csv_sources:
            self.active_csv_sources.append(source_name)
        elif not active and source_name in self.active_csv_sources:
            self.active_csv_sources.remove(source_name)

        # Update combined description
        self._update_csv_description()

        # Reset chatbot to pick up changes
        self.chatbot = None

        return {"success": True, "active": active}

    def update_csv_description(self, source_name, description):
        """Update the description of a CSV source."""
        if source_name not in self.csv_sources:
            return {"success": False, "error": f"Source '{source_name}' not found"}

        if not description or not description.strip():
            return {"success": False, "error": "Description cannot be empty"}

        self.csv_sources[source_name]["description"] = description.strip()

        # Update combined description
        self._update_csv_description()

        # Reset chatbot to pick up changes
        self.chatbot = None

        return {"success": True, "description": description.strip()}

    def get_csv_sources_metadata(self):
        """Get metadata for all CSV sources."""
        result = []
        for name, meta in self.csv_sources.items():
            # Validate that path still exists
            path_valid, _ = validate_csv_path(meta.get("path", ""))
            result.append({
                "source_name": name,
                "path": meta["path"],
                "description": meta["description"],
                "delimiter": meta["delimiter"],
                "document_count": meta.get("document_count", 0),
                "last_vectorized": meta.get("last_vectorized", ""),
                "active": meta["active"],
                "path_valid": path_valid
            })
        return result

    def restore_csv_sources(self, csv_configs):
        """
        Checks if documents already exist in vector store:
        - If documents exist: restore metadata without re-vectorizing
        - If documents don't exist and file exists: skip (will appear as "scanned")
        - If file doesn't exist: mark as failed

        Returns:
            dict with "restored", "failed", and "skipped" lists
        """
        restored = []
        failed = []
        skipped = []

        # Get or create vector store first (needed for existence checks)
        vector_store = self._get_or_create_unstructured_vector_store()

        for config in csv_configs:
            source_name = config.get("source_name")
            path = config.get("path")
            description = config.get("description", "")
            delimiter = config.get("delimiter", ";")
            active = config.get("active", True)

            if not source_name or not path:
                logging.warning("[User] Skipping invalid config: missing source_name or path")
                continue

            # Check if documents already exist in vector store by database_name
            logging.debug(f"[User] Checking existence of source '{source_name}' in vector store")
            documents_exist = vector_store.check_existence(
                view_ids=None,
                database_names=[source_name]
            )

            if documents_exist:
                # Documents exist - restore metadata without re-vectorizing
                logging.info(f"[User] Source '{source_name}' already exists in vector store, restoring metadata only")

                # Validate path still exists
                path_valid, error = validate_csv_path(path)
                if not path_valid:
                    logging.warning(
                        f"[User] Source '{source_name}' documents exist in vector store, but CSV file not found at path: {error}")

                csv_metadata = {
                    "source_name": source_name,
                    "path": path,
                    "description": description,
                    "delimiter": delimiter,
                    "document_count": config.get("document_count", 0),
                    "last_vectorized": config.get("last_vectorized", ""),
                    "active": active
                }

                self.csv_sources[source_name] = csv_metadata

                if active:
                    self.active_csv_sources.append(source_name)

                restored.append(source_name)

            else:
                # Documents don't exist in vector store
                # Check if file still exists on disk
                path_valid, error = validate_csv_path(path)

                if path_valid:
                    # File exists but not vectorized - skip it, will appear as "scanned"
                    logging.info(
                        f"[User] Source '{source_name}' file exists but not vectorized, skipping (will appear as scanned)")
                    skipped.append({
                        "source_name": source_name,
                        "reason": "File exists but not vectorized",
                        "path": path
                    })
                else:
                    # File doesn't exist - mark as failed
                    logging.warning(f"[User] Source '{source_name}' file not found: {error}")
                    failed.append({
                        "source_name": source_name,
                        "error": error,
                        "path": path
                    })

        # Update combined description
        self._update_csv_description()

        # Reset chatbot to pick up restored sources
        self.chatbot = None

        return {
            "restored": restored,
            "failed": failed,
            "skipped": skipped
        }

    def _update_csv_description(self):
        """Update the combined CSV description for the chatbot system prompt."""
        if self.active_csv_sources:
            self.unstructured_vector_store_description = ""
            for active_csv_source in self.active_csv_sources:
                self.unstructured_vector_store_description += f"   - {active_csv_source} => {self.csv_sources[active_csv_source]['description']}\n"
        elif not self.csv_sources:
            # No CSV sources, check for environment-configured KB
            self.unstructured_vector_store_description = ""
            self._check_custom_kb()
        else:
            self.unstructured_vector_store_description = ""

    def set_custom_instructions(self, user_details='', custom_instructions=''):
        """Update custom instructions with user details."""
        self.custom_instructions = (
                self._config.custom_instructions + "\n" + custom_instructions + "\n" + setup_user_details(
                user_details, username=self.id
            )).strip()
        self.user_details = user_details
        # Reset the chatbot to create a new one with updated context
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
            # Remove None values
            return {k: v for k, v in prefs.items() if v is not None}

        # Update if valid data is provided
        chatbot_prefs = parse_and_validate(llm_settings.get('chatbot_llm'))
        if chatbot_prefs is not None:
            self.chatbot_llm_preferences = chatbot_prefs

        base_prefs = parse_and_validate(llm_settings.get('ai_sdk_base_llm'))
        if base_prefs is not None:
            self.ai_sdk_base_llm_preferences = base_prefs

        thinking_prefs = parse_and_validate(llm_settings.get('ai_sdk_thinking_llm'))
        if thinking_prefs is not None:
            self.ai_sdk_thinking_llm_preferences = thinking_prefs

        # Update check_ambiguity preference
        check_ambiguity = llm_settings.get('check_ambiguity')
        if check_ambiguity is not None:
           self.check_ambiguity = bool(check_ambiguity)

        # Update use_base_llm_for_execution preference
        use_base_llm_for_execution = llm_settings.get('use_base_llm_for_execution')
        if use_base_llm_for_execution is not None:
            self.use_base_llm_for_execution = bool(use_base_llm_for_execution)


    def get_or_create_chatbot(self):
        """
        Get existing chatbot or create a new one.

        Returns:
            ChatbotEngine instance
        """
        if not self.chatbot:
            # Use user's chatbot LLM preferences or fall back to global defaults
            chatbot_llm = self.get_chatbot_llm()

            # Prepare LLM parameters for AI SDK tools
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
            thinking_provider = thinking_prefs.get('provider') or getattr(self._config, 'ai_sdk_thinking_llm_provider',
                                                                          None)
            thinking_model = thinking_prefs.get('model') or getattr(self._config, 'ai_sdk_thinking_llm_model', None)
            thinking_temp = thinking_prefs.get('temperature') if thinking_prefs.get(
                'temperature') is not None else getattr(self._config, 'ai_sdk_thinking_llm_temperature', None)
            thinking_tokens = thinking_prefs.get('max_tokens') or getattr(self._config,
                                                                          'ai_sdk_thinking_llm_max_tokens', None)

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

            data_query_limit_max = self.ai_sdk_info['vql_execute_rows_limit']
            ai_sdk_params['vql_execute_rows_limit'] = data_query_limit_max

            self.chatbot = ChatbotEngine(
                llm=chatbot_llm,
                system_prompt=self._config.system_prompt,
                api_host=self._config.ai_sdk_host,
                username=self.id,
                password=self.password,
                vector_store_provider= self._config.vector_store_provider if self._config.unstructured_mode else None,
                vector_store=self.unstructured_vector_store if self._config.unstructured_mode else None,
                denodo_tables=self.denodo_tables,
                user_details=self.user_details,
                enable_deepquery=self._config.deepquery_enabled,
                deep_query_guidance=self._config.deepquery_guidance,
                custom_instructions=self.custom_instructions,
                thread_id=self.thread_id,
                verify_ssl=self._config.ai_sdk_verify_ssl,
                ai_sdk_params=ai_sdk_params,
                data_query_limit_max=data_query_limit_max,
                auto_graph=self._config.auto_graph,
                kb_description=self.unstructured_vector_store_description,
                active_csv_sources=self.active_csv_sources,
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
            # Use chatbot configuration LLM instance
            return self._config.llm

    def set_agent_config(self, config):

        self._config = config

        # Chatbot
        self.agent_id = config.id
        self.chatbot = None
        self.denodo_tables = None  # Preview of some of the views the user has access to
        self.custom_instructions = config.custom_instructions
        self.user_details = ""
        self.thread_id = None

        self.chatbot_llm_preferences = {}
        self.ai_sdk_base_llm_preferences = {}
        self.ai_sdk_thinking_llm_preferences = {}

        self.check_ambiguity = config.check_ambiguity
        self.use_base_llm_for_execution = config.use_base_llm_for_execution
