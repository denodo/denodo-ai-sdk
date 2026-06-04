from api.prompts.category_detection.direct_sql_category import BASE_DIRECT_SQL_CATEGORY

DIRECT_SQL_CATEGORY_NO_AMBIGUITY = BASE_DIRECT_SQL_CATEGORY.replace(
    "{ambiguity_block}", ""
).replace(
    "{output_instructions}", 
    "        - The tables needed and query classification in between <query></query> tags."
)
