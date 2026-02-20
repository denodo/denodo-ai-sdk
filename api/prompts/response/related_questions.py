RELATED_QUESTIONS = """
Generate up to three related questions in plain text format (no markdown) that users can choose from
based solely on the SQL schema supplied. Ensure that each question can be answered directly and accurately
using the retrieved data.

{custom_instructions}

Remember, the questions should be closely related to the provided data and should not require external information.
Return each related question in between <related_question></related_question> tags, like this:

<related_question>...<related_question>
...
<related_question>...</related_question>

If the schema supplied is empty or the execution result is an error/empty, only return:

<N>

Here is the SQL schema for this query: <schema>{schema}</schema>.
Here is the user's question regarding his database: <question>{question}</question>.
Here is the execution result of the SQL query: <execution_result>{sql_response}</execution_result>.

Limit your response to:
    - The related questions, each question in between <related_question></related_question> tags."""
