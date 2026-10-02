import asyncio
import logging

from utils import utils
from utils.schema_catalog.helpers import encode_tag
from utils.data_marketplace.connection import get_user_permissions_for_vector_store
from api.utils import sdk_utils

@utils.log_params
@utils.timed
async def get_relevant_tables(
    query,
    vector_store,
    sample_data_vector_store,
    vdb_list,
    tag_list,
    auth,
    vector_search_k=5,
    use_views=None,
    expand_set_views=True,
    vector_search_sample_data_k=3,
    allow_external_associations=False,
    vector_search_total_limit=20,
    custom_headers=None,
    filter_logic="OR",
):
    """
    Fetches relevant tables from the vector store based on the user's query, applying
    security policies, expanding chunks, fetching associations, and gathering sample data.
    """
    vdb_list = vdb_list or []
    tag_list = tag_list or []
    use_views_list = use_views or []

    timings = {}

    # Asynchronous fetching of embeddings and permissions
    embedding_task = asyncio.create_task(vector_store.embeddings.aembed_query(query))
    permissions_task = asyncio.create_task(
        get_user_permissions_for_vector_store(auth=auth, vector_store=vector_store, custom_headers=custom_headers)
    )
    embedded_query, permissions_data = await asyncio.gather(embedding_task, permissions_task)

    views_details = permissions_data.get("viewsPermissions", [])
    valid_view_ids = [str(view["viewId"]) for view in views_details]
    security_policies_by_view = {str(view["viewId"]): view for view in views_details}

    if not valid_view_ids:
        return (
            [],
            {},
            timings,
            "You don't have permission to access any views in Denodo. Please contact your administrator.",
            permissions_data,
        )

    # Main search in the vector store
    search_params = {
        "vector": embedded_query,
        "k": vector_search_k,
        "database_names": vdb_list,
        "tag_names": tag_list,
        "view_ids": valid_view_ids,
        "filter_logic": filter_logic,
    }

    with sdk_utils.timing_context("vector_store_search_time", timings):
        vector_search = vector_store.search_batched(**search_params)

    seen_view_ids = set()
    relevant_tables = []
    have_chunks = False

    for table in vector_search:
        if "_" in table.id:
            have_chunks = True
        _process_and_append_document(table, seen_view_ids, relevant_tables, security_policies_by_view)

    # Additional rounds due to chunk fragmentation
    have_multiple_chunks = have_chunks and len(vector_search) > vector_search_k
    have_more_to_search = len(valid_view_ids) > len(relevant_tables)

    if have_multiple_chunks and have_more_to_search:
        logging.info(
            "Multiple chunks detected in vector store results, performing additional rounds to find unique views."
        )
        _perform_additional_rounds(
            vector_store,
            search_params,
            valid_view_ids,
            seen_view_ids,
            relevant_tables,
            security_policies_by_view,
            vector_search_k,
            vector_search,
            timings,
        )

    # Add associations and explicitly requested views
    _get_and_append_associations(
        vector_store,
        relevant_tables,
        seen_view_ids,
        valid_view_ids,
        use_views_list,
        vector_search_total_limit,
        allow_external_associations,
        vdb_list,
        tag_list,
        security_policies_by_view,
        timings,
        filter_logic,
    )

    # Restrict results if expansion is not allowed
    if not expand_set_views:
        if use_views_list:
            relevant_tables = [table for table in relevant_tables if table["view_name"] in use_views_list]
        else:
            relevant_tables = []

    # Sample data extraction
    sample_data = _fetch_sample_data(
        relevant_tables,
        sample_data_vector_store,
        embedded_query,
        vector_search_sample_data_k,
        security_policies_by_view,
        timings,
    )

    # Generate error message if applicable
    error_message = _build_no_table_error_message(
        vector_store=vector_store,
        valid_view_ids=valid_view_ids,
        vector_search=vector_search,
        relevant_tables=relevant_tables,
        vdb_list=vdb_list,
        tag_list=tag_list,
        use_views=use_views_list,
        expand_set_views=expand_set_views,
    )

    return relevant_tables, sample_data, timings, error_message, permissions_data

