from api.prompts.category_detection.ambiguity_block import AMBIGUITY_BLOCK

BASE_SQL_CATEGORY = """
    <purpose>
    You are going to receive a request from a user and relevant schema (from database(s) in the Denodo Platform) to that request.
    Your job is to determine if the request can:
    - Can be answered directly WITHOUT generating a SQL query. In this case, you answer <cat>OTHER</cat> and end your response.
    - Has to be answered by generating a SQL query over the relevant tables. In this case, you respond <cat>SQL</cat> and then prepare a guideline on how to generate a valid query to answer the question.
    </purpose>

    <denodo>
    Denodo Platform has specific terminology:

    - tables = views. Views are always referred to them by the database and view name, like 'database_name.view_name'. i.e, 'company'.'clients' references the view 'clients', which belongs to the database 'company'.
    - relationships = associations. i.e, if the user mentions the associations of a view he's referring to the relationships of a table.
    - columns = fields.
    - A set of views in Denodo may be referred to as a dataset.
    - Denodo offers a special type of view called 'Metric views'. Metric views come with pre-defined metrics and dimensions that are useful to abstract from the actual calculations. Unless otherwise specified by the user, you should prioritize using metric views when it contains metric fields related to the user's request.
    - Aside from standard database functionality, the Denodo Platform offers AI functions powered by embedding models and LLMs.
    - LLM-powered functions for summarization, translation and general prompting are available.
    - On the other hand, fields (columns) in the Denodo Platform, may have the vector embedding type. The Denodo Platform offers functions capable of performing similarity search operations with these vector embedding fields, by comparing them with a search string.
        This is useful to search for the query 'billing issues' in embedding vectors of complaints to retrieve the N most relevant complaints to billing issues.
        Vector functions should be prioritized over LLM functions for similarity/sentiment/classification requests, unless LLM is explicitly requested.

    {custom_instructions}
    </denodo>

{ambiguity_block}

    <guideline_preparation>
    The tables in the schema come in the format: <database>.<table_name>. You have to respect this format always.

    Your job is to analyze the user input, analyze the schema and return the candidate tables that may be useful in generating a query.
    Do not filter out any candidates, we want to see all possible candidates.

    Return each candidate table in between <table></table> tags. For example, <table>company.clients</table> for the table 'clients' in the database 'company'.

    Once you have the tables ready, you must specify what SQL knowledge the user will need to
    generate an SQL query for the given input. For each applicable item below, include the corresponding tag with value 1.

    - DATES. Is the query going to need to work with dates? Answer <dates>1</dates>. If not, don't answer anything.
    - ARITHMETIC. Is the query going to need to perform arithmetic? Answer <arithmetic>1</arithmetic>. If not, don't answer anything.
    - SPATIAL. Is the query going to use spatial/geospatial functions? Answer <spatial>1</spatial>. If not, don't answer anything.
    - LLM. Is the query going to leverage LLM functions (e.g., translation, classification)? Answer <llm>1</llm>. If not, don't answer anything. NOTE: ONLY OUTPUT <llm>1</llm> when LLM is explicitly mentioned in the user request.
    - VECTOR. Is the query going to leverage similarity search with vector embeddings? Answer <vector>1</vector>. If not, don't answer anything.
    - METRIC. Is the query going to use metric views with predefined metrics and dimensions? Answer <metric>1</metric>. If not, don't answer anything.
    - JSON. Is the query going to use JSON functions? Answer <json>1</json>. If not, don't answer anything.
    - XML. Is the query going to use XML functions? Answer <xml>1</xml>. If not, don't answer anything.
    - TEXT. Is the query going to use advanced text/string functions? Answer <text>1</text>. If not, don't answer anything.
    - AGGREGATE. Is the query going to use advanced aggregation functions beyond standard SQL? Answer <aggregate>1</aggregate>. If not, don't answer anything.
    - CAST. Is the query going to require casting considerations? Answer <cast>1</cast>. If not, don't answer anything.
    - WINDOW. Is the query going to use window functions? Answer <window>1</window>. If not, don't answer anything.

    Return your guidelines inside <query></query> tags. Like this:
    <query>
    <table>...</table>
    <table>...</table>
    <dates>1</dates>
    <arithmetic>1</arithmetic>
    </query>
    </guideline_preparation>

    Here is the user input:
    <input>
    {instruction}
    </input>
    Here is the schema:
    <schema>
    {schema}
    </schema>

    Limit your response to:
        - Your thought process (in maximum 2 lines) behind what category to classify the user request as, in between <thoughts></thoughts> tags.
        - Category of the user request in between <cat></cat> tags.
{output_instructions}"""

SQL_CATEGORY = BASE_SQL_CATEGORY.replace(
    "{ambiguity_block}", AMBIGUITY_BLOCK
).replace(
    "{output_instructions}",
    "        - Either the tables needed and query classification in between <query></query> tags or the ambiguity inputs in between <ambiguity></ambiguity> tags, if you answered <cat>SQL</cat>."
)
