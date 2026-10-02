"""
 Copyright (c) 2026. DENODO Technologies.
 http://www.denodo.com
 All rights reserved.

 This software is the confidential and proprietary information of DENODO
 Technologies ("Confidential Information"). You shall not disclose such
 Confidential Information and shall use it only in accordance with the terms
 of the license agreement you entered into with DENODO.
"""

CHECK_AMBIGUITY = "If false, skip ambiguity detection."

VQL = "The VQL query to execute against the Denodo Platform."

VQL_EXECUTE_ROWS_LIMIT = "Maximum number of rows to return from the VQL execution result."

ENABLE_QUERY_FIXER = (
    "If enabled, the LLM will try to automatically fix the VQL query if the first VQL query generated fails."
)

ENABLE_QUERY_REVIEWER = (
    "If enabled, the LLM will review the VQL query if the first VQL query generated returns no rows."
)

VERBOSE_ANSWER_QUESTION = (
    "If true, the LLM will return a natural language response in the answer key based on the selected mode. "
    "In data/default mode, it uses the execution result from the generated SQL. In metadata mode, it uses the "
    "vector search output of the schema of the relevant views. If set to false, data/default mode returns the "
    "execution result and generated SQL query, while metadata mode returns the vector search output of the schema "
    "of the relevant views. Setting to false is the recommended option when using the endpoint as a tool."
)

VERBOSE_DATA = (
    "If true, the LLM will receive the execution result from the generated SQL and return a natural language "
    "response in the answer key. If set to false, it will return the execution result and the generated SQL query. "
    "Setting to false is the recommended option when using the endpoint as a tool."
)

VERBOSE_METADATA = (
    "If true, the LLM will receive the vector search output of the schema of the relevant views and return a "
    "natural language response in the answer key. If set to false, it will return the vector search output of the "
    "schema of the relevant views. Setting to false is the recommended option when using the endpoint as a tool."
)
