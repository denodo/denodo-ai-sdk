from dataclasses import dataclass, field

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.callbacks import get_usage_metadata_callback

from utils import langfuse
from utils import utils
from api.utils import sdk_utils
from api.utils.ai_tools.prompts import (
    FIX_LIMIT_PROMPT,
    FIX_OFFSET_PROMPT,
    QUERY_FIXER_SYSTEM_PROMPT,
    QUERY_FIXER_TURN_PROMPT,
    QUERY_REVIEWER_SYSTEM_PROMPT,
    QUERY_REVIEWER_TURN_PROMPT,
)

from api.utils.ai_tools.types import empty_tokens, usage_tokens
from api.utils.ai_tools.schema_text import format_schema_text
from api.utils.ai_tools.vql_rules_builder import build_full_vql_restrictions

@dataclass
class FixOutcome:
    """Result of a single query_fixer call. verdict is either "fix" (new VQL query generated) or
    "give_up" (error not fixable at the query level; explains why)."""
    vql: str
    verdict: str = "fix"   # "fix" | "give_up"
    thoughts: str = ""
    tokens: dict = field(default_factory=empty_tokens)

@dataclass
class ReviewOutcome:
    """Result of a single query_reviewer call. verdict is either "keep" (empty result is
    legitimate, original query unchanged) or "rewrite" (new VQL query proposed)."""
    verdict: str          # "keep" | "rewrite"
    vql: str
    thoughts: str = ""
    tokens: dict = field(default_factory=empty_tokens)

@dataclass
class StaticFix:
    """Result of the proactive (pre-execution) static rewrite."""
    vql: str
    kind: str = "none"          # "none" | "limit_subquery" | "limit_offset"
    seed: list = field(default_factory=list)   # [(role, content)] to seed the fixer conversation
    tokens: dict = field(default_factory=empty_tokens)

def _schema_text(query, vector_search_tables, sample_data, k):
    schema = [table for table in vector_search_tables if table['view_name'] in query.replace('"', '')]
    return format_schema_text(schema, [], sample_data, examples_per_table=k)

def _parse_vql_and_thoughts(response):
    response = response.replace('```vql', '<vql>').replace('```', '</vql>').strip()
    vql = utils.custom_tag_parser(response, 'vql', default='')[0].strip()
    thoughts = utils.custom_tag_parser(response, 'thoughts', default='')[0].strip()
    return vql, thoughts

async def _invoke(llm, messages, session_id, run_name):
    chain = llm.llm | StrOutputParser()
    with get_usage_metadata_callback() as cb:
        text = await chain.ainvoke(
            messages,
            config=langfuse.build_config(
                model_id=f"{llm.provider_name}.{llm.model_name}",
                session_id=session_id,
                run_name=run_name,
            ),
        )
    return text, usage_tokens(cb)

# --- Static issue rewrites ---
# Some errors don't need to be executed to know they will fail.
# For example, LIMIT in subquery is a Denodo VQL restriction that can be detected statically
# and fixed with a dedicated prompt. These are known as static issue rewrites.

_STATIC_REWRITES = {
    sdk_utils.VQL_ISSUE_LIMIT_SUBQUERY: (
        FIX_LIMIT_PROMPT, 'limit_subquery',
        'LIMIT or FETCH inside a subquery is not permitted in VQL.',
    ),
    sdk_utils.VQL_ISSUE_LIMIT_OFFSET: (
        FIX_OFFSET_PROMPT, 'limit_offset',
        'LIMIT OFFSET is not permitted in VQL.',
    ),
}

def _as_fixer_turn(query, error, reasoning, vql):
    """Frame an exchange as a query-fixer turn (human error report + AI thoughts/vql),
    so a static rewrite that seeds the fixer conversation reads like a normal fix turn."""
    return [
        ('human', QUERY_FIXER_TURN_PROMPT.format(query=query, query_error=error)),
        ('ai', f"<thoughts>\n{reasoning}\n</thoughts>\n\n<vql>\n{vql}\n</vql>"),
    ]

