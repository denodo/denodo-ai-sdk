from api.prompts.category_detection.direct_sql_parts import BASE_DIRECT_SQL_PARTS

DIRECT_SQL_PARTS_NO_AMBIGUITY = BASE_DIRECT_SQL_PARTS.replace(
    "{ambiguity_block}", ""
).replace(
    "{output_instructions}",
    "        - The query classification in between <query></query> tags."
)