@utils.log_params
@utils.timed
async def get_tables_by_name(
    query,
    view_names,
    vector_store,
    sample_data_vector_store,
    auth,
    vector_search_sample_data_k=3,
    custom_headers=None,
    vdb_list=None,
    tag_list=None,
    filter_logic="OR",
):
    """Look up named views in the vector store without similarity search or association expansion.

    Every requested view must be found, permitted, and (when vdb_list / tag_list are set) in
    scope. If any name fails those checks, no tables are returned together with a message
    listing the views that could not be used.
    """
    view_names_list = [name.strip() for name in (view_names or []) if name and name.strip()]
    vdb_list = [name.strip() for name in (vdb_list or []) if name and name.strip()]
    tag_list = [name.strip() for name in (tag_list or []) if name and name.strip()]
    timings = {}

    embedding_task = asyncio.create_task(vector_store.embeddings.aembed_query(query))
    permissions_task = asyncio.create_task(
        get_user_permissions_for_vector_store(auth=auth, vector_store=vector_store, custom_headers=custom_headers)
    )
    embedded_query, permissions_data = await asyncio.gather(embedding_task, permissions_task)

    views_details = permissions_data.get("viewsPermissions", [])
    valid_view_ids = {str(view["viewId"]) for view in views_details}
    security_policies_by_view = {str(view["viewId"]): view for view in views_details}

    if not valid_view_ids:
        return (
            [],
            {},
            timings,
            "You don't have permission to access any views in Denodo. Please contact your administrator.",
            permissions_data,
        )

    if not view_names_list:
        return (
            [],
            {},
            timings,
            "No view names were provided.",
            permissions_data,
        )

    seen_view_ids = set()
    relevant_tables = []

    with sdk_utils.timing_context("vector_store_search_time", timings):
        view_ids = [str(view_id) for view_id in vector_store.get_view_ids(view_names_list) if str(view_id) in valid_view_ids]
        docs = vector_store.get_views(view_ids) if view_ids else []

    scope_error = _build_view_names_scope_error(docs, vdb_list, tag_list, filter_logic)
    if scope_error:
        return [], {}, timings, scope_error, permissions_data

    requested_names = set(view_names_list)
    for doc in docs:
        _process_and_append_document(doc, seen_view_ids, relevant_tables, security_policies_by_view)

    relevant_tables = [table for table in relevant_tables if table["view_name"] in requested_names]
    found_names = {table["view_name"] for table in relevant_tables}
    missing_names = [name for name in view_names_list if name not in found_names]
    if missing_names:
        return (
            [],
            {},
            timings,
            (
                f"The specified views ({', '.join(missing_names)}) were not found in the vector store "
                "or you don't have permission to access them."
            ),
            permissions_data,
        )

    sample_data = _fetch_sample_data(
        relevant_tables,
        sample_data_vector_store,
        embedded_query,
        vector_search_sample_data_k,
        security_policies_by_view,
        timings,
    )

    return relevant_tables, sample_data, timings, None, permissions_data

