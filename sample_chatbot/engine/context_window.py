"""
 Copyright (c) 2026. DENODO Technologies.
 http://www.denodo.com
 All rights reserved.

 This software is the confidential and proprietary information of DENODO
 Technologies ("Confidential Information"). You shall not disclose such
 Confidential Information and shall use it only in accordance with the terms
 of the license agreement you entered into with DENODO.
"""

"""
Context-window accounting for the sample chatbot.

The configured window is a reference, not something the provider reports.
The model's max output tokens are reserved, so a call is trimmed when the
prompt would leave no room for that answer. The oldest complete question/answer
pairs are dropped until the most recent 25% of the window remains, and never
more than COMPACTION_KEEP_TOKENS. The conversation then grows again until the
reserved answer no longer fits.

View schemas returned by metadata_search are kept once inside that window.
A later search that hits the same view is rewritten so the model is told the
schema is already in context, instead of receiving it again.
"""

import json
import logging
import re

from langchain_core.utils.function_calling import convert_to_openai_tool

from utils.schema_catalog.helpers import normalize_table_name
from utils.utils import calculate_tokens

COMPACTION_KEEP_TOKENS = 30000
MIN_CONTEXT_WINDOW = 16000
MAX_CONTEXT_WINDOW = 10000000
ALREADY_IN_CONTEXT_NOTE = "This view is already included in the context in a previous tool call."

_OUTPUT_RE = re.compile(r"<output>(.*?)</output>", re.DOTALL)
# metadata_search indents the first line of the schema dump, so the header is
# "        # Table:" Later tables in the
# same dump, and the "# Tag:" appendix, start at the beginning of the line.
_TABLE_SPLIT_RE = re.compile(r"(?=^[ \t]*# Table:)", re.MULTILINE)
_TAG_SPLIT_RE = re.compile(r"(?=^[ \t]*# Tag:)", re.MULTILINE)
_TABLE_HEADER_RE = re.compile(r"^[ \t]*# Table:")

SEGMENT_LABELS = (
    ("conversation", "Conversation"),
    ("views", "Views"),
    ("tools", "Tools"),
    ("skills", "Skills"),
    ("system_prompt", "System prompt"),
)

def compaction_keep_tokens(context_window):
    """25% of the configured window, and never more than COMPACTION_KEEP_TOKENS."""
    return min(COMPACTION_KEEP_TOKENS, context_window // 4)

def input_budget_tokens(context_window, max_output_tokens):
    """Tokens the prompt may use so the reserved answer still fits in the window."""
    return max(1, context_window - max_output_tokens)

def message_content_text(message):
    return _content_to_text(message.content)

def _content_to_text(content):
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)
    parts = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
            continue
        if not isinstance(item, dict):
            parts.append(str(item))
            continue
        text = item.get("text") or item.get("content") or ""
        parts.append(text if isinstance(text, str) else str(text))
    return "".join(parts)

def is_human_message(message):
    return message.type in ("human", "user")

def is_metadata_search_message(message):
    return message.type == "tool" and message.name == "metadata_search"

def message_tokens(message):
    pieces = [message_content_text(message)]
    for call in getattr(message, "tool_calls", None) or []:
        name = call.get("name") or ""
        args = call.get("args") or {}
        pieces.append(str(name))
        pieces.append(json.dumps(args, default=str, sort_keys=True))
    text = "\n".join(piece for piece in pieces if piece)
    return calculate_tokens(text)

def messages_tokens(messages):
    return sum(message_tokens(message) for message in messages)

def tools_token_count(tools):
    if not tools:
        return 0
    chunks = [
        json.dumps(convert_to_openai_tool(tool), default=str, sort_keys=True)
        for tool in tools
    ]
    return calculate_tokens("\n".join(chunks))

def split_prompt_tokens(system_text, skills_text):
    if not system_text:
        return 0, 0
    if skills_text and skills_text in system_text:
        remainder = system_text.replace(skills_text, "", 1)
        return calculate_tokens(remainder), calculate_tokens(skills_text)
    return calculate_tokens(system_text), 0