async def rewrite_static_issue(
    question, query, issue, llm, vector_search_tables,
    sample_data=None,
    vector_search_sample_data_k=3,
    session_id=None,
):
    """Attempt to fix a VQL query where an issue has been detected statically with the dedicated prompt for a known static issue
    (e.g. a LIMIT-in-subquery using ROW_NUMBER()).

    Returns a StaticFix with the rewritten query and the exchange to seed the fixer
    conversation if the rewrite later fails at execution time. The seed is framed as a
    query-fixer turn so it matches the rest of the fixer conversation.
    """
    prompt, kind, error = _STATIC_REWRITES[issue]

    schema = _schema_text(query, vector_search_tables, sample_data, vector_search_sample_data_k)
    human = prompt.format(query=query, schema=schema, question=question)
    response, tokens = await _invoke(llm, [HumanMessage(content=human)], session_id, issue.lower())

    new_vql, thoughts = _parse_vql_and_thoughts(response)
    new_vql = sdk_utils.normalize_vql(new_vql) if new_vql else query
    reasoning = thoughts or "Rewrote the query to use ROW_NUMBER() instead of LIMIT/OFFSET in a subquery."
    seed = _as_fixer_turn(query=query, error=error, reasoning=reasoning, vql=new_vql)
    return StaticFix(vql=new_vql, kind=kind, seed=seed, tokens=tokens)

#---Conversational fixer/reviewer---
class Conversation:
    """A growing chat conversation: one system message + alternating human/ai turns."""

    def __init__(self, system_text, seed=None):
        self.messages = [SystemMessage(content=system_text)]
        for role, content in (seed or []):
            self.messages.append(
                HumanMessage(content=content) if role == 'human' else AIMessage(content=content)
            )

    async def ask(self, llm, human_text, session_id, run_name):
        self.messages.append(HumanMessage(content=human_text))
        text, tokens = await _invoke(llm, self.messages, session_id, run_name)
        self.messages.append(AIMessage(content=text))
        return text, tokens

def make_fixer_conversation(
    question, query, vector_search_tables,
    query_explanation='',
    sample_data=None,
    vector_search_sample_data_k=3,
    can_use_llm=False,
    seed=None,
):
    schema = _schema_text(query, vector_search_tables, sample_data, vector_search_sample_data_k)
    system = QUERY_FIXER_SYSTEM_PROMPT.format(
        vql_restrictions=build_full_vql_restrictions(can_use_llm),
        schema=schema,
        query_explanation=query_explanation,
        question=question,
    )
    return Conversation(system, seed)

async def fixer_step(conversation, llm, query, error, session_id=None):
    human = QUERY_FIXER_TURN_PROMPT.format(query=query, query_error=error)
    response, tokens = await conversation.ask(llm, human, session_id, 'query_fixer')
    vql, thoughts = _parse_vql_and_thoughts(response)

    if not vql or vql.upper() == 'NONE':
        return FixOutcome(vql='', verdict='give_up', thoughts=thoughts, tokens=tokens)
    return FixOutcome(vql=sdk_utils.normalize_vql(vql), verdict='fix', thoughts=thoughts, tokens=tokens)

def make_reviewer_conversation(
    question, query, vector_search_tables,
    sample_data=None,
    vector_search_sample_data_k=3,
    can_use_llm=False,
):
    schema = _schema_text(query, vector_search_tables, sample_data, vector_search_sample_data_k)
    system = QUERY_REVIEWER_SYSTEM_PROMPT.format(
        vql_restrictions=build_full_vql_restrictions(can_use_llm),
        schema=schema,
        question=question,
    )
    return Conversation(system)

async def reviewer_step(conversation, llm, query, note, session_id=None):
    human = QUERY_REVIEWER_TURN_PROMPT.format(query=query, note=note)
    response, tokens = await conversation.ask(llm, human, session_id, 'query_reviewer')
    vql, thoughts = _parse_vql_and_thoughts(response)

    if not vql or vql.upper() == 'OK':
        return ReviewOutcome(verdict='keep', vql=query, thoughts=thoughts, tokens=tokens)
    return ReviewOutcome(verdict='rewrite', vql=sdk_utils.normalize_vql(vql), thoughts=thoughts, tokens=tokens)
