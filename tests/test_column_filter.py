"""Column omissions before metadata sampling and schema normalization."""

import copy
import json

import pytest


@pytest.mark.parametrize('value', ['', '  ', '[]'])
@pytest.mark.parametrize('parameter', ['ignore_columns', 'use_columns'])
def test_empty_column_rules_leave_views_unchanged(value, parameter):
    from utils import column_filter

    views = [{'databaseName': 'hr', 'name': 'employees', 'schema': [{'name': 'id'}]}]
    rules = getattr(column_filter, f'parse_{parameter}')(value)
    if parameter == 'use_columns':
        assert column_filter.filter_view_columns(views, [], rules) is views
    else:
        assert column_filter.filter_view_columns(views, rules) is views


@pytest.mark.parametrize('value', [
    '{', '{}', 'null', '1', '[1]', '[{}]',
    '[{"columns": "salary"}]', '[{"columns": []}]',
    '[{"columns": [null]}]', '[{"columns": [" "]}]',
    '[{"columns": ["salary"], "extra": true}]',
    '[{"columns": ["salary"], "view": null}]',
    '[{"columns": ["salary"], "view": ""}]',
    '[{"columns": ["salary"], "view": "employees"}]',
    '[{"columns": ["salary"], "view": "hr."}]',
    '[{"columns": ["salary"], "view": " hr.employees"}]',
    '[{"columns": ["salary"], "view": "\\\"hr\\\".employees"}]',
    None, [],
])
@pytest.mark.parametrize('parameter', ['ignore_columns', 'use_columns'])
def test_invalid_column_rules_raise_actionable_value_error(value, parameter):
    from utils import column_filter

    with pytest.raises(ValueError, match=parameter):
        getattr(column_filter, f'parse_{parameter}')(value)


def test_global_and_exact_view_rules_combine_without_modifying_source():
    from utils.column_filter import filter_view_columns, parse_ignore_columns

    views = [
        {'databaseName': 'hr', 'name': 'employees', 'schema': [
            {'name': 'INTERNAL_ID'}, {'name': 'salary'}, {'name': 'name'},
        ], 'description': 'The salary description is unchanged.'},
        {'databaseName': 'hr', 'name': 'Employees', 'schema': [
            {'name': 'internal_id'}, {'name': 'salary'},
        ]},
    ]
    original = copy.deepcopy(views)
    rules = parse_ignore_columns(json.dumps([
        {'columns': ['internal_id']},
        {'view': 'hr.employees', 'columns': ['SALARY']},
    ]))
    filtered = filter_view_columns(views, rules)
    assert [field['name'] for field in filtered[0]['schema']] == ['name']
    assert [field['name'] for field in filtered[1]['schema']] == ['salary']
    assert filtered[0]['description'] == original[0]['description']
    assert views == original


def test_literal_column_names_match_quoted_metadata_without_wildcards():
    from utils.column_filter import filter_view_columns

    views = [{'databaseName': 'hr', 'name': 'employees', 'schema': [
        {'name': '"salary.total"'}, {'name': '"employee""id"'},
        {'name': 'private_*'}, {'name': 'private_note'}, {'name': ' other '},
    ]}]
    filtered = filter_view_columns(views, [{'columns': ['SALARY.TOTAL', 'employee"id', 'private_*']}])
    assert [field['name'] for field in filtered[0]['schema']] == ['private_note', ' other ']


def test_scoped_rules_match_canonical_view_names_with_literal_dots():
    from utils.column_filter import filter_view_columns, parse_ignore_columns

    rules = parse_ignore_columns('[{"view":"hr.employee.archive","columns":["salary"]}]')
    views = [{'databaseName': 'hr', 'name': 'employee.archive', 'schema': [
        {'name': 'salary'}, {'name': 'name'},
    ]}]
    filtered = filter_view_columns(views, rules)
    assert filtered[0]['schema'] == [{'name': 'name'}]


def test_omitting_one_primary_key_member_removes_partial_key_and_old_samples():
    from utils.column_filter import filter_view_columns

    views = [{'databaseName': 'hr', 'name': 'employees', 'schema': [
        {'name': 'tenant_id', 'primaryKey': True},
        {'name': 'id', 'primaryKey': True}, {'name': 'name'},
    ], 'viewFieldDataList': [
        {'fieldName': 'tenant_id', 'fieldValues': [1]},
        {'fieldName': 'name', 'fieldValues': ['Anna']},
    ]}]
    filtered = filter_view_columns(views, [{'columns': ['TENANT_ID']}])[0]
    assert [field['name'] for field in filtered['schema']] == ['id', 'name']
    assert not any(field.get('primaryKey') for field in filtered['schema'])
    assert filtered['viewFieldDataList'] == [{'fieldName': 'name', 'fieldValues': ['Anna']}]
    assert views[0]['schema'][1]['primaryKey'] is True


