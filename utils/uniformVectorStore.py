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
        self.dimensions = self.get_dimensions()
        self.chunk_factor = chunk_factor
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

            PGVECTOR_CONNECTION_STRING = os.getenv("PGVECTOR_CONNECTION_STRING", "postgresql+psycopg://langchain:langchain@localhost:6024/langchain")

            if not PGVECTOR_CONNECTION_STRING:
                raise ValueError("PGVECTOR_CONNECTION_STRING environment variable not set.")

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
        else:
            raise ValueError(f"Unsupported vector store provider: {self.provider}")

    @timed
    def get_dimensions(self):
        test_vector = self.embeddings.embed_query("test")
        return len(test_vector)

    def get_last_update_dict(self):
        search_vector = self.search_by_vector([0] * self.dimensions, k = 1, view_ids = ["last_update"])
        if search_vector and 'last_update_dict' in search_vector[0].metadata:
            return json.loads(search_vector[0].metadata['last_update_dict'])
        else:
            return None

    @timed
    def get_last_update(self, source_type, source_name):
        last_update_dict = self.get_last_update_dict()
        if last_update_dict and source_type in last_update_dict and source_name in last_update_dict[source_type]:
            return int(last_update_dict[source_type][source_name])
        else:
            return None

    @timed
    def update_last_update(self, last_update_dict):
        self.client.delete(ids=["last_update"])
        if last_update_dict:
            self.client.add_documents(prepare_last_update_vector(last_update_dict), ids = ["last_update"])

    @timed
    def remove_from_last_update(self, database_names=None, tag_names=None):
        last_update_dict = self.get_last_update_dict()
        modified = False

        if last_update_dict:
            if database_names and "DATABASE" in last_update_dict:
                for db_name in database_names:
                    if db_name in last_update_dict["DATABASE"]:
                        del last_update_dict["DATABASE"][db_name]
                        modified = True
                if not last_update_dict["DATABASE"]:
                    del last_update_dict["DATABASE"]
                    modified = True

            if tag_names and "TAG" in last_update_dict:
                for tag_name in tag_names:
                    if tag_name in last_update_dict["TAG"]:
                        del last_update_dict["TAG"][tag_name]
                        modified = True
                if not last_update_dict["TAG"]:
                    del last_update_dict["TAG"]
                    modified = True

            if modified:
                self.update_last_update(last_update_dict)

    @log_params
    @timed
    def search(self, query, k=3, view_ids=None, database_names=None, tag_names=None, view_names=None, scores=False):
        # If view_ids is provided and it's empty, return empty list
        if view_ids is not None and len(view_ids) == 0:
            return []
        # Build search filter if view_ids has values
        elif view_ids is not None:
            search_filter = self._build_search_filter(view_ids, database_names, tag_names, view_names)
        # Otherwise, no filter on view_ids
        else:
            search_filter = None

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
    @timed
    def search_by_vector(self, vector, k=3, view_ids=None, database_names=None, tag_names=None, view_names=None):
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

        if self.provider == "opensearch":
            return self.client.similarity_search_by_vector(vector, k=k, search_type="script_scoring", pre_filter=search_filter)
        elif self.provider in ["chroma", "pgvector"]:
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
                elif self.provider in ["chroma", "pgvector"]:
                    or_conditions.append({"database_name": {"$eq": db_name}})

        if tag_names:
            for tag_name in tag_names:
                if self.provider == "opensearch":
                    or_conditions.append({"match": {f"metadata.tag_{tag_name}": "1"}})
                elif self.provider in ["chroma", "pgvector"]:
                    or_conditions.append({f"tag_{tag_name}": {"$eq": "1"}})

        if not or_conditions:
            return None # No filter to apply if no conditions were added

        if self.provider == "opensearch":
            if len(or_conditions) == 1:
                return or_conditions[0] # If only one OR condition, return it directly
            return {"bool": {"should": or_conditions, "minimum_should_match": 1}}
        elif self.provider in ["chroma", "pgvector"]:
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
        elif self.provider in ["chroma", "pgvector"]:
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

        elif self.provider in ['chroma', 'pgvector']:
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

    def add_views(self, views, parallel = True, source_type = "OTHER", source_name = "default", sample_data = False):
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
            last_update = int(time.time() * 1000)
            last_update_dict = self.get_last_update_dict()
            if last_update_dict:
                self.client.delete(ids = ["last_update"])
            self.client.add_documents(prepare_last_update_vector(last_update_dict, last_update, source_type, source_name), ids = ["last_update"])

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
        view_ids = self.search_by_vector([0]*self.dimensions, k = len(view_names) * self.chunk_factor, view_names = view_names)
        return [view.metadata['view_id'] for view in view_ids]

    @log_params
    def get_views(self, view_ids):
        if len(view_ids) == 0:
            return []

        views = self.search_by_vector([0]*self.dimensions, k=len(view_ids) * self.chunk_factor, view_ids=view_ids)

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
            results = self.search_by_vector(
                vector=[0]*self.dimensions,
                k=K_BATCH_SIZE,
                database_names=None,
                tag_names=None,
                view_ids=view_ids,
                view_names=None
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
