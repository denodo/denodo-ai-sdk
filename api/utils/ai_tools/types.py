from dataclasses import dataclass, field

def empty_tokens():
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }

def usage_tokens(callback):
    """Extract token usage from a langchain get_usage_metadata_callback, or zeros."""
    return next(iter(callback.usage_metadata.values())) if callback.usage_metadata else empty_tokens()

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
