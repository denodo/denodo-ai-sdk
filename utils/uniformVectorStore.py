import os
import json
import time
import logging
import concurrent.futures
from utils.utils import log_params, prepare_last_update_vector, timed

class UniformVectorStore:
    def __init__(self, provider, embeddings, index_name = "ai_sdk_vector_store", rate_limit_rpm = None, chunk_factor = 5):
        self.provider = provider.lower()
        self.embeddings = embeddings
        self.index_name = index_name
        self.rate_limit_rpm = rate_limit_rpm
        self.client = None
        self.search_vector = self.embeddings.embed_query("tables")
        self.dimensions = len(self.search_vector)
        self.chunk_factor = chunk_factor
        self._connect()

    @staticmethod
    def _ensure_modern_sqlite():
        """Make sure the sqlite3 module Chroma will import is >= 3.35.0."""
        import sys
        import sqlite3

        if sqlite3.sqlite_version_info >= (3, 35, 0):
            return

        for module_name in ("pysqlite3", "sqlean"):
            try:
                __import__(module_name)
            except ImportError:
                continue
            # A source build of pysqlite3 links against the host's libsqlite3, so it
            # can report the same too-old version. Only swap when it really is newer.
            if sys.modules[module_name].sqlite_version_info >= (3, 35, 0):
                sys.modules['sqlite3'] = sys.modules.pop(module_name)
                return
            sys.modules.pop(module_name, None)

        raise RuntimeError(
            f"Chroma requires sqlite3 >= 3.35.0 but this host provides {sqlite3.sqlite_version}. "
            "Run the AI SDK on a Python linked against a newer SQLite (a uv, pyenv or conda "
            "managed build ships one), or upgrade the system SQLite."
        )

    def _connect(self):
        if self.provider == "chroma":
            self._ensure_modern_sqlite()
            from chromadb.config import Settings
            from langchain_chroma import Chroma
            data_dir = os.getenv("AI_SDK_DATA_DIR", ".")
            persist_dir = os.path.join(data_dir, self.index_name)

            self.client = Chroma(
                collection_name=self.index_name,
                embedding_function=self.embeddings,
                persist_directory=persist_dir,
                collection_metadata={
                    "hnsw:space": "cosine",
                    "hnsw:construction_ef": 512,
                    "hnsw:search_ef": 256,
                    "hnsw:M": 256
                },
                client_settings = Settings(
                    anonymized_telemetry=False,
                    is_persistent=True
                )
            )
        elif self.provider == "pgvector":
            from langchain_postgres import PGVector
            from sqlalchemy import create_engine

            PGVECTOR_CONNECTION_STRING = os.getenv("PGVECTOR_CONNECTION_STRING")

            if not PGVECTOR_CONNECTION_STRING:
                raise ValueError("PGVECTOR_CONNECTION_STRING environment variable not set.")

            engine = create_engine(
                PGVECTOR_CONNECTION_STRING,
                pool_pre_ping=True, # Test connection before use to handle dropped connections
                pool_recycle=1800, # Recycle connections after 1800 seconds
            )

            self.client = PGVector(
                embeddings=self.embeddings,
                connection=engine,
                collection_name=self.index_name,
                use_jsonb=True,
            )
        elif self.provider == "opensearch":
            from langchain_community.vectorstores import OpenSearchVectorSearch

            OPENSEARCH_URL = os.getenv("OPENSEARCH_URL", "http://localhost:9200")
            OPENSEARCH_USERNAME = os.getenv("OPENSEARCH_USERNAME", "admin")
            OPENSEARCH_PASSWORD = os.getenv("OPENSEARCH_PASSWORD", "admin")

            if not OPENSEARCH_URL:
                raise ValueError("OPENSEARCH_URL environment variable not set.")
            if not OPENSEARCH_USERNAME:
                raise ValueError("OPENSEARCH_USERNAME environment variable not set.")
            if not OPENSEARCH_PASSWORD:
                raise ValueError("OPENSEARCH_PASSWORD environment variable not set.")

            self.client = OpenSearchVectorSearch(
                opensearch_url = OPENSEARCH_URL,
                http_auth = (OPENSEARCH_USERNAME, OPENSEARCH_PASSWORD),
                embedding_function = self.embeddings,
                index_name = self.index_name,
                engine="faiss",
                use_ssl = True,
                verify_certs = False,
                ssl_assert_hostname = False,
                ssl_show_warn = False,
            )

            if not self.client.client.indices.exists(index=self.index_name):
                self.client.create_index(
                    dimension=self.dimensions,
                    index_name=self.index_name,
                    engine="faiss"
                )
        elif self.provider == "oracle":
            import oracledb
            from langchain_oracledb.vectorstores import OracleVS
            from langchain_oracledb.vectorstores.oraclevs import DistanceStrategy

            ORACLE_USERNAME = os.getenv("ORACLE_USERNAME")
            ORACLE_PASSWORD = os.getenv("ORACLE_PASSWORD")
            ORACLE_DSN = os.getenv("ORACLE_DSN")

            if not all([ORACLE_USERNAME, ORACLE_PASSWORD, ORACLE_DSN]):
                raise ValueError("ORACLE_USERNAME, ORACLE_PASSWORD, and ORACLE_DSN environment variables must be set.")

            try:
                connection = oracledb.connect(
                    user=ORACLE_USERNAME,
                    password=ORACLE_PASSWORD,
                    dsn=ORACLE_DSN
                )
            except Exception as e:
                raise ConnectionError(f"Failed to connect to Oracle Database: {e}")

            self.client = OracleVS(
                client=connection,
                embedding_function=self.embeddings,
                table_name=self.index_name,
                distance_strategy=DistanceStrategy.COSINE,
            )
        else:
            raise ValueError(f"Unsupported vector store provider: {self.provider}")

    def get_last_update_dict(self):
        search_vector = self.search_by_vector(self.search_vector, k = 1, view_ids = ["last_update"])
        if search_vector and 'last_update_dict' in search_vector[0].metadata:
            return json.loads(search_vector[0].metadata['last_update_dict'])
        else:
            return None

    def get_partial_resources_dict(self):
        search_vector = self.search_by_vector(self.search_vector, k=1, view_ids=["last_update"])
        if search_vector and 'partial_resources_dict' in search_vector[0].metadata:
            return json.loads(search_vector[0].metadata['partial_resources_dict'])
        else:
            return None

    @timed
    def get_sync_metadata(self):
        search_vector = self.search_by_vector(self.search_vector, k=1, view_ids=["last_update"])

        last_update_dict = None
        partial_resources_dict = None

        if search_vector:
            metadata = search_vector[0].metadata

            if 'last_update_dict' in metadata:
                last_update_dict = json.loads(metadata['last_update_dict'])

            if 'partial_resources_dict' in metadata:
                partial_resources_dict = json.loads(metadata['partial_resources_dict'])

        return last_update_dict, partial_resources_dict

    @timed
    def get_last_update(self, source_type, source_name):
        last_update_dict = self.get_last_update_dict()
        if last_update_dict and source_type in last_update_dict and source_name in last_update_dict[source_type]:
            return int(last_update_dict[source_type][source_name])
        else:
            return None

    @timed
    def update_last_update(self, last_update_dict, partial_resources_dict):
        self.client.delete(ids=["last_update"])
        self.client.add_documents(
            prepare_last_update_vector(last_update_dict, partial_resources_dict),
            ids=["last_update"]
        )

    @timed
    def remove_from_last_update(self, database_names=None, tag_names=None):
        last_update_dict, partial_resources_dict = self.get_sync_metadata()
        modified = False

        if last_update_dict:
            if database_names and "DATABASE" in last_update_dict:
                for db_name in database_names:
                    if db_name in last_update_dict["DATABASE"]:
                        del last_update_dict["DATABASE"][db_name]
                        modified = True

            if tag_names and "TAG" in last_update_dict:
                for tag_name in tag_names:
                    if tag_name in last_update_dict["TAG"]:
                        del last_update_dict["TAG"][tag_name]
                        modified = True

        if partial_resources_dict:
            if database_names and "partial_tags_by_db" in partial_resources_dict:
                partial_tags_by_db = partial_resources_dict["partial_tags_by_db"]
                for db_name in database_names:
                    if db_name in partial_tags_by_db:
                        del partial_tags_by_db[db_name]
                        modified = True

            if tag_names:
                if "partial_dbs_by_tag" in partial_resources_dict:
                    partial_dbs_by_tag = partial_resources_dict["partial_dbs_by_tag"]
                    for tag_name in tag_names:
                        if tag_name in partial_dbs_by_tag:
                            del partial_dbs_by_tag[tag_name]
                            modified = True

                if "partial_tags_by_tag" in partial_resources_dict:
                    partial_tags_by_tag = partial_resources_dict["partial_tags_by_tag"]
                    for tag_name in tag_names:
                        if tag_name in partial_tags_by_tag:
                            del partial_tags_by_tag[tag_name]
                            modified = True

        if self._prune_orphan_sync_entries(last_update_dict, partial_resources_dict):
            modified = True

        if last_update_dict:
            for source_type in ("DATABASE", "TAG"):
                if source_type in last_update_dict and not last_update_dict[source_type]:
                    del last_update_dict[source_type]
                    modified = True

        if modified:
            self.update_last_update(last_update_dict, partial_resources_dict)

    @timed
    def _prune_orphan_sync_entries(self, last_update_dict, partial_resources_dict):
        """
        Drops sync metadata entries that no longer have any document backing them.

        A resource can stop having documents without being named in the deletion
        request: deleting a database also removes the only views a tag was covering.
        The leftover entry is invisible while the store is empty, but it reappears
        with its old timestamp as soon as a matching view is indexed again, and it
        makes is_non_conflicting_doc treat those views as protected, so they can no
        longer be deleted. Both dicts are modified in place.

        Returns True if anything was removed.
        """
        modified = False

        if last_update_dict:
            for source_type, filter_key in (("DATABASE", "database_names"), ("TAG", "tag_names")):
                for source_name in list(last_update_dict.get(source_type, {})):
                    if not self.check_existence(None, **{filter_key: [source_name]}):
                        del last_update_dict[source_type][source_name]
                        modified = True
                        logging.info(f"Pruned orphan {source_type} sync entry: {source_name}")

        if partial_resources_dict:
            buckets = (
                ("partial_tags_by_db", lambda db, tag: {"database_names": [db], "tag_names": [tag]}),
                ("partial_dbs_by_tag", lambda tag, db: {"database_names": [db], "tag_names": [tag]}),
                ("partial_tags_by_tag", lambda tag, other: {"tag_names": [tag, other]}),
            )

            for bucket_name, build_filters in buckets:
                bucket = partial_resources_dict.get(bucket_name, {})
                for source_name in list(bucket):
                    current = bucket[source_name] or []
                    surviving = [
                        target_name for target_name in current
                        if self.check_existence(None, **build_filters(source_name, target_name))
                    ]

                    if not surviving:
                        del bucket[source_name]
                        modified = True
                        logging.info(f"Pruned orphan {bucket_name} entry: {source_name}")
                    elif surviving != current:
                        bucket[source_name] = surviving
                        modified = True
                        logging.info(f"Pruned orphan {bucket_name} targets for {source_name}")

        return modified

    @log_params
    @timed
    def search(self, query, k=3, view_ids=None, database_names=None, tag_names=None, view_names=None, scores=False):
        # If view_ids is provided and it's empty, return empty list
        if view_ids is not None and len(view_ids) == 0:
            return []
        # Build search filter if view_ids has values
        elif view_ids is not None:
            search_filter = self._build_search_filter(view_ids, database_names, tag_names, view_names)
        elif not view_names and ((database_names and len(database_names) > 0) or (tag_names and len(tag_names) > 0)):
            search_filter = self._build_metadata_search_filter(database_names, tag_names)
        elif view_names:
            search_filter = self._build_get_view_ids_search_filter(view_names)
        else:
            search_filter = None

        if scores:
            if self.provider == "opensearch":
                return self.client.similarity_search_with_score(query, k=k, search_type="script_scoring", pre_filter=search_filter)
            elif self.provider in ["chroma", "pgvector", "oracle"]:
                return self.client.similarity_search_with_score(query, k=k, filter=search_filter)
        else:
            if self.provider == "opensearch":
                return self.client.similarity_search(query, k=k, search_type="script_scoring", pre_filter=search_filter)
            elif self.provider in ["chroma", "pgvector", "oracle"]:
                return self.client.similarity_search(query, k=k, filter=search_filter)

    @log_params
    @timed
    def search_by_vector(self, vector, k=3, view_ids=None, database_names=None, tag_names=None, view_names=None, scores=False):
        # If view_ids is provided and it's empty, return empty list
        if view_ids is not None and len(view_ids) == 0:
            return []
        # Build search filter if view_ids has values
        elif view_ids is not None:
            search_filter = self._build_search_filter(view_ids, database_names, tag_names, view_names)
        elif not view_names and ((database_names and len(database_names) > 0) or (tag_names and len(tag_names) > 0)):
            search_filter = self._build_metadata_search_filter(database_names, tag_names)
        else:
            search_filter = self._build_get_view_ids_search_filter(view_names)

        if scores:
            if self.provider == "opensearch":
                return self.client.similarity_search_with_score_by_vector(vector, k=k, search_type="script_scoring", pre_filter=search_filter)
            elif self.provider in ["pgvector", "oracle"]:
                return self.client.similarity_search_with_score_by_vector(vector, k=k, filter=search_filter)
            elif self.provider == "chroma":
                return self.client.similarity_search_by_vector_with_relevance_scores(vector, k=k, filter=search_filter)
        else:
            if self.provider == "opensearch":
                return self.client.similarity_search_by_vector(vector, k=k, search_type="script_scoring", pre_filter=search_filter)
            elif self.provider in ["chroma", "pgvector", "oracle"]:
                return self.client.similarity_search_by_vector(vector, k=k, filter=search_filter)

    @log_params
    def _build_metadata_search_filter(self, database_names=None, tag_names=None):
        """
        Builds a search filter for metadata-only queries (database_names, tag_names)
        using OR logic across the provided lists.
        """
        or_conditions = []

        if database_names:
            for db_name in database_names:
                if self.provider == "opensearch":
                    or_conditions.append({"match": {"metadata.database_name": db_name}})
                elif self.provider in ["chroma", "pgvector", "oracle"]:
                    or_conditions.append({"database_name": {"$eq": db_name}})

        if tag_names:
            for tag_name in tag_names:
                if self.provider == "opensearch":
                    or_conditions.append({"match": {f"metadata.tag_{tag_name}": "1"}})
                elif self.provider in ["chroma", "pgvector", "oracle"]:
                    or_conditions.append({f"tag_{tag_name}": {"$eq": "1"}})

        if not or_conditions:
            return None # No filter to apply if no conditions were added

        if self.provider == "opensearch":
            if len(or_conditions) == 1:
                return or_conditions[0] # If only one OR condition, return it directly
            return {"bool": {"should": or_conditions, "minimum_should_match": 1}}
        elif self.provider in ["chroma", "pgvector", "oracle"]:
            if len(or_conditions) == 1:
                return or_conditions[0] # If only one OR condition, return it directly
            return {"$or": or_conditions}
        else:
            return None

    @log_params
    def _build_get_view_ids_search_filter(self, view_names):
        if self.provider == "opensearch":
            #return {"metadata.view_name": {"$in": view_names}}
            return {"terms": {
                "metadata.view_name.keyword": view_names
            }}
        elif self.provider in ["chroma", "pgvector", "oracle"]:
            return {"view_name": {"$in": view_names}}
        else:
            return None

    @log_params
    def _build_search_filter(self, view_ids, database_names=None, tag_names=None, view_names=None):
        # Check if any additional filters are provided
        has_additional_filters = database_names or tag_names or view_names

        if self.provider == "opensearch":
            # If no additional filters, return a simple terms filter for view_ids
            if not has_additional_filters:
                return {
                    "terms": {
                        "metadata.view_id": view_ids
                    }
                }

            # Otherwise, create the more complex filter with boolean logic
            filter_query = {
                "bool": {
                    "must": [
                        {
                            "terms": {
                                "metadata.view_id": view_ids
                            }
                        }
                    ]
                }
            }

            # Add additional filters if provided
            or_conditions = []

            # Add database name conditions
            if database_names:
                for db_name in database_names:
                    or_conditions.append({
                        "match": {
                            "metadata.database_name": db_name
                        }
                    })

            # Add tag conditions
            if tag_names:
                for tag_name in tag_names:
                    or_conditions.append({
                        "match": {
                            f"metadata.tag_{tag_name}": "1"
                        }
                    })

            # Add view name conditions
            if view_names:
                for view_name in view_names:
                    or_conditions.append({
                        "match": {
                            "metadata.view_name": view_name
                        }
                    })

            # Add the conditions to the filter
            if len(or_conditions) == 1:
                # If only one condition, add it directly to must
                filter_query["bool"]["must"].append(or_conditions[0])
            elif len(or_conditions) > 1:
                # If multiple conditions, use should with minimum_should_match
                filter_query["bool"]["must"].append({
                    "bool": {
                        "should": or_conditions,
                        "minimum_should_match": 1
                    }
                })

            return filter_query

        elif self.provider in ['chroma', 'pgvector', 'oracle']:
            # If no additional filters, return a simple filter for view_ids
            if not has_additional_filters:
                return {"view_id": {"$in": view_ids}}

            # Otherwise, create the more complex filter with $and
            filter_query = {
                "$and": [
                    {"view_id": {"$in": view_ids}}
                ]
            }

            # Add additional filters if provided
            or_conditions = []

            # Add database name conditions
            if database_names:
                for db_name in database_names:
                    or_conditions.append({"database_name": {"$eq": db_name}})

            # Add tag conditions
            if tag_names:
                for tag_name in tag_names:
                    or_conditions.append({f"tag_{tag_name}": {"$eq": "1"}})

            # Add view name conditions
            if view_names:
                for view_name in view_names:
                    or_conditions.append({"view_name": {"$eq": view_name}})

            # Add the conditions to the filter
            if len(or_conditions) == 1:
                # If only one condition, add it directly to $and
                filter_query["$and"].append(or_conditions[0])
            elif len(or_conditions) > 1:
                # If multiple conditions, use $or
                filter_query["$and"].append({"$or": or_conditions})

            return filter_query
        else:
            return None

    def delete(self, ids, batch_size = 1000):
        for i in range(0, len(ids), batch_size):
            batch_ids = ids[i:i+batch_size]
            self.client.delete(ids=batch_ids)

    def add_views(self, views, parallel = True, source_type = "OTHER", source_name = "default", sample_data = False, tags_by_db=None, dbs_by_tag=None, tags_by_tag=None):
        views = list({view.id: view for view in views}.values())

        if source_type in ["DATABASE", "TAG"]:
            view_ids = []
            ids_to_delete_set = set()

            for view in views:
                view_ids.append(view.id)
                if 'view_id' in view.metadata:
                    ids_to_delete_set.add(view.metadata.get('view_id'))
                else:
                    ids_to_delete_set.add(view.id)

            ids_to_delete = list(ids_to_delete_set)

            if ids_to_delete:
                self.delete_by_view_id(view_ids = ids_to_delete)
        else:
            view_ids = [view.id for view in views]
            if view_ids:
                self.delete(ids = view_ids)

        # If rate limiting is enabled, process views in batches
        if self.rate_limit_rpm and len(view_ids) > self.rate_limit_rpm:
            logging.info(f"Rate limiting enabled: {self.rate_limit_rpm} views per minute. Total views: {len(view_ids)}")

            # Process views in batches based on rate limit
            for i in range(0, len(view_ids), self.rate_limit_rpm):
                batch_end = min(i + self.rate_limit_rpm, len(view_ids))
                batch_views = views[i:batch_end]
                batch_ids = view_ids[i:batch_end]

                logging.info(f"Processing batch {i//self.rate_limit_rpm + 1}: {len(batch_views)} views")

                # Process this batch using existing methods
                if parallel:
                    try:
                        self._add_views_parallel(batch_views, batch_ids)
                    except Exception as e:
                        logging.warning(f"Parallel processing failed: {str(e)}. Falling back to sequential processing.")
                        self.client.add_documents(batch_views, ids=batch_ids)
                else:
                    self.client.add_documents(batch_views, ids=batch_ids)

                # If there are more batches to process, wait for the next minute
                if batch_end < len(views):
                    wait_time = 60  # Wait 1 minute
                    logging.info(f"Waiting {wait_time} seconds before processing next batch...")
                    time.sleep(wait_time)
        else:
            # Process all views at once (original behavior)
            if parallel:
                try:
                    self._add_views_parallel(views, view_ids)
                except Exception as e:
                    logging.warning(f"Parallel processing failed: {str(e)}. Falling back to sequential processing.")
                    self.client.add_documents(views, ids=view_ids)
            else:
                self.client.add_documents(views, ids=view_ids)

        if source_type in ["DATABASE", "TAG"] and not sample_data:
            last_update_timestamp = int(time.time() * 1000)

            current_last_update_dict, current_partial_resources_dict = self.get_sync_metadata()

            if current_last_update_dict or current_partial_resources_dict:
                self.client.delete(ids=["last_update"])

            new_partial_resources = {
                "partial_tags_by_db": {k: list(v) for k, v in (tags_by_db or {}).items()},
                "partial_dbs_by_tag": {k: list(v) for k, v in (dbs_by_tag or {}).items()},
                "partial_tags_by_tag": {k: list(v) for k, v in (tags_by_tag or {}).items()}
            }

            docs_to_save = prepare_last_update_vector(
                last_update_dict=current_last_update_dict,
                partial_resources_dict=current_partial_resources_dict,
                new_partial_resources=new_partial_resources,
                last_update=last_update_timestamp,
                source_type=source_type,
                source_name=source_name
            )

            self.client.add_documents(docs_to_save, ids=["last_update"])

    def _add_views_parallel(self, views, ids, batch_size=5, max_retries=3):
        """Add views in parallel with batching and error handling."""

        def process_batch(batch_views, batch_ids, attempt=1):
            try:
                self.client.add_documents(batch_views, ids=batch_ids)
                return True, None
            except Exception as e:
                if attempt < max_retries:
                    logging.warning(f"Attempt {attempt} failed: {str(e)}. Retrying...", exc_info=True)
                    time.sleep(5**attempt)
                    return process_batch(batch_views, batch_ids, attempt + 1)
                return False, (batch_views, batch_ids, str(e))

        # Create batches
        batches = [
            (views[i:i + batch_size], ids[i:i + batch_size])
            for i in range(0, len(views), batch_size)
        ]

        failed_batches = []

        # Process batches in parallel
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = [
                executor.submit(process_batch, batch_views, batch_ids)
                for batch_views, batch_ids in batches
            ]

            # Collect results and handle failures
            for future in concurrent.futures.as_completed(futures):
                success, result = future.result()
                if not success:
                    failed_batch_views, failed_batch_ids, error = result
                    failed_batches.append((failed_batch_views, failed_batch_ids))
                    logging.error(f"Batch processing failed: {error}")

        # Handle any failed batches sequentially
        if failed_batches:
            logging.warning(f"Processing {len(failed_batches)} failed batches sequentially")
            for failed_views, failed_ids in failed_batches:
                try:
                    self.client.add_documents(failed_views, ids=failed_ids)
                except Exception as e:
                    logging.error(f"Fatal error processing batch: {str(e)}")
                    raise RuntimeError(f"Failed to process views after all retries: {str(e)}")

    @log_params
    def get_view_ids(self, view_names):
        view_ids = self.search_by_vector(self.search_vector, k = len(view_names) * self.chunk_factor, view_names = view_names)
        return [view.metadata['view_id'] for view in view_ids]

    @log_params
    def get_views(self, view_ids):
        if len(view_ids) == 0:
            return []

        views = self.search_by_vector(self.search_vector, k=len(view_ids) * self.chunk_factor, view_ids=view_ids)

        # Create a dictionary to keep only unique views based on view_name
        # Necessary because now there might be chunks of the same view
        unique_views = {}
        for view in views:
            view_name = view.metadata['view_name']
            if view_name not in unique_views:
                unique_views[view_name] = view

        return list(unique_views.values())

    @log_params
    def delete_views(self, view_names):
        # Create tasks for each view name
        results = [self.get_view_ids([view_name]) for view_name in view_names]

        # Flatten the results and convert to strings
        view_ids = [str(id) for sublist in results for id in sublist]

        if view_ids:
            self.delete(view_ids)

    @log_params
    def delete_by_view_id(self, view_ids=None):
        """
        Iteratively deletes all documents matching the given view ids.
        Continues fetching and deleting in batches until none are left.
        """
        K_BATCH_SIZE = 1000
        more_results_left = True

        while more_results_left:
            results = self.search_batched(
                vector=self.search_vector,
                k=K_BATCH_SIZE,
                view_ids=view_ids
            )

            if not results:
                break

            ids_to_delete = list(set(
                doc.metadata.get('document_id')
                for doc in results
                if 'document_id' in doc.metadata
            ))

            self.delete(ids=ids_to_delete)

            more_results_left = len(results) == K_BATCH_SIZE

    def check_existence(self, view_ids, database_names=None, tag_names=None):
        """
        Checks if ANY document exists for the given view_ids/filters, handling batching.
        Returns True immediately if found.
        """
        BATCH_SIZE = 30000
        total_ids = len(view_ids) if view_ids else 0

        if view_ids is not None and total_ids == 0:
            return False

        if not view_ids or total_ids <= BATCH_SIZE:
            results = self.search_by_vector(
                vector=self.search_vector,
                k=1, # We only need to know if at least 1 exists
                view_ids=view_ids,
                database_names=database_names,
                tag_names=tag_names
            )
            return bool(results)

        for i in range(0, total_ids, BATCH_SIZE):
            batch_ids = view_ids[i : i + BATCH_SIZE]

            if self.search_by_vector(
                vector=self.search_vector,
                k=1, # We only need to know if at least 1 exists
                view_ids=batch_ids,
                database_names=database_names,
                tag_names=tag_names
            ):
                return True

        return False

    def search_batched(self, k, view_ids=None, query=None, vector=None, scores=False, **kwargs):
        """
        Performs a search (text or vector) handling large lists of view_ids by batching.
        Safe to use with >65k view_ids on Postgres.
        """

        BATCH_SIZE = 30000
        total_ids = len(view_ids) if view_ids else 0

        if view_ids is not None and total_ids == 0:
            return []

        if vector is not None:
            search_method = self.search_by_vector
            search_arg = vector
        else:
            search_method = self.search
            search_arg = query

        if not view_ids or total_ids <= BATCH_SIZE:
            return search_method(search_arg, k=k, view_ids=view_ids, scores=scores, **kwargs)

        all_candidates = []
        for i in range(0, total_ids, BATCH_SIZE):
            batch_ids = view_ids[i : i + BATCH_SIZE]
            batch_results = search_method(search_arg, k=k, view_ids=batch_ids, scores=True, **kwargs)
            all_candidates.extend(batch_results)

        # Sort by score (distance ascending for most VectorStores)
        # Check if results are tuples (doc, score)
        if all_candidates and isinstance(all_candidates[0], tuple):
            all_candidates.sort(key=lambda x: x[1])

        top_k = all_candidates[:k]

        if not scores:
            return [item[0] if isinstance(item, tuple) else item for item in top_k]

        return top_k