def conversation_blocks(messages):
    """Index ranges of complete turns: each human message through the one before the next."""
    blocks = []
    start = None
    for index, message in enumerate(messages):
        if is_human_message(message):
            if start is not None:
                blocks.append((start, index - 1))
            start = index
    if start is not None:
        blocks.append((start, len(messages) - 1))
    return blocks

def kept_block_start(messages, keep_tokens):
    """
    Index of the first message to keep.

    The suffix is complete turns whose token count fits in keep_tokens.
    The newest turn is always kept, even when that single turn is larger than
    keep_tokens, because a question and its answer are not split apart.
    """
    blocks = conversation_blocks(messages)
    if not blocks:
        return 0

    start_index = blocks[-1][0]
    total = 0
    for start, end in reversed(blocks):
        block_tokens = messages_tokens(messages[start:end + 1])
        is_newest = start == blocks[-1][0]
        if not is_newest and total + block_tokens > keep_tokens:
            break
        total += block_tokens
        start_index = start
    return start_index

def newest_blocks_within(messages, keep_tokens):
    """Keep a suffix of complete turns whose token count is within keep_tokens."""
    return list(messages[kept_block_start(messages, keep_tokens):])

def _table_name_from_header(header_line):
    _, _, name = header_line.strip().partition(":")
    return name.strip()

def _rewrite_output(output_text, seen, views):
    tag_parts = _TAG_SPLIT_RE.split(output_text, maxsplit=1)
    body = tag_parts[0]
    tags = tag_parts[1] if len(tag_parts) > 1 else ""
    parts = _TABLE_SPLIT_RE.split(body)
    rewritten = []
    deduped = 0

    for part in parts:
        if not _TABLE_HEADER_RE.match(part):
            rewritten.append(part)
            continue

        lines = part.splitlines(keepends=True)
        header = lines[0]
        name = _table_name_from_header(header)
        key = normalize_table_name(name)
        if not key:
            rewritten.append(part)
            continue

        if key in seen:
            rewritten.append(f"{header}{ALREADY_IN_CONTEXT_NOTE}\n\n")
            deduped += 1
            continue

        seen.add(key)
        views.append({
            "name": name,
            "tokens": calculate_tokens(part),
        })
        rewritten.append(part)

    return "".join(rewritten) + tags, deduped

def dedupe_metadata_views(messages):
    """
    Return a copy of messages where repeated metadata_search schemas are replaced.

    The first copy of a view inside this message list keeps its schema. Later
    copies become a short note. Messages that do not change keep their identity
    so the caller can tell whether the request actually changed.
    """
    seen = set()
    views = []
    deduped = 0
    prepared = []

    for message in messages:
        if not is_metadata_search_message(message):
            prepared.append(message)
            continue

        content = message_content_text(message)
        match = _OUTPUT_RE.search(content)
        if not match:
            prepared.append(message)
            continue

        new_output, replaced = _rewrite_output(match.group(1), seen, views)
        deduped += replaced
        if replaced == 0 and new_output == match.group(1):
            prepared.append(message)
            continue

        new_content = content[:match.start(1)] + new_output + content[match.end(1):]
        if new_content == content:
            prepared.append(message)
            continue
        prepared.append(message.model_copy(update={"content": new_content}))

    return prepared, views, deduped

def received_tool_outputs(original_messages, prepared):
    """
    Tool results whose text in the model request differs from what the tool returned.

    The checkpoint keeps the original result so a later compaction can put a view
    schema back in full. The chat UI uses this list to show the text the model receives.
    """
    original_by_id = {}
    for message in original_messages:
        tool_call_id = getattr(message, "tool_call_id", None)
        if tool_call_id:
            original_by_id[tool_call_id] = message_content_text(message)

    received = []
    for message in prepared:
        tool_call_id = getattr(message, "tool_call_id", None)
        if not tool_call_id:
            continue
        content = message_content_text(message)
        if original_by_id.get(tool_call_id) != content:
            received.append({
                "tool_call_id": tool_call_id,
                "content": content,
            })
    return received

