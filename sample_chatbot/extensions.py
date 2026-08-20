"""
Flask extensions module.
"""

import logging
import threading

from flask_login import LoginManager

from utils.uniformEmbeddings import UniformEmbeddings
from utils.uniformVectorStore import UniformVectorStore

# Flask-Login setup
login_manager = LoginManager()

# Thread lock for report file operations
report_lock = threading.Lock()

# One shared unstructured vector store for the whole chatbot (across every
# agent). Per-(user, agent) activation lives in the KBRegistry — the store
# itself only holds collection documents and the catalog doc.
UNSTRUCTURED_KB_INDEX_NAME = "unstructured_chatbot_kb"

_unstructured_store = None
_unstructured_store_lock = threading.Lock()

def get_unstructured_vector_store(config):
    """Return (creating on first call) the shared chatbot vector store."""
    global _unstructured_store
    with _unstructured_store_lock:
        if _unstructured_store is not None:
            return _unstructured_store

        logging.info(f"[extensions] Creating shared chatbot vector store '{UNSTRUCTURED_KB_INDEX_NAME}'")
        embeddings = UniformEmbeddings(
            config.embeddings_provider,
            config.embeddings_model,
        ).model
        _unstructured_store = UniformVectorStore(
            provider=config.vector_store_provider,
            embeddings=embeddings,
            index_name=UNSTRUCTURED_KB_INDEX_NAME,
        )
        return _unstructured_store
