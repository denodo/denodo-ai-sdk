from io import StringIO

import pandas as pd


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


def build_execution_result_bundle(execution_result, llm_rows_limit):
    full_rows = get_execution_result_rows(execution_result)
    llm_rows = limit_execution_result_rows(full_rows, llm_rows_limit)

    return {
        "full": full_rows,
        "full_csv": execution_result_to_csv(full_rows),
        "llm": llm_rows,
        "llm_csv": execution_result_to_csv(llm_rows),
    }


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


def execution_result_to_csv(execution_result):
    rows_dict = get_execution_result_rows(execution_result)
    if not rows_dict:
        return ''

    rows = [
        extract_execution_result_row(row_id, row_values)
        for row_id, row_values in rows_dict.items()
    ]

    if not rows:
        return ''

    dataframe = pd.DataFrame(rows)
    ordered_columns = ['row_id'] + [column for column in dataframe.columns if column != 'row_id']
    dataframe = dataframe[ordered_columns]

    csv_buffer = StringIO()
    dataframe.to_csv(csv_buffer, index=False)
    return csv_buffer.getvalue()
