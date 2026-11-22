import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.endpoints import getMetadata as endpoint
from api.utils.sdk_utils import process_metadata_source
from api.utils import sdk_utils
from utils.data_marketplace import connection


@pytest.mark.parametrize('parameter', ['use_columns', 'ignore_columns'])
def test_invalid_rules_rejected_before_endpoint_side_effects(parameter, monkeypatch):
    async def unexpected_permissions(**kwargs):
        raise AssertionError("Invalid rules must be rejected before permission lookup")

    monkeypatch.setattr(endpoint, "get_user_permissions", unexpected_permissions)
    app = FastAPI()
    app.include_router(endpoint.router)
    app.dependency_overrides[endpoint.authenticate] = lambda: 'test'
    app.dependency_overrides[endpoint.get_custom_request_headers] = lambda: {}
    with TestClient(app) as client:
        response = client.get('/getMetadata', params={parameter: '{}'})
    assert response.status_code == 422
    assert parameter in response.text


@pytest.mark.parametrize('source_type', ['DATABASE', 'TAG'])
def test_column_rules_filter_metadata_and_samples_in_source_pipeline(monkeypatch, source_type):
    raw_views = [{
        'id': 42, 'databaseName': 'hr', 'name': 'employees',
        'schema': [
            {'name': 'id', 'type': 'int', 'primaryKey': True},
            {'name': 'name', 'type': 'text'},
            {'name': 'salary', 'type': 'int'},
            {'name': 'secret', 'type': 'text'},
        ],
        'viewFieldDataList': [
            {'fieldName': 'name', 'fieldValues': ['Jane']},
            {'fieldName': 'salary', 'fieldValues': ['100']},
            {'fieldName': 'secret', 'fieldValues': ['private']},
        ],
    }]

    class Response:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def text(self):
            return json.dumps({'viewsDetails': raw_views})

    class Session(Response):
        def __init__(self, **kwargs):
            pass

        def post(self, url, **kwargs):
            return Response()

    monkeypatch.setattr(connection.aiohttp, 'ClientSession', Session)
    request = endpoint.getMetadataRequest(
        insert=False, examples_per_table=3,
        use_columns='[{"view":"hr.employees","columns":["name","salary"]}]',
        ignore_columns='[{"columns":["salary"]}]',
    )
    schema, rendered, errors, _ = asyncio.run(process_metadata_source(
        source_type=source_type, source_name='hr' if source_type == 'DATABASE' else 'people',
        request=request, auth='test', vector_store=None, sample_data_vector_store=None,
    ))
    columns = schema['views'][0]['schema']
    assert [col['columnName'] for col in columns] == ['name']
    assert columns[0]['sample_data'] == ['Jane']
    assert 'private' not in str(schema)
    assert 'salary' not in str(rendered)
    assert errors == []


@pytest.mark.parametrize('source_type', ['DATABASE', 'TAG'])
def test_resync_removes_old_samples_when_no_replacement_rows_remain(monkeypatch, source_type):
    async def metadata(**kwargs):
        return {'views': [{'id': '42', 'tableName': 'hr.employees', 'schema': []}]}, [], [], []

    class Samples:
        def __init__(self):
            self.documents = {'42': ['old private sample'], '99': ['unrelated sample']}

        def delete_by_view_id(self, view_ids):
            for view_id in view_ids:
                self.documents.pop(view_id, None)

        def add_views(self, views, **kwargs):
            assert views, 'Do not send an empty batch to a vector store'

    monkeypatch.setattr(sdk_utils, 'get_views_metadata_documents', metadata)
    samples = Samples()
    request = endpoint.getMetadataRequest(examples_per_table=3)
    asyncio.run(process_metadata_source(
        source_type=source_type, source_name='hr', request=request, auth='test',
        vector_store=None, sample_data_vector_store=samples, incremental=True,
    ))
    assert samples.documents == {'99': ['unrelated sample']}


def test_column_rules_open_sample_store_for_cleanup_when_sampling_is_disabled(monkeypatch):
    schema_store, sample_store = object(), object()
    seen = []

    async def permissions(**kwargs):
        return {}

    def store(**kwargs):
        return sample_store if kwargs.get('index_name') == 'ai_sdk_sample_data' else schema_store

    async def delete(**kwargs):
        seen.append(kwargs['sample_data_vector_store'])

    async def process(**kwargs):
        seen.append(kwargs['sample_data_vector_store'])
        return {}, [], [], {}

    monkeypatch.setattr(endpoint, 'get_user_permissions', permissions)
    monkeypatch.setattr(endpoint, 'check_metadata_user_permission', lambda *a: True)
    monkeypatch.setattr(endpoint.state_manager, 'get_vector_store', store)
    monkeypatch.setattr(endpoint, 'delete_by_db_or_tag', delete)
    monkeypatch.setattr(endpoint, 'process_metadata_source', process)
    request = endpoint.getMetadataRequest(
        vdp_database_names=['hr'], insert=True, examples_per_table=0,
        ignore_columns='[{"columns":["secret"]}]',
    )
    asyncio.run(endpoint.getMetadata(endpoint_request=request, auth='test', custom_headers={}))
    assert seen == [sample_store, sample_store]


def test_column_rules_preserve_marketplace_null_schema_compatibility():
    from utils.column_filter import filter_view_columns
    from utils.schema_catalog import SchemaCatalog

    views = [{'id': '42', 'databaseName': 'hr', 'name': 'employees', 'schema': None}]
    filtered = filter_view_columns(views, [{'view': 'other.view', 'columns': ['secret']}])
    catalog = SchemaCatalog.from_marketplace_json(filtered)
    assert catalog.to_storage_json()['views'][0]['schema'] == []
