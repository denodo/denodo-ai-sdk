from api.prompts.category_detection.direct_sql_category import BASE_DIRECT_SQL_CATEGORY_SYSTEM, DIRECT_SQL_CATEGORY_USER

DIRECT_SQL_CATEGORY_NO_AMBIGUITY_SYSTEM = BASE_DIRECT_SQL_CATEGORY_SYSTEM.replace(
    "{ambiguity_block}", ""
).replace(
    "{output_instructions}", 
    "        - A brief explanation in <selection_thoughts></selection_thoughts>, followed by the tables needed and query classification in between <query></query> tags."
)

DIRECT_SQL_CATEGORY_NO_AMBIGUITY = DIRECT_SQL_CATEGORY_NO_AMBIGUITY_SYSTEM + DIRECT_SQL_CATEGORY_USER
