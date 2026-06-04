from io import StringIO

from utils.execution_result_helpers import (
    extract_execution_result_row,
    get_execution_result_rows,
    get_full_execution_result_rows,
    limit_execution_result_rows,
)

def build_execution_result_bundle(execution_result, llm_rows_limit):
    full_rows = get_execution_result_rows(execution_result)
    llm_rows = limit_execution_result_rows(full_rows, llm_rows_limit)

    return {
        "full": full_rows,
        "full_csv": execution_result_to_csv(full_rows),
        "llm": llm_rows,
        "llm_csv": execution_result_to_csv(llm_rows),
    }

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

    import pandas as pd

    dataframe = pd.DataFrame(rows)
    ordered_columns = ['row_id'] + [column for column in dataframe.columns if column != 'row_id']
    dataframe = dataframe[ordered_columns]

    csv_buffer = StringIO()
    dataframe.to_csv(csv_buffer, index=False)
    return csv_buffer.getvalue()
