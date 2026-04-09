from dataclasses import dataclass, field

from api.utils.ai_tools.types import empty_tokens


@dataclass
class QueryExecutionResult:
    vql_query: str
    execution_result: object
    status_code: int
    timings: dict
    fixer_history: list = field(default_factory=list)
    tokens: dict = field(default_factory=empty_tokens)
