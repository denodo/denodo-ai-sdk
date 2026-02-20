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
        self.chatbot = None
        self.denodo_tables = None # Preview of some of the views the user has access to
        self.custom_instructions = ""
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

        # General AI SDK preferences
        self.check_ambiguity = True

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
            logging.info(f"[User] Creating unstructured vector store for user '{self.id}': {self._unstructured_index_name}")
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
                    logging.warning(f"[User] Source '{source_name}' documents exist in vector store, but CSV file not found at path: {error}")

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
                    logging.info(f"[User] Source '{source_name}' file exists but not vectorized, skipping (will appear as scanned)")
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

    def set_custom_instructions(self):
        """Update custom instructions with user details."""
        self.custom_instructions = self.custom_instructions + "\n" + setup_user_details(
            self.user_details, username=self.id
        )
        # Reset the chatbot to create a new one with updated context
        self.chatbot = None

    def get_or_create_chatbot(self, llm):
        """
        Get existing chatbot or create a new one.

        Args:
            llm: Default UniformLLM instance to use if no user preferences

        Returns:
            ChatbotEngine instance
        """
        if not self.chatbot:
            # Use user's chatbot LLM preferences or fall back to global defaults
            chatbot_llm = self._get_chatbot_llm(llm)

            # Prepare LLM parameters for AI SDK tools
            ai_sdk_llm_params = {}

            if self.ai_sdk_base_llm_preferences:
                if self.ai_sdk_base_llm_preferences.get('provider'):
                    ai_sdk_llm_params['llm_provider'] = self.ai_sdk_base_llm_preferences['provider']
                if self.ai_sdk_base_llm_preferences.get('model'):
                    ai_sdk_llm_params['llm_model'] = self.ai_sdk_base_llm_preferences['model']
                if self.ai_sdk_base_llm_preferences.get('temperature') is not None:
                    ai_sdk_llm_params['llm_temperature'] = self.ai_sdk_base_llm_preferences['temperature']
                if self.ai_sdk_base_llm_preferences.get('max_tokens'):
                    ai_sdk_llm_params['llm_max_tokens'] = self.ai_sdk_base_llm_preferences['max_tokens']

            thinking_llm_params = {}
            if self.ai_sdk_thinking_llm_preferences:
                if self.ai_sdk_thinking_llm_preferences.get('provider'):
                    thinking_llm_params['thinking_llm_provider'] = self.ai_sdk_thinking_llm_preferences['provider']
                if self.ai_sdk_thinking_llm_preferences.get('model'):
                    thinking_llm_params['thinking_llm_model'] = self.ai_sdk_thinking_llm_preferences['model']
                if self.ai_sdk_thinking_llm_preferences.get('temperature') is not None:
                    thinking_llm_params['thinking_llm_temperature'] = self.ai_sdk_thinking_llm_preferences['temperature']
                if self.ai_sdk_thinking_llm_preferences.get('max_tokens'):
                    thinking_llm_params['thinking_llm_max_tokens'] = self.ai_sdk_thinking_llm_preferences['max_tokens']

            ai_sdk_params = {
                **ai_sdk_llm_params,
                **thinking_llm_params,
                'check_ambiguity': self.check_ambiguity,
            }

            self.chatbot = ChatbotEngine(
                llm=chatbot_llm,
                llm_response_rows_limit=self._config.llm_response_rows_limit,
                system_prompt=self._config.system_prompt,
                api_host=self._config.ai_sdk_host,
                username=self.id,
                password=self.password,
                vector_store_provider=self._config.vector_store_provider,
                vector_store=self.unstructured_vector_store,
                denodo_tables=self.denodo_tables,
                user_details=self.user_details,
                enable_deepquery=self._config.deepquery_enabled,
                deep_query_guidance=self._config.deepquery_guidance,
                custom_instructions=self.custom_instructions,
                thread_id=self.thread_id,
                verify_ssl=self._config.ai_sdk_verify_ssl,
                ai_sdk_params=ai_sdk_params,
                auto_graph=self._config.auto_graph,
                kb_description=self.unstructured_vector_store_description,
                active_csv_sources=self.active_csv_sources,
            )
        return self.chatbot

    def _get_chatbot_llm(self, default_llm):
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
            # Use global LLM instance
            return default_llm
