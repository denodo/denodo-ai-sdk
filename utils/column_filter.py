"""Optional column selection and omissions for Data Marketplace metadata ingestion."""

from copy import deepcopy
import json
import re


_IDENTIFIER = r'"(?:[^"]|"")+"|[^\W\d][\w$]*'
_IDENTIFIER_TOKEN = re.compile(_IDENTIFIER)
# Skip SQL string literals so their contents cannot be mistaken for references.
_MAPPING_TOKEN = re.compile(
    rf"'(?:[^']|'')*'|(?P<reference>(?:{_IDENTIFIER})(?:\s*\.\s*(?:{_IDENTIFIER}))+)",
)


def parse_ignore_columns(value: str) -> list[dict]:
    """Validate the JSON query parameter while preserving literal column names."""
    return _parse_column_rules(value, 'ignore_columns')


def parse_use_columns(value: str) -> list[dict]:
    """Validate optional column selection rules with the same shape as omissions."""
    return _parse_column_rules(value, 'use_columns')


def _parse_column_rules(value: str, parameter: str) -> list[dict]:
    if not isinstance(value, str):
        raise ValueError(f'{parameter} must be a JSON string containing a list of rules')
    if not value.strip():
        return []
    try:
        rules = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f'{parameter} must contain valid JSON') from exc
    if not isinstance(rules, list):
        raise ValueError(f'{parameter} must contain a JSON list of rules')
    for index, rule in enumerate(rules):
        prefix = f'{parameter} rule {index + 1}'
        if not isinstance(rule, dict):
            raise ValueError(f'{prefix} must be an object with columns and an optional view')
        if set(rule) - {'columns', 'view'}:
            raise ValueError(f'{prefix} only accepts columns and view')
        columns = rule.get('columns')
        if not isinstance(columns, list) or not columns:
            raise ValueError(f'{prefix}.columns must be a nonempty list of column names')
        if any(not isinstance(column, str) or not column.strip() for column in columns):
            raise ValueError(f'{prefix}.columns must contain only nonempty strings')
        if 'view' in rule:
            view = rule['view']
            if (not isinstance(view, str) or '.' not in view
                    or any(not part.strip() for part in view.split('.', 1))
                    or view != view.strip() or '"' in view):
                raise ValueError(f'{prefix}.view must be an unquoted database.view name')
    return rules


def _identifier_name(name):
    """Decode a quoted metadata identifier, including escaped double quotes."""
    if len(name) >= 2 and name.startswith('"') and name.endswith('"'):
        return name[1:-1].replace('""', '"')
    return name


def _view_name(view):
    # Match the canonical database.view names used by schema_catalog.
    return f"{view.get('databaseName', '')}.{view.get('name', '')}".replace('"', '')


def _association_uses_hidden_column(association, view, is_hidden):
    endpoints = [view, association.get('viewDetailsOfTheOtherView', {})]
    for token in _MAPPING_TOKEN.finditer(association.get('mapping', '')):
        reference = token.group('reference')
        if reference is None:
            continue
        parts = [_identifier_name(part.group()) for part in _IDENTIFIER_TOKEN.finditer(reference)]
        qualifier, column = parts[:-1], parts[-1]
        for endpoint in endpoints:
            name = _identifier_name(endpoint.get('name', ''))
            database = _identifier_name(endpoint.get('databaseName', ''))
            if qualifier in ([name], [database, name]) and is_hidden(_view_name(endpoint), column):
                return True
    return False


def _columns_by_scope(rules):
    columns_by_scope = {}
    for rule in rules:
        columns_by_scope.setdefault(rule.get('view'), set()).update(
            column.casefold() for column in rule['columns']
        )
    return columns_by_scope


def filter_view_columns(views: list[dict], rules: list[dict], use_rules: list[dict] | None = None) -> list[dict]:
    """Select fields, then omit configured fields and associations without changing input."""
    if not rules and not use_rules:
        return views
    ignored_by_scope = _columns_by_scope(rules)
    used_by_scope = _columns_by_scope(use_rules or [])
    global_ignored = ignored_by_scope.get(None, set())
    global_used = used_by_scope.get(None, set())

    def is_hidden(name, column):
        column = column.casefold()
        if column in global_ignored or column in ignored_by_scope.get(name, ()):
            return True
        # Check membership directly so associations to unfetched views need no schema.
        return ((None in used_by_scope or name in used_by_scope)
                and column not in global_used and column not in used_by_scope.get(name, ()))

    filtered_views = []
    for view in views:
        name = _view_name(view)
        schema = view.get('schema') or []
        kept_schema = [field for field in schema if not is_hidden(name, _identifier_name(field['name']))]
        samples = view.get('viewFieldDataList') or []
        kept_samples = [sample for sample in samples
                        if not is_hidden(name, _identifier_name(sample['fieldName']))]
        associations = view.get('associationData') or []
        kept_associations = [association for association in associations
                             if not _association_uses_hidden_column(association, view, is_hidden)]
        if (len(kept_schema) == len(schema) and len(kept_samples) == len(samples)
                and len(kept_associations) == len(associations)):
            filtered_views.append(view)
            continue
        filtered = dict(view, schema=kept_schema)
        if len(kept_samples) != len(samples):
            filtered['viewFieldDataList'] = kept_samples
        if len(kept_associations) != len(associations):
            filtered['associationData'] = kept_associations
        filtered = deepcopy(filtered)
        # A surviving subset of a composite key is not itself a unique key.
        if any(field.get('primaryKey') is True and is_hidden(name, _identifier_name(field['name']))
               for field in schema):
            for field in filtered['schema']:
                field.pop('primaryKey', None)
        filtered_views.append(filtered)
    return filtered_views
