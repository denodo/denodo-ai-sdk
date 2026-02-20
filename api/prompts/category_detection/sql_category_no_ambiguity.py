from api.prompts.category_detection.ambiguity_block import AMBIGUITY_BLOCK
from api.prompts.category_detection.sql_category import SQL_CATEGORY

SQL_CATEGORY_NO_AMBIGUITY = SQL_CATEGORY.replace(AMBIGUITY_BLOCK, "").replace(
    "        - Either the tables needed and query classification in between <query></query> tags or the ambiguity inputs in between <ambiguity></ambiguity> tags, if you answered <cat>SQL</cat>.",
    "        - The tables needed and query classification in between <query></query> tags, if you answered <cat>SQL</cat>."
)