def test_filter_keeps_empty_views_so_existing_index_documents_can_be_replaced():
    from utils.column_filter import filter_view_columns

    views = [{'id': 42, 'databaseName': 'hr', 'name': 'employees', 'schema': [{'name': 'id'}]}]
    filtered = filter_view_columns(views, [{'columns': ['id']}])
    assert filtered == [{'id': 42, 'databaseName': 'hr', 'name': 'employees', 'schema': []}]


def test_filter_accepts_null_optional_metadata_without_rewriting_it():
    from utils.column_filter import filter_view_columns

    views = [{'databaseName': 'hr', 'name': 'employees', 'schema': [{'name': 'salary'}],
              'viewFieldDataList': None, 'associationData': None}]
    filtered = filter_view_columns(views, [{'columns': ['salary']}])
    assert filtered[0]['schema'] == []
    assert filtered[0]['viewFieldDataList'] is None
    assert filtered[0]['associationData'] is None


@pytest.mark.parametrize('mapping,hidden,removed', [
    ('employees.department_id = departments.id', {'columns': ['department_id']}, True),
    ('employees.department_id = departments.id', {'view': 'org.departments', 'columns': ['id']}, True),
    ('"employees"."department_id" = "departments"."id"', {'view': 'org.departments', 'columns': ['ID']}, True),
    ('hr.employees.department_id = org.departments.id', {'view': 'org.departments', 'columns': ['id']}, True),
    ('"employees"."department.id" = "departments"."id"', {'columns': ['department.id']}, True),
    ('"employees"."employee""id" = "departments"."id"', {'columns': ['employee"id']}, True),
    ('employees.department_id = departments.id', {'view': 'other.departments', 'columns': ['id']}, False),
    ('employees.department_id = departments.identity', {'columns': ['id']}, False),
    ("employees.name = 'departments.id'", {'columns': ['id']}, False),
])
def test_associations_omit_only_mappings_that_reference_hidden_endpoint_columns(mapping, hidden, removed):
    from utils.column_filter import filter_view_columns

    association = {'mapping': mapping, 'viewDetailsOfTheOtherView': {
        'id': 2, 'databaseName': 'org', 'name': 'departments',
    }}
    views = [{'databaseName': 'hr', 'name': 'employees', 'schema': [{'name': 'name'}],
              'associationData': [association]}]
    original = copy.deepcopy(views)
    filtered = filter_view_columns(views, [hidden])
    assert filtered[0]['associationData'] == ([] if removed else [association])
    assert views == original


def test_use_columns_combines_global_and_exact_view_rules_with_omissions_taking_precedence():
    from utils.column_filter import filter_view_columns, parse_use_columns

    views = [
        {'databaseName': 'hr', 'name': 'employees', 'schema': [
            {'name': 'ID'}, {'name': 'name'}, {'name': 'salary'}, {'name': 'private_note'},
        ], 'description': 'The salary description is unchanged.'},
        {'databaseName': 'hr', 'name': 'Employees', 'schema': [
            {'name': 'id'}, {'name': 'name'}, {'name': 'salary'},
        ]},
    ]
    original = copy.deepcopy(views)
    use_rules = parse_use_columns(json.dumps([
        {'columns': ['id']},
        {'view': 'hr.employees', 'columns': ['NAME']},
        {'view': 'hr.employees', 'columns': ['salary']},
    ]))
    filtered = filter_view_columns(views, [{'columns': ['SALARY']}], use_rules)
    assert [field['name'] for field in filtered[0]['schema']] == ['ID', 'name']
    assert [field['name'] for field in filtered[1]['schema']] == ['id']
    assert filtered[0]['description'] == original[0]['description']
    assert views == original


def test_scoped_use_columns_leaves_other_views_unrestricted():
    from utils.column_filter import filter_view_columns

    views = [
        {'databaseName': database, 'name': name, 'schema': [{'name': 'id'}, {'name': 'name'}]}
        for database, name in [('hr', 'employees'), ('hr', 'Employees'), ('HR', 'employees')]
    ]
    filtered = filter_view_columns(views, [], [{'view': 'hr.employees', 'columns': ['name']}])
    assert filtered[0]['schema'] == [{'name': 'name'}]
    assert filtered[1] is views[1]
    assert filtered[2] is views[2]