def _build_view_names_scope_error(docs, vdb_list, tag_list, filter_logic="OR"):
    """Returns an error message when any of the explicitly requested views falls outside the
    vdp_database_names / vdp_tag_names scope of the request, or None when all views are in scope.

    When both filters are set, filter_logic decides the rule. OR accepts a view that matches
    either list. AND accepts a view only when it matches both.
    """
    if not vdb_list and not tag_list:
        return None

    out_of_scope = [
        doc.metadata.get("view_name") for doc in docs
        if not _passes_external_filters(doc, False, vdb_list, tag_list, filter_logic)
    ]
    out_of_scope = [name for name in out_of_scope if name]
    if not out_of_scope:
        return None

    names = ", ".join(out_of_scope)
    if vdb_list and tag_list and filter_logic == "AND":
        return (
            f"The request is filtered by vdp_database_names ({', '.join(vdb_list)}) AND "
            f"vdp_tag_names ({', '.join(tag_list)}) but the following views in view_names "
            f"do not match both filters: {names}. "
            "Please fix your request so that view_names only contains views from those databases that are also tagged with those tags."
        )
    if vdb_list and tag_list:
        return (
            f"The request is filtered by vdp_database_names ({', '.join(vdb_list)}) OR "
            f"vdp_tag_names ({', '.join(tag_list)}) but the following views in view_names "
            f"do not belong to those databases and are not tagged with those tags: {names}. "
            "Please fix your request so that view_names only contains views from those databases or tagged with those tags."
        )
    if vdb_list:
        return (
            f"The request is filtered by vdp_database_names ({', '.join(vdb_list)}) but the following views "
            f"in view_names do not belong to those databases: {names}. "
            "Please fix your request so that view_names only contains views from those databases."
        )
    return (
        f"The request is filtered by vdp_tag_names ({', '.join(tag_list)}) but the following views "
        f"in view_names are not tagged with those tags: {names}. "
        "Please fix your request so that view_names only contains views tagged with those tags."
    )

def _process_and_append_document(
    doc, seen_view_ids, relevant_tables, security_policies_by_view, filter_associations=False, valid_view_ids=None
):
    """Parses a view document, applies security, and adds it to the results if not seen before."""
    view_id = doc.metadata.get("view_id")

    if not view_id or view_id in seen_view_ids:
        return False

    seen_view_ids.add(view_id)
    security_info = security_policies_by_view.get(view_id, {})

    parsed_doc = sdk_utils.parse_view_document(
        doc, filter_associations=filter_associations, valid_view_ids=valid_view_ids, security_info=security_info
    )
    relevant_tables.append(parsed_doc)
    return True

def _perform_additional_rounds(
    vector_store,
    search_params,
    valid_view_ids,
    seen_view_ids,
    relevant_tables,
    security_policies_by_view,
    vector_search_k,
    initial_vector_search,
    timings,
):
    """Performs additional searches in the vector store if multiple chunks are detected."""
    max_rounds = 2
    current_round = 0

    with sdk_utils.timing_context("vector_store_search_time", timings):
        while (
            len(relevant_tables) < vector_search_k
            and len(valid_view_ids) > len(relevant_tables)
            and current_round < max_rounds
            and len(initial_vector_search)
        ):
            remaining_view_ids = [view_id for view_id in valid_view_ids if view_id not in seen_view_ids]
            search_params["view_ids"] = remaining_view_ids
            new_search = vector_store.search_batched(**search_params)

            if not new_search:
                break

            for table in new_search:
                if len(relevant_tables) >= vector_search_k:
                    break
                _process_and_append_document(table, seen_view_ids, relevant_tables, security_policies_by_view)

            current_round += 1

def _collect_additional_view_ids(vector_store, relevant_tables, seen_view_ids, valid_view_ids, use_views_list):
    """
    Gathers view IDs from view associations and explicitly requested views, avoiding duplicates.
    """
    additional_ids = []
    seen_locally = set(seen_view_ids)

    for table in relevant_tables:
        for assoc_id in utils.get_table_associations(table["view_name"], table["view_json"]):
            if assoc_id not in seen_locally:
                additional_ids.append(assoc_id)
                seen_locally.add(assoc_id)

    if use_views_list:
        for view_id in vector_store.get_view_ids(use_views_list):
            if view_id not in seen_locally:
                additional_ids.append(view_id)
                seen_locally.add(view_id)

    return [v_id for v_id in additional_ids if v_id in valid_view_ids]

def _passes_external_filters(assoc_doc, allow_external_associations, vdb_list, tag_list, filter_logic="OR"):
    """Checks if a view document passes database and tag filters when external associations are restricted."""
    if allow_external_associations or not (vdb_list or tag_list):
        return True

    db_match = not vdb_list or assoc_doc.metadata.get("database_name") in vdb_list
    tag_match = not tag_list or any(
        f"tag_{encode_tag(tag)}" in assoc_doc.metadata and assoc_doc.metadata.get(f"tag_{encode_tag(tag)}") == "1"
        for tag in tag_list
    )

    if not vdb_list:
        return tag_match
    if not tag_list:
        return db_match
    if filter_logic == "AND":
        return db_match and tag_match
    return db_match or tag_match

