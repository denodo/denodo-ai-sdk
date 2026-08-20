from enum import Enum
from dataclasses import dataclass, field

from utils.data_marketplace.connection import execute_vql
from api.utils import sdk_utils
from api.utils.ai_tools.types import empty_tokens
from api.utils.data_category.fixing import (
    rewrite_static_issue,
    make_fixer_conversation,
    fixer_step,
    make_reviewer_conversation,
    reviewer_step,
)
from utils.data_marketplace.vql_execution_outcomes import ExecutionOutcome
from api.utils.sdk_utils import add_tokens, timing_context

class Resolution(str, Enum):
    """Terminal state of the resolution loop."""
    SUCCESS = "success"
    EMPTY = "empty"
    EXHAUSTED = "exhausted"      # ran out of fix/review attempts
    UNFIXABLE = "unfixable"      # fixer gave up: error not fixable at query level

@dataclass
class ResolvedQuery:
    """The status of a VQL query after it has been executed and resolved (fixed/reviewed)."""
    original_vql: str               # query_to_vql output
    vql: str                        # the resolved VQL query that produced the final outcome
    outcome: ExecutionOutcome
    explanation: str                # cumulative explanation (base + per-attempt log + terminal line)
    resolution: Resolution = Resolution.SUCCESS
    tokens: dict = field(default_factory=empty_tokens)
    attempts: int = 0               # number of fix/review iterations performed

def strip_conditions(explanation):
    """Drop the internal 'Conditions: ...' trailer that query_to_vql appends, keeping
    only the human-facing reasoning."""
    explanation = explanation or ""
    if "Conditions:" in explanation:
        return explanation.split("Conditions:")[0].strip()
    return explanation

class ExplanationLog:
    """Builds the cumulative query explanation: base reasoning + one block per failed
    attempt (attempted VQL, error, fix reasoning) + a terminal status line."""

    def __init__(self, base_explanation):
        self.base = strip_conditions(base_explanation)
        self.entries = []
        self.terminal = ""

    def add(self, attempt, vql, error, reasoning):
        self.entries.append(
            f"--- Fix attempt {attempt} ---\n\n"
            f"The attempted VQL was:\n\n"
            f"<vql>\n{vql}\n</vql>\n\n"
            f"But it failed due to this error:\n\n"
            f"<error>\n{error}\n</error>\n\n"
            f"<reasoning>\n{reasoning}\n</reasoning>"
        )

    def finalize(self, resolution, attempts):
        if resolution == Resolution.SUCCESS:
            self.terminal = "" # No need to append anything when resolved VQL query is successful
        elif resolution == Resolution.EMPTY:
            self.terminal = "---Generated VQL executed correctly but returned no rows---"
        elif resolution == Resolution.UNFIXABLE:
            self.terminal = "---The VQL could not be generated because the error is not fixable at the query level---"
        elif attempts == 0:  # Resolution.EXHAUSTED with no attempts: fixing disabled
            self.terminal = "---Generated VQL failed and automatic query fixing is disabled.---"
        else:  # Resolution.EXHAUSTED
            self.terminal = (
                f"---Generated VQL failed again and reached maximum limit of attempts: {attempts}.---"
            )

    def render(self):
        parts = [self.base, *self.entries]
        if self.terminal:
            parts.append(self.terminal)
        return "\n\n".join(part for part in parts if part)

