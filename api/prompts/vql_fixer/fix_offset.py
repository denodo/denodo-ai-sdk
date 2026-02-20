FIX_OFFSET = """This VQL query is using LIMIT OFFSET, but my SQL engine doesn't allow LIMIT OFFSET, only LIMIT.

Generate an equivalent VQL query that doesn't use LIMIT OFFSET. To solve this, use ROW_NUMBER().

This is the query:
<vql_query>
{query}
</vql_query>

Here is the schema for the tables present in the VQL query:
<schema>
{schema}
</schema>

This query was generated to answer the following question:
<question>
{question}
</question>

Limit your response to:
- The new query in between <vql></vql> tags."""
