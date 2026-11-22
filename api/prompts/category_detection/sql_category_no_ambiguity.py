from api.prompts.category_detection.sql_category import BASE_SQL_CATEGORY_SYSTEM, SQL_CATEGORY_USER

SQL_CATEGORY_NO_AMBIGUITY_SYSTEM = BASE_SQL_CATEGORY_SYSTEM.replace(
    "{ambiguity_block}", ""
).replace(
    "{output_instructions}", 
    "        - A brief explanation in <selection_thoughts></selection_thoughts>, followed by the tables needed and query classification in between <query></query> tags, if you answered <cat>SQL</cat>."
)

SQL_CATEGORY_NO_AMBIGUITY = SQL_CATEGORY_NO_AMBIGUITY_SYSTEM + SQL_CATEGORY_USER
