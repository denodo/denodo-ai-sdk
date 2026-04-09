from dataclasses import dataclass, field


def empty_tokens():
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }


@dataclass
class LLMCallResult:
    text: str
    tokens: dict = field(default_factory=empty_tokens)


@dataclass
class CategoryDecision:
    category: str
    category_response: str
    related_questions: list
    tokens: dict = field(default_factory=empty_tokens)
