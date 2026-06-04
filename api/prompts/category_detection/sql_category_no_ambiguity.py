from api.prompts.category_detection.sql_category import BASE_SQL_CATEGORY

SQL_CATEGORY_NO_AMBIGUITY = BASE_SQL_CATEGORY.replace(
    "{ambiguity_block}", ""
).replace(
    "{output_instructions}", 
    "        - The tables needed and query classification in between <query></query> tags, if you answered <cat>SQL</cat>."
)
