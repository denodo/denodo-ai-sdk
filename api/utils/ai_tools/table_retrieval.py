import asyncio
import json
import logging

from utils import utils
from utils.data_catalog import get_allowed_view_ids
from api.utils import sdk_utils

def _table_from_search_result(table, filter_associations=False, valid_view_ids=None):
    view_json = json.loads(table.metadata['view_json'])
    if filter_associations:
        view_json = sdk_utils.filter_non_allowed_associations(view_json, valid_view_ids or [])

    return {
        "view_text": table.page_content,
        "view_name": table.metadata['view_name'],
        "view_json": view_json,
        "view_id": table.metadata['view_id']
    }

def _build_no_table_error_message(
    vector_store,
    valid_view_ids,
    vector_search,
    relevant_tables,
    vdb_list,
    tag_list,
    use_views,
    expand_set_views
):
    if relevant_tables:
        return None

    vector_store_has_data = bool(vector_store.search("tables", k=1))
    if not vector_store_has_data:
        return "The vector store is empty. Please synchronize the metadata first."

    user_has_accessible_views = vector_store.check_existence(valid_view_ids)
    if not user_has_accessible_views:
        return "You don't have permission to access any views that are currently indexed in the vector store. Please contact your administrator."

    if not vector_search:
        if vdb_list or tag_list:
            filters = []
            if vdb_list:
                quoted_vdb_list = [f'"{vdb}"' for vdb in vdb_list]
                filters.append(f"database filters: {', '.join(quoted_vdb_list)}")
            if tag_list:
                quoted_tag_list = [f'"{tag}"' for tag in tag_list]
                filters.append(f"tag filters: {', '.join(quoted_tag_list)}")
            return f"No relevant views found in the vector store matching your query with the specified {' and '.join(filters)}. Try adjusting your filters or query."
        return "No relevant views found in the vector store matching your query. Please try a different query."

    if use_views and not expand_set_views:
        return f"The specified views ({', '.join(use_views)}) were not found in the vector store or you don't have permission to access them."

    return "The vector search found results, but they were filtered out because you don't have permission to access them."

