AMBIGUITY_BLOCK = """
    <ambiguous_queries>
    Sometimes the user input might be ambiguous in regards to what the expected output is
    and you might need to generate clarifying questions to resolve them.

    A user input is considered ambiguous when there is more than one reasonable interpretation
    due to unclear, incomplete, or conflicting information.

    Types of ambiguous query:

    - 'Unclear schema reference' (UNCL_SCHEMA). The question lacks sufficient context to determine which table or column to use for operations
    like filtering, ranking, or aggregation, resulting in multiple plausible interpretations.
        - (e.g., 'the oldest user' could refer to 'age' column or 'registration_date' column)
        - (e.g., 'show the total number of transactions for each customer' if you have tables payments, invoices and orders, where a transaction could be considered a payment/invoice/order)
        - (e.g., 'total employees' if you only have one employees table would not be an ambiguous question, since it can be calculated by a COUNT)
    - 'Temporal ambiguity' (TEMP). Spatial or temporal constraints are underspecified, resulting in multiple possible interpretations at different granularities.
        - (e.g., 'after the 2018 World Cup' could mean immediately after the final match or after the entire tournament year).
    - 'Output schema ambiguity' (OUTPUT). When the expected output of the query could lead to multiple different possibilities depending on the interpretation.
        - (e.g., 'List employees' might refer to retrieving all columns or only a subset of key identifiers such as employee ID and name)
    - 'Qualitative ambiguity' (QUAL). Use of descriptive terms without defined criteria.
        - (e.g., 'top sales employees' could be ranked by columns SUM(order_amount) or COUNT(order_id))
    - 'Missing obligatory input' (MISSING_OBL). Views containing fields marked as [OBLIGATORY] require specific, discrete values to be set for that field to generate any query on them (i.e. using '=' or 'IN'), regardless of the columns being requested. Using ranges (like BETWEEN, <, >) or asking for "all" records is not technically possible.

    If you identify any of these ambiguities in the user input in regards to the schema, generate clarifying questions by
    adding an ambiguous_input object PER ambiguous element in the user input. You can have multiple ambiguous inputs in the user question.
    You can also have multiple ambiguous inputs of the same type in the user input. Include schema evidence, if available, in your clarifying question.
    Use single quotes to quote verbatim any part of the user input, if needed.

    <ambiguity>
    <ambiguous_input>
    <type>UNCL_SCHEMA</type>
    <cl_question>Should I use the age column or the registration_date column to calculate the oldest user?</cl_question>
    </ambiguous_input>
    <ambiguous_input>
    <type>TEMP</type>
    <cl_question>When you mention 'after 2020' do you mean including 2020 or after 2020?</cl_question>
    </ambiguous_input>
    <ambiguous_input>
    <type>MISSING_OBL</type>
    <cl_question>The sales view contains the field 'region', which is an obligatory parameter. What value would you like me to use?</cl_question>
    </ambiguous_input>
    </ambiguity>

    If you detect ambiguity, you would return ONLY the <ambiguity> tag. You wouldn't return the guideline <query></query> tags.

    If you do not identify any ambiguities in the user input in regards to the schema, output ONLY the guideline <query></query> tags:

    <query>
    <table>...</table>
    <table>...</table>
    <dates>1</dates>
    <arithmetic>1</arithmetic>
    </query>

    </ambiguous_queries>
"""
