QUERY_FIXER = """You are a VQL query language expert.
Here are the VQL generation rules:
<vql_rules>
{vql_restrictions}
</vql_rules>

Here is a VQL query:
<vql_query>
{query}
</vql_query>

Here is the schema for the tables present in the VQL query:
<schema>
{schema}
</schema>

This VQL did not work and failed with error:
<query_error>
{query_error}
</query_error>

This was the thought process behind the generation of the previous VQL:
<query_explanation>
{query_explanation}
<query_explanation>

This query was generated to answer the following question:
<question>
{question}
</question>

Analyze the error, check the VQL rules again and fix the query to correctly answer the question.

Limit your response to:
    - Your thought process in 50-100 words on why the query failed and how to fix it based on the VQL rules provided and the expected answer from the question, in between <thoughts></thoughts> tags.
    - The fixed VQL query in between <vql></vql> tags."""