def _get_and_append_associations(
    vector_store,
    relevant_tables,
    seen_view_ids,
    valid_view_ids,
    use_views_list,
    vector_search_total_limit,
    allow_external_associations,
    vdb_list,
    tag_list,
    security_policies_by_view,
    timings,
    filter_logic="OR",
):
    """Finds and extracts associations (or explicitly requested views), safely integrating them into the results."""
    association_ids = _collect_additional_view_ids(
        vector_store, relevant_tables, seen_view_ids, valid_view_ids, use_views_list
    )

    remaining_slots = vector_search_total_limit - len(relevant_tables)
    if remaining_slots < 0:
        del relevant_tables[vector_search_total_limit:]
        remaining_slots = 0

    if remaining_slots <= 0 or not association_ids:
        return

    with sdk_utils.timing_context("vector_store_search_time", timings):
        association_lookup = vector_store.get_views(association_ids)

    association_lookup_map = {assoc.metadata.get("view_id"): assoc for assoc in association_lookup}

    for assoc_id in association_ids:
        if len(relevant_tables) >= vector_search_total_limit:
            break

        assoc_doc = association_lookup_map.get(assoc_id)
        if not assoc_doc or assoc_doc.metadata.get("view_id") in seen_view_ids:
            continue

        if not _passes_external_filters(
            assoc_doc, allow_external_associations, vdb_list, tag_list, filter_logic
        ):
            continue

        _process_and_append_document(
            doc=assoc_doc,
            seen_view_ids=seen_view_ids,
            relevant_tables=relevant_tables,
            security_policies_by_view=security_policies_by_view,
            filter_associations=True,
            valid_view_ids=valid_view_ids,
        )

def _fetch_sample_data(
    relevant_tables,
    sample_data_vector_store,
    embedded_query,
    vector_search_sample_data_k,
    security_policies_by_view,
    timings,
):
    """Dynamically fetches sample data for each view, applying security restrictions."""
    sample_data = {}
    with sdk_utils.timing_context("vector_store_search_time", timings):
        for table in relevant_tables:
            view_id = table["view_id"]
            security_info = security_policies_by_view.get(view_id, {})

            if security_info.get("hasRowRestrictions", False):
                logging.info(f"Skipping sample data for view {view_id} due to row restrictions.")
                continue

            result = sample_data_vector_store.search_by_vector(
                vector=embedded_query, k=vector_search_sample_data_k, view_ids=[view_id]
            )

            if result and len(result) > 0:
                column_names = [col.strip() for col in result[0].metadata["columns"].split(",") if col.strip()]
                column_samples = {col: [] for col in column_names}

                for row in result:
                    values = [value.strip() for value in row.page_content.strip().split(",")]
                    for col, val in zip(column_names, values):
                        column_samples[col].append(val)

                restricted_cols = security_info.get("restrictedColumns", [])
                if restricted_cols:
                    restricted_set = set([col.lower() for col in restricted_cols])
                    column_samples = {
                        col: vals for col, vals in column_samples.items() if col.lower() not in restricted_set
                    }

                sample_data[view_id] = column_samples

    return sample_data

def _build_no_table_error_message(
    vector_store, valid_view_ids, vector_search, relevant_tables, vdb_list, tag_list, use_views, expand_set_views
):
    """Builds appropriate error messages when no relevant views are found."""
    if relevant_tables:
        return None

    vector_store_has_data = bool(vector_store.search("tables", k=1))
    if not vector_store_has_data:
        return "The vector store is empty. Please synchronize the metadata first."

    user_has_accessible_views = vector_store.check_existence(valid_view_ids)
    if not user_has_accessible_views:
        return (
            "None of the views you have permission to access are currently synchronized "
            "in the vector store. Please synchronize the required metadata or check your access rights."
        )

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

    return (
        "The vector search found results, but they were filtered out because you don't have permission to access them."
    )