@utils.log_params
@utils.timed
async def get_relevant_tables(
    query, vector_store, sample_data_vector_store, vdb_list, tag_list, auth,
    vector_search_k=5,
    use_views='',
    expand_set_views=True,
    vector_search_sample_data_k=3,
    allow_external_associations=True,
    vector_search_total_limit=20,
    custom_headers=None
):
    vdb_list = [db.strip() for db in vdb_list.split(',')] if vdb_list else []
    tag_list = [tag.strip() for tag in tag_list.split(',')] if tag_list else []

    timings = {}
    embedding_task = asyncio.create_task(vector_store.embeddings.aembed_query(query))
    view_ids_task = asyncio.create_task(get_allowed_view_ids(auth=auth, custom_headers=custom_headers))
    embedded_query, valid_view_ids = await asyncio.gather(embedding_task, view_ids_task)

    if not valid_view_ids:
        return [], {}, timings, "You don't have permission to access any views in Denodo. Please contact your administrator."

    valid_view_ids = [str(view_id) for view_id in valid_view_ids]
    search_params = {
        "vector": embedded_query,
        "k": vector_search_k,
        "database_names": vdb_list,
        "tag_names": tag_list,
        "view_ids": valid_view_ids
    }

    with sdk_utils.timing_context("vector_store_search_time", timings):
        vector_search = vector_store.search_batched(**search_params)

    seen_view_ids = set()
    relevant_tables = []
    have_chunks = False

    for table in vector_search:
        view_id = table.metadata['view_id']
        document_id = table.id
        if "_" in document_id:
            have_chunks = True
        if view_id not in seen_view_ids:
            seen_view_ids.add(view_id)
            relevant_tables.append(_table_from_search_result(table))

    max_rounds = 2
    current_round = 0
    have_multiple_chunks = have_chunks and len(vector_search) > vector_search_k
    have_more_to_search = len(valid_view_ids) > len(relevant_tables)

    if have_multiple_chunks and have_more_to_search:
        logging.info("Multiple chunks detected in vector store results, performing additional rounds to find unique views.")
        with sdk_utils.timing_context("vector_store_search_time", timings):
            while len(relevant_tables) < vector_search_k and len(valid_view_ids) > len(relevant_tables) and current_round < max_rounds and len(vector_search):
                remaining_view_ids = [view_id for view_id in valid_view_ids if view_id not in seen_view_ids]
                search_params["view_ids"] = remaining_view_ids
                new_search = vector_store.search_batched(**search_params)
                if not new_search:
                    break

                for table in new_search:
                    view_id = table.metadata['view_id']
                    if view_id not in seen_view_ids and len(relevant_tables) < vector_search_k:
                        seen_view_ids.add(view_id)
                        relevant_tables.append(_table_from_search_result(table))

                current_round += 1

    association_ids = []
    for table in relevant_tables:
        table_associations = utils.get_table_associations(table['view_name'], table['view_json'])
        for assoc_id in table_associations:
            if assoc_id not in seen_view_ids and assoc_id not in association_ids:
                association_ids.append(assoc_id)

    if use_views != '':
        use_views = [view.strip() for view in use_views.split(',') if view.strip()]
        use_view_ids = vector_store.get_view_ids(use_views)
        for view_id in use_view_ids:
            if view_id not in seen_view_ids and view_id not in association_ids:
                association_ids.append(view_id)

    association_ids = [assoc_id for assoc_id in association_ids if assoc_id in valid_view_ids]
    remaining_slots = vector_search_total_limit - len(relevant_tables)
    if remaining_slots < 0:
        remaining_slots = 0
        relevant_tables = relevant_tables[:vector_search_total_limit]

    if remaining_slots and association_ids:
        with sdk_utils.timing_context("vector_store_search_time", timings):
            association_lookup = vector_store.get_views(association_ids)

        association_lookup_map = {assoc.metadata['view_id']: assoc for assoc in association_lookup}

        for assoc_id in association_ids:
            if len(relevant_tables) >= vector_search_total_limit:
                break

            assoc_doc = association_lookup_map.get(assoc_id)
            if not assoc_doc or assoc_doc.metadata['view_id'] in seen_view_ids:
                continue

            if not allow_external_associations and (vdb_list or tag_list):
                db_match = not vdb_list or assoc_doc.metadata.get('database_name') in vdb_list
                tag_match = not tag_list or any(
                    f"tag_{tag}" in assoc_doc.metadata and assoc_doc.metadata[f"tag_{tag}"] == "1" for tag in tag_list
                )
                if not (db_match and tag_match):
                    continue

            seen_view_ids.add(assoc_doc.metadata['view_id'])
            relevant_tables.append(_table_from_search_result(assoc_doc, filter_associations=True, valid_view_ids=valid_view_ids))

    if not expand_set_views:
        if use_views != '':
            relevant_tables = [table for table in relevant_tables if table['view_name'] in use_views]
        else:
            relevant_tables = []

    with sdk_utils.timing_context("vector_store_search_time", timings):
        sample_data = {}
        for table in relevant_tables:
            view_id = str(table['view_id'])
            result = sample_data_vector_store.search_by_vector(
                vector=embedded_query,
                k=vector_search_sample_data_k,
                view_ids=[view_id]
            )

            if result and len(result) > 0:
                column_names = [col.strip() for col in result[0].metadata['columns'].split(',') if col.strip()]
                column_samples = {col: [] for col in column_names}

                for row in result:
                    values = [value.strip() for value in row.page_content.strip().split(',')]
                    for col, val in zip(column_names, values):
                        column_samples[col].append(val)

                sample_data[view_id] = column_samples

    error_message = _build_no_table_error_message(
        vector_store=vector_store,
        valid_view_ids=valid_view_ids,
        vector_search=vector_search,
        relevant_tables=relevant_tables,
        vdb_list=vdb_list,
        tag_list=tag_list,
        use_views=use_views,
        expand_set_views=expand_set_views
    )

    return relevant_tables, sample_data, timings, error_message