def test_use_columns_preserves_literal_quoted_column_and_view_names():
    from utils.column_filter import filter_view_columns, parse_use_columns

    views = [{'databaseName': '"hr"', 'name': '"employee.archive"', 'schema': [
        {'name': '"salary.total"'}, {'name': '"employee""id"'},
        {'name': 'private_*'}, {'name': 'private_note'}, {'name': ' other '},
    ]}]
    use_rules = parse_use_columns(json.dumps([{
        'view': 'hr.employee.archive',
        'columns': ['SALARY.TOTAL', 'employee"id', 'private_*', ' other '],
    }]))
    filtered = filter_view_columns(views, [], use_rules)
    assert [field['name'] for field in filtered[0]['schema']] == [
        '"salary.total"', '"employee""id"', 'private_*', ' other ',
    ]


def test_use_columns_removes_partial_primary_keys_and_unlisted_samples_without_mutation():
    from utils.column_filter import filter_view_columns

    views = [{'databaseName': 'hr', 'name': 'employees', 'schema': [
        {'name': 'tenant_id', 'primaryKey': True},
        {'name': 'id', 'primaryKey': True}, {'name': 'name'},
    ], 'viewFieldDataList': [
        {'fieldName': 'tenant_id', 'fieldValues': [1]},
        {'fieldName': '"NAME"', 'fieldValues': ['Anna']},
    ]}]
    original = copy.deepcopy(views)
    filtered = filter_view_columns(views, [], [{'columns': ['ID', 'name']}])[0]
    assert filtered['schema'] == [{'name': 'id'}, {'name': 'name'}]
    assert filtered['viewFieldDataList'] == [{'fieldName': '"NAME"', 'fieldValues': ['Anna']}]
    assert views == original


def test_use_columns_keeps_empty_views_for_existing_document_cleanup():
    from utils.column_filter import filter_view_columns

    views = [{'id': 42, 'databaseName': 'hr', 'name': 'employees', 'schema': [{'name': 'id'}],
              'viewFieldDataList': None, 'associationData': None}]
    filtered = filter_view_columns(views, [], [{'columns': ['unknown_column']}])
    assert filtered == [{'id': 42, 'databaseName': 'hr', 'name': 'employees', 'schema': [],
                         'viewFieldDataList': None, 'associationData': None}]


@pytest.mark.parametrize('mapping,use_rules,removed', [
    ('employees.department_id = departments.id', [{'view': 'hr.employees', 'columns': ['name']}], True),
    ('employees.department_id = departments.id', [{'view': 'org.departments', 'columns': ['name']}], True),
    ('"employees"."department_id" = "departments"."id"',
     [{'view': 'org.departments', 'columns': ['ID']}], False),
    ('hr.employees.department_id = org.departments.id',
     [{'view': 'org.departments', 'columns': ['name']}], True),
    ('"employees"."department.id" = "departments"."id"',
     [{'view': 'hr.employees', 'columns': ['DEPARTMENT.ID']}], False),
    ('"employees"."employee""id" = "departments"."id"',
     [{'view': 'hr.employees', 'columns': ['employee"id']}], False),
    ('employees.department_id = departments.id', [{'view': 'other.departments', 'columns': ['name']}], False),
    ('employees.department_id = departments.identity', [{'columns': ['id', 'department_id']}], True),
    ('employees.department_id = departments.id',
     [{'columns': ['department_id']}, {'view': 'org.departments', 'columns': ['id']}], False),
    ("employees.name = 'departments.id'", [{'columns': ['name']}], False),
])
def test_use_columns_filters_both_association_endpoints_without_related_schema(mapping, use_rules, removed):
    from utils.column_filter import filter_view_columns

    association = {'mapping': mapping, 'viewDetailsOfTheOtherView': {
        'id': 2, 'databaseName': 'org', 'name': 'departments',
    }}
    views = [{'databaseName': 'hr', 'name': 'employees', 'schema': [{'name': 'name'}],
              'associationData': [association]}]
    original = copy.deepcopy(views)
    filtered = filter_view_columns(views, [], use_rules)
    assert filtered[0]['associationData'] == ([] if removed else [association])
    assert views == original
