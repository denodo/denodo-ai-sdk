METADATA_CATEGORY_RESPONSE_MARKDOWN = """    Always answer in markdown format:
        - Structure your answer in a way that it's readable and visually easy to understand.
        - Use bold, italics and tables in markdown when appropriate to better illustrate the response.
        - You cannot use markdown headings, instead use titles in bold to separate sections, if needed."""

METADATA_CATEGORY_RESPONSE_PLAIN = """    Answer in plain text only. Do not use markdown.
        - Structure your answer clearly."""

METADATA_CATEGORY = """You are going to receive a user input from an employee and relevant schema (from a company's Denodo database) to that user input.

    In Denodo databases, some terminology may be different:

    - Tables are called views. Therefore, if the user mentions 'views' simply replace views for tables.
    - Associations are called relationships. Therefore, if the user mentions the 'relationships' of a view he's asking about the associations of a table.
    - A user may refer to the a set of tables as a 'dataset'. In this instance, simply answer regarding that set of tables.
    {custom_instructions}

    Now, your job is to determine how to answer the user input.
    To do this, you have to determine if the user input can be answered using only the relevant schema provided WITHOUT generating a SQL query.
    If the user input is specifically asking about the schema of table names, structure of tables, column information, schema, etc then you don't need to generate an SQL query. In this case, answer <cat>METADATA</cat>.
    If the user input is asking about values, rows or actual data in the tables, then you would need to generate an SQL query. In this case, answer <cat>OTHER</cat>.

    For you to answer <cat>METADATA</cat>, the user input must SPECIFICALLY ask for metadata/schema information. For example:

    - What views do we have related to this topic?
    - What is the structure of this table?
    - What relationships does this table have?
    - What datasets do we have?
    - What data do we have?

    These would be METADATA questions. However, if the user input is asking specific questions about the values of data, like:

    - What is the list of products?
    - What doctors are there?

    Then that would NOT be a METADATA question, and we would answer <cat>OTHER</cat>.

    Write down your thought process in between <thoughts></thoughts> tags, with a short explanation. For example:

    <thoughts>
    The user is asking about X, therefore I can (or I can't) answer with (or without) generating an SQL query.
    </thoughts>

    If you responded with <cat>OTHER</cat> your job is done and you don't need to continue responding.
    If you responded with <cat>METADATA</cat>, you will also have to generate a response to answer the user input.
    When answering the user input, be truthful and answer only with the information you have received in the schema. Do not speculate.
    When answering with a table, avoid including columns where ALL the values of that column are empty.

{metadata_response_instructions}

    Return the answer in between <response></response> tags.

    Finally, also:
        - Generate up to three related questions in plain text format (no markdown) that users can choose from based solely on the the schema provided. Ensure that each question can be answered directly
          and accurately using the retrieved data (by generating an SQL query or not, doesn't matter). Remember, the questions should be closely related to the provided data and should not require external information.
        - Return each related question in between <related_question></related_question> tags.

    Here is the user input: <input>{instruction}</input>.
    Here is the schema: <schema>{schema}</schema>.

    Limit your response to:
        - Your thought process (in maximum 2 lines) of what category to choose in between <thoughts></thoughts>.
        - The category of the user input in between <cat></cat> tags.
        - The response to the user input in between <response></response> tags ONLY if you answered <cat>METADATA</cat>.
        - The related questions in plain text format (no markdown) in between <related_question></related_question> tags ONLY if you answered <cat>METADATA</cat>."""
