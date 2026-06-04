"""
 Copyright (c) 2026. DENODO Technologies.
 http://www.denodo.com
 All rights reserved.
"""

def get_execution_result_rows(execution_result):
    if not isinstance(execution_result, dict) or not execution_result:
        return {}

    return {
        row_id: row_values
        for row_id, row_values in execution_result.items()
        if isinstance(row_id, str) and row_id.startswith("Row ")
    }

def get_full_execution_result_rows(execution_result):
    if not isinstance(execution_result, dict):
        return {}

    return execution_result.get("full", {})

def limit_execution_result_rows(execution_result, rows_limit):
    rows = get_execution_result_rows(execution_result)
    if not rows or rows_limit is None:
        return rows

    limited_rows = {}
    for index, (row_id, row_values) in enumerate(rows.items(), start=1):
        if index > rows_limit:
            break
        limited_rows[row_id] = row_values
    return limited_rows

def extract_execution_result_row(row_id, row_values):
    row = {'row_id': row_id}
    if not isinstance(row_values, list):
        return row

    for column in row_values:
        if not isinstance(column, dict):
            continue

        column_name = column.get('columnName')
        if not column_name:
            continue

        row[column_name] = column.get('value')

    return row
