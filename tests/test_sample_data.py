import copy
import json

from langchain_core.documents import Document

from api.utils.ai_tools.table_retrieval import _fetch_sample_data
from utils.schema_catalog import SchemaCatalog
from utils.utils import prepare_sample_data_schema


class SampleStore:
    def __init__(self, documents):
        self.documents = documents
        self.searches = []

    def search_by_vector(self, **kwargs):
        self.searches.append(kwargs)
        return self.documents[:kwargs['k']]


def fetch(documents, security=None, k=8):
    store = SampleStore(documents)
    result = _fetch_sample_data(
        [{'view_id': '42'}], store, [0.1], k,
        {'42': security or {}}, {},
    )
    return result, store


def sample_schema():
    return {'views': [{
        'id': '42', 'tableName': 'demo.customers', 'databaseName': 'demo',
        'schema': [
            {'columnName': 'name', 'logicalName': 'Customer name',
             'sample_data': ['Smith, Jane', '', '  Ali  ']},
            {'columnName': 'city', 'sample_data': ['Riyadh', 'Jeddah']},
            {'columnName': 'note,details', 'sample_data': ['line\n"two"', None, 'الرياض']},
        ],
    }]}


def test_sample_documents_round_trip_commas_unicode_and_placeholders_without_mutating_schema():
    schema = sample_schema()
    original = copy.deepcopy(schema)
    documents = prepare_sample_data_schema(schema)[0]
    samples, _ = fetch(documents)

    assert samples == {'42': {
        'name': ['Smith, Jane', '', '  Ali  '],
        'city': ['Riyadh', 'Jeddah', ''],
        'note,details': ['line\n"two"', None, 'الرياض'],
    }}
    assert schema == original
    assert json.loads(documents[0].metadata['row_json']) == {
        'name': 'Smith, Jane', 'city': 'Riyadh', 'note,details': 'line\n"two"',
    }
    assert json.loads(documents[0].metadata['columns']) == ['name', 'city', 'note,details']
    assert 'Customer name:' in documents[0].page_content
    assert 'Smith, Jane' in documents[0].page_content


def test_missing_json_fields_do_not_shift_later_rows_and_json_is_authoritative():
    documents = [
        Document(page_content='wrong,embedding', metadata={
            'columns': 'name,city', 'row_json': '{"name": "a"}'}),
        Document(page_content='wrong,embedding', metadata={
            'columns': 'name,city', 'row_json': '{"name": "b", "city": "c,d"}'}),
        Document(page_content='wrong,embedding', metadata={
            'columns': '["city", "name"]', 'row_json': '{"city": null, "name": "c"}'}),
    ]
    samples, _ = fetch(documents)
    assert samples == {'42': {'name': ['a', 'b', 'c'], 'city': ['', 'c,d', None]}}


def test_mixed_legacy_rows_and_json_keep_alignment_and_skip_ambiguous_or_corrupt_rows():
    documents = [
        Document(page_content='a,b', metadata={'columns': 'name,city'}),
        Document(page_content='a,b,extra', metadata={'columns': 'name,city'}),
        Document(page_content='ignored,text', metadata={'columns': 'name,city', 'row_json': '{bad'}),
        Document(page_content='ignored,text', metadata={'columns': 'name,city', 'row_json': '[]'}),
        Document(page_content='ignored,text', metadata={
            'columns': 'name,city', 'row_json': '{"name": "c,d", "city": ""}'}),
    ]
    samples, _ = fetch(documents)
    assert samples == {'42': {'name': ['a', 'c,d'], 'city': ['b', '']}}


def test_rows_reach_prompt_with_falsey_values_in_their_original_positions():
    schema = {'views': [{'id': '42', 'tableName': 'demo.items', 'schema': [
        {'columnName': 'id', 'type': 'int', 'sample_data': list(range(10))},
        {'columnName': 'value', 'type': 'text',
         'sample_data': ['', None, False, 0, 'a,b', 'five', 'six', 'seven', 'eight', 'nine']},
    ]}]}
    documents = prepare_sample_data_schema(schema)[0]
    samples, store = fetch(documents)
    assert store.searches[0]['k'] == 8
    assert samples['42']['value'] == ['', None, False, 0, 'a,b', 'five', 'six', 'seven']
    rendered = SchemaCatalog.from_storage_json(schema).render_vql_schema(sample_data=samples, examples_per_table=8)
    assert 'sample values: [0, 1, 2, 3, 4, 5, 6, 7]' in rendered
    assert 'sample values: ["", null, false, 0, "a,b", "five", "six", "seven"]' in rendered
    assert 'same row' in rendered
    assert '"eight"' not in rendered


def test_sample_security_removes_restricted_columns_and_skips_row_restricted_views():
    documents = prepare_sample_data_schema(sample_schema())[0]
    samples, _ = fetch(documents, {'restrictedColumns': ['NAME', 'note,DETAILS']})
    assert samples == {'42': {'city': ['Riyadh', 'Jeddah', '']}}
    samples, store = fetch(documents, {'hasRowRestrictions': True})
    assert samples == {}
    assert store.searches == []


def test_no_sample_rows_produce_no_documents():
    schema = {'views': [{'id': '42', 'schema': [{'columnName': 'name'}]}]}
    assert prepare_sample_data_schema(schema) == [[]]


