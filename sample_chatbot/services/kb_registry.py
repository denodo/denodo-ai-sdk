"""
Knowledge-base registry.

There is exactly one shared vector store for the whole chatbot (all agents). The
catalog of vectorized CSV collections lives in that store under a single
document with id `unstructured_chatbot_config`.

Collection-level state (global, the same regardless of which agent is currently
selected):
- csv_path, description, delimiter, vectorized_columns
- owner, last_vectorized, num_rows
- private (visibility)

Subscription state (which is per-user **and** per-agent):
- active_by_user: {username: [agent_id, ...]} on each collection.
  A user activates a collection for the agent they are currently using; the
  same user may have different active sets on different agents.
"""

import json
import time
import logging
import threading

from langchain_core.documents.base import Document

CONFIG_DOC_ID = "unstructured_chatbot_config"

_registry_singleton = None
_registry_lock = threading.Lock()

def get_registry_for(config):
    """Shared KBRegistry singleton — one per process, NOT per agent.

    `config` is taken from the caller only so we can lazily resolve the shared
    embeddings/vector-store on first use; the registry itself is agent-agnostic.
    """
    from sample_chatbot.extensions import get_unstructured_vector_store

    global _registry_singleton
    with _registry_lock:
        if _registry_singleton is None:
            _registry_singleton = KBRegistry(get_unstructured_vector_store(config))
        return _registry_singleton

class KBRegistry:
    """Reads/writes the catalog document. One instance for the whole chatbot."""

    def __init__(self, vector_store):
        self._store = vector_store
        self._lock = threading.Lock()

    # ---------- low-level persistence ----------

    def _read(self):
        """Return the raw collections dict. Empty dict if not present."""
        results = self._store.search_by_vector(
            self._store.search_vector,
            k=1,
            view_ids=[CONFIG_DOC_ID],
        )
        if not results:
            return {}
        try:
            return json.loads(results[0].metadata.get("config_json") or "{}")
        except (TypeError, ValueError) as e:
            logging.warning(f"[KBRegistry] Could not parse config_json: {e}. Resetting.")
            return {}

    def _write(self, collections):
        """Replace the catalog doc with the given collections dict."""
        try:
            self._store.client.delete(ids=[CONFIG_DOC_ID])
        except Exception as e:
            logging.debug(f"[KBRegistry] delete catalog doc (ignored): {e}")

        doc = Document(
            id=CONFIG_DOC_ID,
            page_content=CONFIG_DOC_ID,
            metadata={
                "view_id": CONFIG_DOC_ID,
                "document_id": CONFIG_DOC_ID,
                "config_json": json.dumps({"collections": collections}),
            },
        )
        self._store.client.add_documents([doc], ids=[CONFIG_DOC_ID])

    # ---------- helpers ----------

    @staticmethod
    def _active_by_user(meta):
        """Always return a dict, regardless of legacy shape."""
        v = meta.get("active_by_user")
        return v if isinstance(v, dict) else {}

    # ---------- read helpers ----------

    def list_collections(self):
        with self._lock:
            data = self._read()
        return data.get("collections", {}) if isinstance(data, dict) else data

    def has_collection(self, name):
        return name in self.list_collections()

    def get_collection(self, name):
        return self.list_collections().get(name)

    def active_for_user(self, username, agent_id):
        """Collections this user has switched on for the given agent."""
        result = []
        for name, meta in self.list_collections().items():
            agents = self._active_by_user(meta).get(username) or []
            if agent_id in agents:
                result.append(name)
        return result

    # ---------- mutations ----------

    def register_collection(self, name, csv_path, description, delimiter,
                            vectorized_columns, owner, num_rows,
                            auto_activate_for=None, auto_activate_agent=None,
                            private=False):
        """Create a collection.

        `auto_activate_for` + `auto_activate_agent` together turn it on for the
        uploader on the agent they were using when they ran the upload.
        """
        with self._lock:
            collections = self._read().get("collections", {})
            active_by_user = {}
            if auto_activate_for and auto_activate_agent:
                active_by_user[auto_activate_for] = [auto_activate_agent]
            collections[name] = {
                "name": name,
                "csv_path": csv_path,
                "description": description,
                "delimiter": delimiter,
                "vectorized_columns": list(vectorized_columns or []),
                "owner": owner,
                "num_rows": int(num_rows),
                "last_vectorized": int(time.time() * 1000),
                "active_by_user": active_by_user,
                "private": bool(private),
            }
            self._write(collections)
            return collections[name]

    def set_private(self, name, private):
        """Toggle visibility. Making it private drops *all* non-owner subscriptions."""
        with self._lock:
            collections = self._read().get("collections", {})
            meta = collections.get(name)
            if meta is None:
                return None
            meta["private"] = bool(private)
            if meta["private"]:
                owner = meta.get("owner")
                cleaned = {
                    u: agents for u, agents in self._active_by_user(meta).items() if u == owner
                }
                meta["active_by_user"] = cleaned
            self._write(collections)
            return meta

    def delete_collection(self, name):
        with self._lock:
            collections = self._read().get("collections", {})
            removed = collections.pop(name, None)
            if removed is not None:
                self._write(collections)
            return removed

    def set_active(self, name, username, agent_id, active):
        """Activate / deactivate a single collection for (user, agent)."""
        with self._lock:
            collections = self._read().get("collections", {})
            meta = collections.get(name)
            if meta is None:
                return None
            active_by_user = self._active_by_user(meta)
            agents = set(active_by_user.get(username) or [])
            if active:
                agents.add(agent_id)
            else:
                agents.discard(agent_id)
            if agents:
                active_by_user[username] = sorted(agents)
            else:
                active_by_user.pop(username, None)
            meta["active_by_user"] = active_by_user
            collections[name] = meta
            self._write(collections)
            return meta

    def set_active_set(self, username, agent_id, active_names):
        """Replace this (user, agent)'s active set in one shot."""
        wanted = set(active_names or [])
        with self._lock:
            collections = self._read().get("collections", {})
            changed = False
            for name, meta in collections.items():
                active_by_user = self._active_by_user(meta)
                agents = set(active_by_user.get(username) or [])
                want = name in wanted
                has = agent_id in agents
                if want and not has:
                    agents.add(agent_id)
                    changed_here = True
                elif not want and has:
                    agents.discard(agent_id)
                    changed_here = True
                else:
                    changed_here = False
                if changed_here:
                    if agents:
                        active_by_user[username] = sorted(agents)
                    else:
                        active_by_user.pop(username, None)
                    meta["active_by_user"] = active_by_user
                    changed = True
            if changed:
                self._write(collections)

    def update_description(self, name, description):
        with self._lock:
            collections = self._read().get("collections", {})
            meta = collections.get(name)
            if meta is None:
                return None
            meta["description"] = description
            self._write(collections)
            return meta