def _usage_payload(prepared, views, deduped_count, system_text, skills_text, tools, context_window, input_budget, keep_tokens, will_compact, turns_total, tool_outputs):
    system_tokens, skills_tokens = split_prompt_tokens(system_text, skills_text)
    tool_tokens = tools_token_count(tools)
    conversation_tokens = messages_tokens(prepared)
    view_tokens = min(sum(view["tokens"] for view in views), conversation_tokens)

    amounts = {
        "conversation": conversation_tokens - view_tokens,
        "views": view_tokens,
        "tools": tool_tokens,
        "skills": skills_tokens,
        "system_prompt": system_tokens,
    }
    segments = [
        {"id": segment_id, "label": label, "tokens": amounts[segment_id]}
        for segment_id, label in SEGMENT_LABELS
    ]
    used = sum(segment["tokens"] for segment in segments)
    turns_kept = len(conversation_blocks(prepared))

    return {
        "context_window": context_window,
        "input_budget": input_budget,
        "used": used,
        "keep_tokens": keep_tokens,
        "will_compact": will_compact,
        "turns_kept": turns_kept,
        "turns_total": turns_total,
        "deduped_views": deduped_count,
        "segments": segments,
        "views": views,
        "received_tool_outputs": tool_outputs,
    }

def prepare_model_messages(messages, system_text, tools, skills_text, context_window, max_output_tokens=0, log=False):
    """
    Build the message list that should be sent to the model, plus a usage report.

    Compaction looks at the conversation after repeated view schemas have been
    removed. If that still leaves no room for the reserved answer, only the
    newest complete turns that fit in 25% of the window (capped at
    COMPACTION_KEEP_TOKENS, and also capped by the room left after the system
    prompt and tools) are kept. Dedupe runs again on that suffix so a view
    dropped with an old turn can be included in full again. If putting that
    schema back still does not fit, another older turn is dropped.
    """
    messages = list(messages)
    input_budget = input_budget_tokens(context_window, max_output_tokens)
    turns_total = len(conversation_blocks(messages))

    deduped, views, deduped_count = dedupe_metadata_views(messages)
    system_tokens, skills_tokens = split_prompt_tokens(system_text, skills_text)
    fixed_tokens = system_tokens + skills_tokens + tools_token_count(tools)
    full_tokens = fixed_tokens + messages_tokens(deduped)
    keep_tokens = min(
        compaction_keep_tokens(context_window),
        max(0, input_budget - fixed_tokens),
    )

    if full_tokens <= input_budget:
        usage = _usage_payload(
            deduped, views, deduped_count, system_text, skills_text, tools,
            context_window, input_budget, keep_tokens, False, turns_total,
            received_tool_outputs(messages, deduped),
        )
        return deduped, usage

    # Turn boundaries match the original list: dedupe rewrites tool text, it
    # does not add or remove messages. Count the budget on the deduped text,
    # then slice the originals so a schema can be restored in full.
    start = kept_block_start(deduped, keep_tokens)
    suffix = list(messages[start:])
    prepared, views, deduped_count = dedupe_metadata_views(suffix)
    while fixed_tokens + messages_tokens(prepared) > input_budget:
        blocks = conversation_blocks(suffix)
        if len(blocks) <= 1:
            break
        start = start + blocks[1][0]
        suffix = list(messages[start:])
        prepared, views, deduped_count = dedupe_metadata_views(suffix)

    will_compact = len(conversation_blocks(prepared)) < turns_total
    if log:
        logging.info(
            "Context window would leave no room for the reserved answer "
            f"({full_tokens} + {max_output_tokens} > {context_window}). "
            f"Keeping the most recent complete question/answer pairs "
            f"({messages_tokens(prepared)} conversation tokens, "
            f"limit {keep_tokens})."
        )
    usage = _usage_payload(
        prepared, views, deduped_count, system_text, skills_text, tools,
        context_window, input_budget, keep_tokens, will_compact, turns_total,
        received_tool_outputs(suffix, prepared),
    )
    if log and usage["used"] > input_budget:
        logging.warning(
            "The newest question and answer still leave no room for the reserved answer "
            f"({usage['used']} + {max_output_tokens} > {context_window}) "
            "after older turns were dropped."
        )
    return prepared, usage
