import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.endpoints import getMetadata as endpoint
from api.utils.sdk_utils import process_metadata_source
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
