from api.prompts.category_detection.ambiguity_block import AMBIGUITY_BLOCK
from api.prompts.category_detection.direct_sql_category import DIRECT_SQL_CATEGORY

DIRECT_SQL_CATEGORY_NO_AMBIGUITY = DIRECT_SQL_CATEGORY.replace(AMBIGUITY_BLOCK, "").replace(
    "        - Either the tables needed and query classification in between <query></query> tags or the ambiguity clarification questions in between <ambiguity></ambiguity> tags.",
    "        - The tables needed and query classification in between <query></query> tags."
)
