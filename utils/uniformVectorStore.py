import os
import sqlite3

from utils.utils import log_params
from utils.uniformEmbeddings import UniformEmbeddings

class UniformVectorStore:
    def __init__(self, provider, embeddings_provider, embeddings_model, index_name = "ai_sdk_vector_store", manager_db = "ai_sdk_manager.db"):
        self.provider = provider.lower()
        self.embeddings = UniformEmbeddings(embeddings_provider, embeddings_model).model
        self.index_name = index_name
        self.manager_db = os.path.join(index_name, manager_db)
        self.client = None
        self.dimensions = self._get_dimensions()
        self._connect_manager()
        self._connect()

    def _connect(self):
        if self.provider == "chroma":
            import platform
            if platform.system() == "Linux":
                __import__('pysqlite3')
                import sys
                sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
            from chromadb.config import Settings
            from langchain_chroma import Chroma
            self.client = Chroma(
                collection_name=self.index_name,
                embedding_function=self.embeddings,
                persist_directory=self.index_name,
                collection_metadata={
                    "hnsw:space": "cosine",
                    "hnsw:construction_ef": 128,
                    "hnsw:search_ef": 128,
                    "hnsw:M": 128
                },
                client_settings = Settings(
                    anonymized_telemetry=False,
                    is_persistent=True
                )
            )
        elif self.provider == "pgvector":
            from langchain_postgres import PGVector

            PGVECTOR_CONNECTION_STRING = os.getenv("PGVECTOR_CONNECTION_STRING", "postgresql+psycopg://langchain:langchain@localhost:6024/langchain")

            self.client = PGVector(
                embeddings=self.embeddings,
                collection_name=self.index_name,
                connection=PGVECTOR_CONNECTION_STRING,
                use_jsonb=True,
            )
        elif self.provider == "opensearch":
            from langchain_community.vectorstores import OpenSearchVectorSearch

            OPENSEARCH_URL = os.getenv("OPENSEARCH_URL", "http://localhost:9200")
            OPENSEARCH_USERNAME = os.getenv("OPENSEARCH_USERNAME", "admin")
            OPENSEARCH_PASSWORD = os.getenv("OPENSEARCH_PASSWORD", "admin")

            self.client = OpenSearchVectorSearch(
                opensearch_url = OPENSEARCH_URL,
                http_auth = (OPENSEARCH_USERNAME, OPENSEARCH_PASSWORD),
                embedding_function = self.embeddings,
                index_name = self.index_name,
                use_ssl = True,
                verify_certs = False,
                ssl_assert_hostname = False,
                ssl_show_warn = False,
            )
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")
        
    def _get_dimensions(self):
        return len(self.embeddings.embed_query("test"))

    def _connect_manager(self):
        if not os.path.exists(self.index_name):
            os.makedirs(self.index_name)
        self.manager_conn = sqlite3.connect(self.manager_db)
        self.manager_cursor = self.manager_conn.cursor()
        self.manager_cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_sdk_VectorStore (
                view_id TEXT PRIMARY KEY,
                view_name TEXT,
                database_name TEXT
            )
        ''')
        self.manager_conn.commit()

    def add_views(self, views, database_name, overwrite = False):
        views = list({view.id: view for view in views}.values())

        if overwrite and self.count(database_name) > 0:
            view_ids = self._get_view_ids_by_database(database_name)
            self.client.delete(ids = view_ids)
            self._delete_views_from_manager(view_ids)

        existing_view_ids = self._get_view_ids_by_database(database_name)
        new_views = [view for view in views if view.id not in existing_view_ids]
        ids = [view.id for view in new_views]
        if new_views:
            self.client.add_documents(new_views, ids = ids)
            self._add_views_to_manager(new_views, database_name)

    @log_params
    def get_views(self, view_names, valid_view_ids = None):
        view_ids = self.get_view_ids(view_names)
        if valid_view_ids is not None:
            view_ids = [view_id for view_id in view_ids if view_id in valid_view_ids]
        if len(view_ids) == 0:
            view_ids = None
            return []
        views = self.search_by_vector([0]*self.dimensions, k=len(view_names), view_ids=view_ids, scores=False)
        return views
    
    @log_params
    def get_view_ids(self, view_names):
        # Make sure the view names don't contain quotes
        view_names = [view_name.replace('"', '') for view_name in view_names]
        placeholders = ','.join(['?' for _ in view_names])
        self.manager_cursor.execute(f"SELECT view_id FROM ai_sdk_VectorStore WHERE view_name IN ({placeholders})", view_names)
        return [row[0] for row in self.manager_cursor.fetchall()]

    @log_params
    def get_view_names(self, view_ids):
        placeholders = ','.join(['?' for _ in view_ids])
        self.manager_cursor.execute(f"SELECT view_id, view_name FROM ai_sdk_VectorStore WHERE view_id IN ({placeholders})", view_ids)
        return [(row[0], row[1]) for row in self.manager_cursor.fetchall()]
    
    @log_params
    def delete_views(self, view_names):
        view_ids = [str(id) for id in self.get_view_ids(view_names)]
        if len(view_ids) != 0:
            self.client.delete(view_ids)
            self._delete_views_from_manager(view_ids)

    @log_params
    def delete_database(self, database_name):
        view_ids = []
        while True:
            ids = self.search_by_vector([0]*self.dimensions, k=1000, database_names=[database_name])
            if len(ids) == 0:
                break
            view_ids.extend(ids)
        self.client.delete(view_ids)
        self._delete_views_from_manager(view_ids)

    @log_params
    def count(self, database: str = "all"):
        if database == "all":
            self.manager_cursor.execute("SELECT COUNT(*) FROM ai_sdk_VectorStore")
        else:
            self.manager_cursor.execute("SELECT COUNT(*) FROM ai_sdk_VectorStore WHERE database_name = ?", (database,))
        return self.manager_cursor.fetchone()[0]

    @log_params
    def search(self, query, k=3, view_ids = None, scores=False, database_names = None):
        if view_ids is not None and len(view_ids) == 0:
            return []

        search_filter = self._build_search_filter(view_ids, database_names)
        
        if scores:
            if self.provider == "opensearch":
                return self.client.similarity_search_with_score(query, k=k, search_type="script_scoring", pre_filter=search_filter)
            elif self.provider in ["chroma", "pgvector"]:
                return self.client.similarity_search_with_score(query, k=k, filter=search_filter)
        else:
            if self.provider == "opensearch":
                return self.client.similarity_search(query, k=k, search_type="script_scoring", pre_filter=search_filter)
            elif self.provider in ["chroma", "pgvector"]:
                return self.client.similarity_search(query, k=k, filter=search_filter)

    @log_params
    def search_by_vector(self, vector, k=3, view_ids = None, scores=False, database_names = None):
        if view_ids is not None and len(view_ids) == 0:
            return []
        
        search_filter = self._build_search_filter(view_ids, database_names)

        # PGVector does not support scores
        if self.provider == "pgvector":
            scores = False
        
        if scores:
            if self.provider == "opensearch":
                return self.client.similarity_search_by_vector_with_relevance_scores(vector, k=k, search_type="script_scoring", pre_filter=search_filter)
            elif self.provider in ["chroma", "pgvector"]:
                return self.client.similarity_search_by_vector_with_relevance_scores(vector, k=k, filter=search_filter)
        else:
            if self.provider == "opensearch":
                return self.client.similarity_search_by_vector(vector, k=k, search_type="script_scoring", pre_filter=search_filter)
            elif self.provider in ["chroma", "pgvector"]:
                return self.client.similarity_search_by_vector(vector, k=k, filter=search_filter)

    @log_params
    def _get_view_ids_by_database(self, database_name):
        self.manager_cursor.execute("SELECT view_id FROM ai_sdk_VectorStore WHERE database_name = ?", (database_name,))
        return [str(row[0]) for row in self.manager_cursor.fetchall()]

    def _add_views_to_manager(self, views, database_name):
        for view in views:
            self.manager_cursor.execute(
                "INSERT OR REPLACE INTO ai_sdk_VectorStore (view_id, view_name, database_name) VALUES (?, ?, ?)",
                (view.id, view.metadata['view_name'], database_name)
            )
        self.manager_conn.commit()

    def _delete_views_from_manager(self, view_ids):
        placeholders = ','.join(['?' for _ in view_ids])
        self.manager_cursor.execute(f"DELETE FROM ai_sdk_VectorStore WHERE view_id IN ({placeholders})", view_ids)
        self.manager_conn.commit()

    @log_params
    def _build_search_filter(self, view_ids, database_names):
        # Convert empty lists to None
        view_ids = None if not view_ids else view_ids
        database_names = None if not database_names else database_names

        if self.provider == "opensearch":
            if view_ids is not None and database_names is None:
                return {"terms": {"metadata.view_id": view_ids}}
            elif database_names is not None and view_ids is None:
                return {"terms": {"metadata.database_name": database_names}}
            elif view_ids is not None and database_names is not None:
                return {
                    "bool": {
                        "must": [
                            {"terms": {"metadata.view_id": view_ids}},
                            {"terms": {"metadata.database_name": database_names}}
                        ]
                    }
                }
        elif self.provider in ['chroma', 'pgvector']:
            if view_ids is not None and database_names is None:
                return {"view_id": {"$in": view_ids}}
            elif database_names is not None and view_ids is None:
                return {"database_name": {"$in": database_names}}
            elif view_ids is not None and database_names is not None:
                return {"$and": [{"view_id": {"$in": view_ids}}, {"database_name": {"$in": database_names}}]}
        else:
            return None

    def __del__(self):
        try:
            if hasattr(self, 'manager_conn'):
                self.manager_conn.close()
        except Exception:
            pass