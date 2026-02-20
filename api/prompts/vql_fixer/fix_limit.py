FIX_LIMIT = """This VQL query is using LIMIT/FETCH inside a subquery, but my SQL engine doesn't allow LIMIT or FETCH to be used inside a subquery.
CTE is also considered a subquery.

Generate an equivalent VQL query that doesn't use LIMIT or FETCH in a subquery. To solve this, use ROW_NUMBER().

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