async def resolve_query(
    request,
    gen,
    auth,
    llm,
    timings,
    vector_search_tables,
    session_id=None,
    sample_data=None,
    custom_headers=None,
    can_use_llm=False,
):
    """This flow takes the generated VQL, executes it and resolves (fixes/reviews) any issues until it works
    or the limit of fix/review attempts is reached. Returns a ResolvedQuery."""

    limit = request.vql_execute_rows_limit
    max_attempts = 2
    k = request.vector_search_sample_data_k

    log = ExplanationLog(gen.explanation)
    tokens = gen.tokens

    # Once a VQL is received, it is normalized and checked for issues.
    # If LIMIT in subquery is detected (via detect_vql_issues) in the VQL query, it goes through a single-shot dedicated fix prompt.
    vql_query = sdk_utils.normalize_vql(gen.vql)
    issues = sdk_utils.detect_vql_issues(vql_query)
    static = None
    if issues:
        with timing_context("llm_time", timings):
            static = await rewrite_static_issue(
                question=request.question,
                query=vql_query,
                issue=issues[0],
                llm=llm,
                vector_search_tables=vector_search_tables,
                sample_data=sample_data,
                vector_search_sample_data_k=k,
                session_id=session_id,
            )
        tokens = add_tokens(tokens, static.tokens)
        vql_query = static.vql

    original_vql = vql_query

    # The VQL query is now executed. If it returns empty, it goes through the query reviewer for max_attempts attempts.
    # If it returns an error, it goes through the query fixer for max_attempts attempts.
    outcome = await _execute(vql_query, auth, limit, timings, custom_headers)

    attempts = 0
    flow = None
    conversation = None
    resolution = None

    # Choose the flow once (fixing/reviewing) based on the first failure, and hold it. The fixer/reviewer
    # can be turned off per-request (enable_query_fixer / enable_query_reviewer);
    # when the relevant one is disabled we present the failure/empty result as-is.
    if outcome.needs_review and request.enable_query_reviewer:
        flow = "review"
        conversation = make_reviewer_conversation(
            question=request.question,
            query=vql_query,
            vector_search_tables=vector_search_tables,
            sample_data=sample_data,
            vector_search_sample_data_k=k,
            can_use_llm=can_use_llm,
        )
    elif outcome.needs_fix and request.enable_query_fixer:
        flow = "fix"
        # If the static rewrite for LIMIT in subquery produces a query that keeps failing,
        # it joins the query fixing flow and that attempt is counted as attempt 1.
        seed = static.seed if static is not None else None
        conversation = make_fixer_conversation(
            question=request.question,
            query=vql_query,
            vector_search_tables=vector_search_tables,
            query_explanation=gen.explanation,
            sample_data=sample_data,
            vector_search_sample_data_k=k,
            can_use_llm=can_use_llm,
            seed=seed,
        )
        if seed:
            attempts += 1
            log.add(
                attempt=attempts,
                vql=gen.vql,
                error="LIMIT/OFFSET in subquery is not permitted in VQL.",
                reasoning="Rewrote the query to remove the LIMIT/OFFSET in subquery using ROW_NUMBER().",
            )

    while attempts < max_attempts and (
            (flow == "fix" and outcome.needs_fix) or
            (flow == "review" and not outcome.is_success)
        ):

        attempts += 1

        if flow == "fix":
            with timing_context("llm_time", timings):
                fix = await fixer_step(conversation, llm, vql_query, outcome.error, session_id)
            tokens = add_tokens(tokens, fix.tokens)
            if fix.verdict == "give_up":
                log.add(
                    attempts, vql_query, outcome.error,
                    fix.thoughts or "The error is not fixable at the query level.",
                )
                resolution = Resolution.UNFIXABLE
                break
            log.add(attempts, vql_query, outcome.error, fix.thoughts)
            vql_query = fix.vql
        else:
            with timing_context("llm_time", timings):
                review = await reviewer_step(conversation, llm, vql_query, _review_note(outcome), session_id)
            tokens = add_tokens(tokens, review.tokens)
            if review.verdict == "keep":
                break
            log_error = "(query returned no rows)" if outcome.is_empty else outcome.error
            log.add(attempts, vql_query, log_error, review.thoughts)
            vql_query = review.vql

        outcome = await _execute(vql_query, auth, limit, timings, custom_headers)

    if resolution is None:
        if outcome.is_success:
            resolution = Resolution.SUCCESS
        elif outcome.is_empty:
            resolution = Resolution.EMPTY
        else:
            resolution = Resolution.EXHAUSTED

    log.finalize(resolution, attempts)

    return ResolvedQuery(
        original_vql=original_vql,
        vql=vql_query,
        outcome=outcome,
        explanation=log.render(),
        resolution=resolution,
        tokens=tokens,
        attempts=attempts,
    )

async def _execute(vql_query, auth, limit, timings, custom_headers=None):
    with timing_context("vql_execution_time", timings):
        return await execute_vql(
            vql=vql_query, auth=auth, limit=limit, custom_headers=custom_headers
        )

def _review_note(outcome):
    if outcome.is_empty:
        return "returned no rows."
    else:
        return f"failed with the following error:\n<query_error>\n{outcome.error}\n</query_error>"
