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
Durable chatbot memory, stored in the conversation history database.

Each memory is one row in ``memories``, in the
same database as chat history.

Memories are per-user. Each agent (including the general global chat agent)
has its own memories. There are three kinds:

- ``user``: a fact or preference about the person, with no metadata link.
  For example, that they like to be called Jamie instead of James. Also known as "about you" memories.
  This type of memory is per-user, per-agent. This means it is not automatically shared across agents.
- ``user-metadata``: a personal preference about specific metadata, linked
  to at least one view, database, or tag. For example, that Jamie likes
  the field salary in samples_bank.loan to always show the currency sign.
  This type of memory is per-user, per-agent. This means it is not automatically shared across agents.
  The same preference with no link would be a ``user`` memory. Also known as "data preferences" memories.
- ``metadata``: an objective fact about the metadata that is not in the
  metadata itself, linked to at least one view, database, or tag. For
  example, that the currency of salary in samples_bank.loan is USD.
  This type of memory is per-user and shared across all agents.
  One name is one fact: a write from any agent replaces that fact.

``user`` and ``user-metadata`` memories belong to one agent. A specialized
agent can also see the general agent's ``user`` and ``user-metadata``
memories when its YAML sets ``share_general_memory`` (on by default).
A write or delete then updates that shared row, unless this agent already
has its own memory of the same name.

A memory name is unique for one user. ``prefers-eur`` cannot be saved again
as another type, or on another agent. A write may only replace the row it
already owns: this agent's row, the general agent's row when sharing is on
and this agent has no row of its own, or the one metadata fact of that name.
Any other row with that name is left in place and the write is refused.

The ``user`` memories index is loaded into the system prompt. Only the first 200
lines are loaded. ``user-metadata`` and ``metadata`` have no such cap because they are
attached to ``metadata_search`` results, only when a linked view, database,
or tag appears in those results.
"""

import json
import re
import logging
import threading
from datetime import datetime, timezone

import yaml

from utils.database_utils import UserMemories

MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
MAX_BODY_LENGTH = 100000
MAX_LINK_NAME_LENGTH = 256
MAX_LINKS = 100

# The user-memory index loaded into the system prompt is capped at 200
# lines. A write near that cap asks the agent to shorten the index. A
# write past it still succeeds.
MAX_INDEX_LINES = 200
NEAR_INDEX_LINES = 180

MEMORY_TYPES = ("user", "user-metadata", "metadata")
GLOBAL_AGENT_ID = "global"
# Kinds a specialized agent may inherit from the general agent.
# 'metadata' is not in this list: it belongs to the user and every agent
# of that user can read it.
SHARED_MEMORY_TYPES = ("user", "user-metadata")
LINKED_MEMORY_TYPES = ("user-metadata", "metadata")
LINK_KINDS = ("view", "database", "tag")
_LINK_SUFFIX = {"view": "views", "database": "databases", "tag": "tags"}

class _Quoted(str):
    """String value that is dumped in double quotes. Keys stay plain."""

class _QuotedDumper(yaml.SafeDumper):
    """Dumper that honors ``_Quoted`` values."""

def _represent_quoted(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", str(data), style='"')

_QuotedDumper.add_representer(_Quoted, _represent_quoted)

def _q(value):
    return _Quoted(value)

_NAME_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_MEMORIES_BLOCK = re.compile(r"<memories>.*?</memories>", re.DOTALL)
_PROMPT_MEMORY_BLOCK = re.compile(
    r"\n*<memory>\s*Durable memory persists.*?</memory>\s*",
    re.DOTALL,
)
_MEMORY_TOOL_LINE = (
    "Facts that should persist across sessions belong in memory. "
    "Read and write those with the memory tools."
)

_locks_guard = threading.Lock()
_user_locks = {}
_store_lock = threading.Lock()
_store_ready = False

class MemoryError(Exception):
    """Raised when a memory cannot be read or written."""

def ensure_memory_store():
    """Create the memory tables in the conversation history database."""
    global _store_ready
    with _store_lock:
        if _store_ready:
            return
        UserMemories.init_db()
        _store_ready = True

def _agent_id(agent_id):
    agent_id = str(agent_id or "").strip()
    return agent_id or GLOBAL_AGENT_ID

def _visible_agent_ids(agent_id, include_shared_general=False):
    """Agents whose user/user-metadata memories this agent may read, own first."""
    agent_id = _agent_id(agent_id)
    if include_shared_general and agent_id != GLOBAL_AGENT_ID:
        return [agent_id, GLOBAL_AGENT_ID]
    return [agent_id]

def _load_visible(username, memory_type, agent_id, include_shared_general=False):
    """Entries of one kind visible to an agent.

    ``user`` and ``user-metadata`` stay on one agent, plus the general
    agent's copies when sharing is on. The agent's own copy wins a name
    clash. ``metadata`` is per user: every agent sees every metadata memory
    that user has saved, whichever agent saved it.
    """
    if memory_type == "metadata":
        return _load_metadata(username, agent_id)
    if memory_type in SHARED_MEMORY_TYPES:
        scopes = _visible_agent_ids(agent_id, include_shared_general)
    else:
        scopes = [_agent_id(agent_id)]
    records = []
    seen = set()
    for scope in scopes:
        for record in _load_entries(username, memory_type, scope):
            if record["name"] in seen:
                continue
            seen.add(record["name"])
            records.append(record)
    return records

def _all_metadata(username):
    """Every metadata row this user has, including duplicate names."""
    username = _validate_username(username)
    ensure_memory_store()
    return [
        _record_from_stored(row)
        for row in UserMemories.list_type_for_user(username, "metadata")
    ]

def _metadata_named(username, name):
    """Every copy of one metadata name. A user should have only one."""
    return [record for record in _all_metadata(username) if record["name"] == name]

def _rows_named(username, name):
    """Every memory this user has under this name, any type, any agent."""
    found = []
    for memory_type in MEMORY_TYPES:
        for row in UserMemories.list_type_for_user(username, memory_type):
            if row["name"] == name:
                found.append(_record_from_stored(row))
    return found

def _name_conflict(username, name, memory_type, target_agent):
    """A different memory that already uses this name, or None.

    The row this write replaces is not a conflict. Every metadata copy of
    this same name is that one fact, so those copies are not a conflict
    either. The write deletes the spare copies.
    """
    target_agent = _agent_id(target_agent)
    for record in _rows_named(username, name):
        if memory_type == "metadata" and record["type"] == "metadata":
            continue
        agent = record.get("agent_id") or GLOBAL_AGENT_ID
        if record["type"] == memory_type and agent == target_agent:
            continue
        return record
    return None

def _name_taken_message(record, name):
    return (
        f"A {record['type']} memory named '{name}' already exists. "
        "Delete it or choose another name."
    )

def _shared_general_memory(username, memory_type, name, agent_id, include_shared_general):
    """The general agent's row of this name, when this agent may change it.

    Used only when this agent has no row of its own. Sharing off, or a call
    on the general agent itself, returns None.
    """
    if memory_type not in SHARED_MEMORY_TYPES:
        return None
    if not include_shared_general or agent_id == GLOBAL_AGENT_ID:
        return None
    for record in _load_entries(username, memory_type, GLOBAL_AGENT_ID):
        if record["name"] == name:
            return record
    return None

def _preferred_metadata(copies, agent_id):
    """The copy a write or a read should keep. The current agent wins a tie."""
    agent_id = _agent_id(agent_id)
    for record in copies:
        if (record.get("agent_id") or GLOBAL_AGENT_ID) == agent_id:
            return record
    return copies[0] if copies else None

def _load_metadata(username, agent_id):
    """One metadata memory per name for this user, current agent first.

    An older duplicate name is hidden. The next write of that name drops it.
    """
    prefer = _agent_id(agent_id)
    records = _all_metadata(username)
    records.sort(key=lambda record: (
        0 if (record.get("agent_id") or GLOBAL_AGENT_ID) == prefer else 1,
        record.get("name") or "",
    ))
    unique = []
    seen = set()
    for record in records:
        if record["name"] in seen:
            continue
        seen.add(record["name"])
        unique.append(record)
    return unique

def render_user_memories_content(username, agent_id=GLOBAL_AGENT_ID, include_shared_general=False):
    """Index text of this user's 'user' memories, without the wrapper tags.

    This fills the ``{memories}`` placeholder of the system prompt when the
    engine is built, so it is fixed for the life of that engine. Only
    link-free ``user`` memories are listed. ``user-metadata`` and
    ``metadata`` memories surface through ``metadata_search`` instead.
    """
    try:
        records = _load_visible(username, "user", agent_id, include_shared_general)
    except MemoryError:
        logging.warning("Skipping user memories for an invalid username.")
        records = []
    kept, truncated = _truncate_index(_index_text(records))
    lines = []
    if kept:
        lines.append("\n".join(kept))
    if truncated:
        lines.append(
            "The memories index is over the 200-line limit, so later lines were left out. "
            "Rewrite it by merging or dropping stale memories next time you deal with memories."
        )
    return "\n".join(line for line in lines if line)

def render_user_memories_block(username, agent_id=GLOBAL_AGENT_ID, include_shared_general=False):
    """Index of this user's 'user' memories, wrapped in ``<memories>`` tags."""
    inner = render_user_memories_content(username, agent_id, include_shared_general)
    if inner:
        return f"<memories>\n{inner}\n</memories>"
    return "<memories>\n</memories>"

def is_memory_enabled(username, agent_id):
    """Whether this agent should form and use memories for this user.

    Missing preference means on.
    """
    ensure_memory_store()
    return UserMemories.is_enabled(username, agent_id or "global")

def set_memory_enabled(username, agent_id, enabled):
    """Turn memory formation on or off for one user on one agent."""
    ensure_memory_store()
    UserMemories.set_enabled(username, agent_id or "global", bool(enabled))

def strip_memory_prompt(system_text):
    """Remove the memory instructions and the memory index placeholder.

    Used when memory formation is off for this agent. A ``<memories>``
    fragment inside custom instructions is left alone, because the
    placeholder owned by the chatbot prompt is the last block.
    """
    if not system_text:
        return system_text
    text = _PROMPT_MEMORY_BLOCK.sub("\n\n", system_text)
    matches = list(_MEMORIES_BLOCK.finditer(text))
    if matches:
        match = matches[-1]
        text = text[:match.start()] + text[match.end():]
    text = text.replace(_MEMORY_TOOL_LINE, "")
    return re.sub(r"\n{3,}", "\n\n", text)

def render_metadata_memories_section(username, agent_id, response, include_shared_general=False):
    """Index lines for linked memories that match a ``metadata_search``.

    Covers this agent's ``user-metadata`` and ``metadata`` memories, plus
    the general agent's ``user-metadata`` ones when sharing is on. Nothing
    is attached unless a linked view, database, or tag appears in the
    search results.
    """
    if not isinstance(response, dict) or response.get("error"):
        return ""
    views, databases, tags = _resources_from_metadata_response(response)
    if not views and not databases and not tags:
        return ""
    try:
        records = []
        for memory_type in LINKED_MEMORY_TYPES:
            records.extend(_load_visible(username, memory_type, agent_id, include_shared_general))
    except MemoryError:
        return ""
    matched = [
        record for record in records
        if _links_match_resources(record.get("links"), views, databases, tags)
    ]
    if not matched:
        return ""
    sections = []
    metadata_lines = [_index_line(record) for record in matched if record.get("type") == "metadata"]
    user_metadata_lines = [_index_line(record) for record in matched if record.get("type") == "user-metadata"]
    if metadata_lines:
        sections.append(
            "<metadata_memories>\n"
            "Metadata memories for these results. Read one with read_memory before applying it.\n"
            + "\n".join(metadata_lines)
            + "\n</metadata_memories>"
        )
    if user_metadata_lines:
        sections.append(
            "<user-metadata_memories>\n"
            "User-metadata memories for these results. Read one with read_memory before applying it.\n"
            + "\n".join(user_metadata_lines)
            + "\n</user-metadata_memories>"
        )
    return "\n\n" + "\n\n".join(sections)

def list_memories(username, memory_type=None, link_kind=None, link_name=None, query=None, agent_id=GLOBAL_AGENT_ID, include_shared_general=False):
    """Return this user's memories for one agent, optionally filtered.

    With sharing on, a specialized agent also lists the general agent's
    ``user`` and ``user-metadata`` memories. ``metadata`` memories are listed
    from every agent this user has.
    """
    types = (memory_type,) if memory_type else MEMORY_TYPES
    if memory_type:
        _validate_type(memory_type)
    link_kind = _blank_to_none(link_kind)
    link_name = _blank_to_none(link_name)
    query = _blank_to_none(query)
    if link_kind and link_kind != "none":
        _validate_link_kind(link_kind)
    records = []
    for current_type in types:
        records.extend(_load_visible(username, current_type, agent_id, include_shared_general))
    return [
        record for record in records
        if _matches_filter(record, link_kind, link_name, query)
    ]

def list_metadata_for_resource(link_kind, link_name):
    """Metadata memories every user attached to one view, database, or tag.

    A memory linked to several resources is included when any one of them
    matches. User memories are never included, even when they carry the same link.
    """
    link_kind = _validate_link_kind(link_kind)
    link_name = _validate_link_name(link_kind, link_name)
    ensure_memory_store()
    return [
        _record_from_stored(row)
        for row in UserMemories.list_metadata_for_link(link_kind, link_name)
    ]

def metadata_link_index():
    """Databases, tags, and views that already have a metadata memory.

    A view link ``database.view`` is filed under that database. ``count`` is
    the number of metadata memories linked to that exact resource. One memory
    linked to several resources is counted under each of them. A database is
    included when a view inside it has memories, even if the database itself
    has none. Tags have no nested views, because a memory does not record
    which views carry a tag.
    """
    ensure_memory_store()
    databases = {}
    tags = {}
    views_by_database = {}

    def slot(store, name):
        key = str(name).casefold()
        row = store.get(key)
        if row is None:
            row = {"name": name, "count": 0}
            store[key] = row
        return row

    for kind, name in UserMemories.list_metadata_links():
        if kind == "database":
            slot(databases, name)["count"] += 1
        elif kind == "tag":
            slot(tags, name)["count"] += 1
        elif kind == "view":
            database, _separator, view_name = str(name).partition(".")
            if not database or not view_name:
                continue
            slot(databases, database)
            slot(views_by_database.setdefault(database.casefold(), {}), name)["count"] += 1

    catalog = []
    for key, database in databases.items():
        views = sorted(
            views_by_database.get(key, {}).values(),
            key=lambda item: item["name"].casefold(),
        )
        catalog.append({"name": database["name"], "count": database["count"], "views": views})
    catalog.sort(key=lambda item: item["name"].casefold())
    return {
        "databases": catalog,
        "tags": sorted(tags.values(), key=lambda item: item["name"].casefold()),
    }

def find_memory(username, name, agent_id=GLOBAL_AGENT_ID, include_shared_general=False):
    """Return the memory with this name that the agent can see.

    A name is unique for a user, so the caller does not pass a type.
    """
    name = _validate_name(name)
    matches = []
    for memory_type in MEMORY_TYPES:
        for record in _load_visible(username, memory_type, agent_id, include_shared_general):
            if record["name"] == name:
                matches.append(record)
    if not matches:
        raise MemoryError(f"No memory named '{name}'.")
    if len(matches) > 1:
        raise MemoryError(f"More than one memory is named '{name}'.")
    return matches[0]

def read_memory(username, memory_type, name, agent_id=GLOBAL_AGENT_ID, include_shared_general=False):
    """Return one memory owned by ``username``, including its markdown.

    Looks in this agent's scope first. With sharing on, a ``user`` or
    ``user-metadata`` memory of the general agent is found too. A
    ``metadata`` memory is found on whichever agent this user saved it.
    """
    memory_type = _validate_type(memory_type)
    name = _validate_name(name)
    records = _load_visible(username, memory_type, agent_id, include_shared_general)
    for record in records:
        if record["name"] == name:
            return record
    raise MemoryError(f"No {memory_type} memory named '{name}'.")

def write_memory(username, memory_type, name, description, body, links=None, allow_create=True, agent_id=GLOBAL_AGENT_ID, include_shared_general=False):
    """Create or replace one memory and refresh its index line.

    ``agent_id`` is the scope a ``user`` or ``user-metadata`` memory is
    written to. When sharing is on and this agent has no row of that name,
    the general agent's row is updated instead of saving a second copy.
    This agent's own row still wins when both exist. A second memory with
    the same name is refused, whether the other row has a different type or
    belongs to another agent. A ``metadata`` memory is one fact for this
    user: a write from any agent updates the copy that already exists,
    whichever agent saved it, and drops any other copy of that name.
    ``links`` replaces the whole list. A ``user`` memory takes no links; a
    ``user-metadata`` or ``metadata`` memory needs at least one.
    ``modified`` is always written by the store. A user-memory write that
    crosses the index limit still succeeds; the returned message says so.
    ``allow_create`` is False for the sample chatbot UI, which can edit a
    memory the agent already saved but cannot create one. The agent tools
    leave it True.
    """
    username = _validate_username(username)
    memory_type = _validate_type(memory_type)
    scope_agent = _agent_id(agent_id)
    name = _validate_name(name)
    description = _validate_description(description)
    body = _validate_body(body)
    links = _validate_links(memory_type, links)
    record = {
        "name": name,
        "description": description,
        "type": memory_type,
        "owner": username,
        "agent_id": scope_agent,
        "modified": _now(),
        "links": links,
        "body": body,
        "filename": f"{name}.md",
    }
    ensure_memory_store()
    records = []
    with _user_lock(username):
        target_agent = scope_agent
        extras = []
        if memory_type == "metadata":
            copies = _metadata_named(username, name)
            chosen = _preferred_metadata(copies, scope_agent)
            if chosen is None:
                created = True
            else:
                created = False
                target_agent = chosen.get("agent_id") or scope_agent
                extras = [
                    copy for copy in copies
                    if (copy.get("agent_id") or GLOBAL_AGENT_ID) != target_agent
                ]
        else:
            existing = {
                item["name"]: item
                for item in _load_entries(username, memory_type, scope_agent)
            }
            if name in existing:
                created = False
            else:
                shared = _shared_general_memory(
                    username, memory_type, name, scope_agent, include_shared_general,
                )
                if shared is None:
                    created = True
                else:
                    created = False
                    target_agent = shared.get("agent_id") or GLOBAL_AGENT_ID
        conflict = _name_conflict(username, name, memory_type, target_agent)
        if conflict:
            raise MemoryError(_name_taken_message(conflict, name))
        if created and not allow_create:
            raise MemoryError("Memories can only be created by the agent.")
        record["agent_id"] = target_agent
        record["content"] = _render_file(record)
        stored_body = record["body"]
        if created:
            inserted = UserMemories.insert(
                username,
                target_agent,
                memory_type,
                name,
                description,
                stored_body,
                links,
                username,
                record["modified"],
                UserMemories.next_position(username, target_agent, memory_type),
            )
            if not inserted:
                conflict = _name_conflict(username, name, memory_type, target_agent)
                if conflict:
                    raise MemoryError(_name_taken_message(conflict, name))
                updated = UserMemories.update(
                    username,
                    target_agent,
                    memory_type,
                    name,
                    description,
                    stored_body,
                    links,
                    username,
                    record["modified"],
                )
                if not updated:
                    raise MemoryError(f"No {memory_type} memory named '{name}'.")
        else:
            updated = UserMemories.update(
                username,
                target_agent,
                memory_type,
                name,
                description,
                stored_body,
                links,
                username,
                record["modified"],
            )
            if not updated:
                raise MemoryError(f"No {memory_type} memory named '{name}'.")
        for extra in extras:
            UserMemories.delete(
                username,
                extra.get("agent_id") or GLOBAL_AGENT_ID,
                memory_type,
                name,
            )
        if memory_type == "user":
            records = _load_entries(username, memory_type, scope_agent)
    verb = "Saved" if created else "Updated"
    message = f"{verb} {memory_type} memory '{name}'."
    if memory_type == "user":
        index_text = _index_text(records)
        notice = index_limit_notice("user", index_text)
        if notice:
            if _status_from_text(index_text)["over_limit"]:
                message = f"{message} The write succeeded. {notice}"
            else:
                message = f"{message} {notice}"
    logging.info(f"Memory {verb.lower()} for '{username}' on agent '{target_agent}': {memory_type}/{name}")
    return {
        "record": _public_record(record),
        "created": created,
        "message": message,
        "index": user_index_status(username, scope_agent, include_shared_general),
    }

def delete_memory(username, memory_type, name, agent_id=GLOBAL_AGENT_ID, include_shared_general=False):
    """Delete one memory this user owns and its index line.

    ``metadata`` is per user, so every copy of that name is removed, including
    one saved by another agent. ``user`` and ``user-metadata`` remove the row
    this agent can see. Its own row wins when both exist. With sharing on, a
    general-agent row is removed when this agent has no row of its own.
    """
    username = _validate_username(username)
    memory_type = _validate_type(memory_type)
    scope_agent = _agent_id(agent_id)
    name = _validate_name(name)
    ensure_memory_store()
    with _user_lock(username):
        if memory_type == "metadata":
            copies = _metadata_named(username, name)
            if not copies:
                raise MemoryError(f"No {memory_type} memory named '{name}'.")
            removed = False
            for copy in copies:
                if UserMemories.delete(
                    username,
                    copy.get("agent_id") or scope_agent,
                    memory_type,
                    name,
                ):
                    removed = True
            if not removed:
                raise MemoryError(f"No {memory_type} memory named '{name}'.")
        else:
            visible = _load_visible(username, memory_type, scope_agent, include_shared_general)
            match = next((record for record in visible if record["name"] == name), None)
            target = (match.get("agent_id") if match else None) or scope_agent
            if match is None or not UserMemories.delete(username, target, memory_type, name):
                raise MemoryError(f"No {memory_type} memory named '{name}'.")
    message = f"Deleted {memory_type} memory '{name}'."
    notice = ""
    if memory_type == "user":
        notice = index_limit_notice("user", _index_text(_load_visible(username, "user", scope_agent, include_shared_general)))
        if notice:
            message = f"{message} {notice}"
    logging.info(f"Memory deleted for '{username}' on agent '{scope_agent}': {memory_type}/{name}")
    return {"message": message, "index": user_index_status(username, scope_agent, include_shared_general)}

def user_index_status(username, agent_id=GLOBAL_AGENT_ID, include_shared_general=False):
    """Line count for the visible user-memory index, plus limit flags."""
    try:
        text = _index_text(_load_visible(username, "user", agent_id, include_shared_general))
    except MemoryError:
        text = ""
    return _status_from_text(text)

def index_limit_notice(memory_type, index_text):
    """Warning text when a user index is near or over the 200-memory limit."""
    if memory_type != "user":
        return ""
    status = _status_from_text(index_text)
    if status["over_limit"]:
        dropped = status["dropped_lines"]
        notice = (
            f"The user memory index is over its load limit "
            f"({status['lines']} lines; "
            f"only the first {MAX_INDEX_LINES} lines are loaded). "
            "The overflow will be dropped on the next load. "
            "Rewrite the index by merging or dropping stale memories."
        )
        if dropped:
            preview = dropped[:30]
            extra = len(dropped) - len(preview)
            shown = "\n".join(preview)
            notice = f"{notice}\nThese index lines will be dropped on the next load:\n{shown}"
            if extra:
                notice = f"{notice}\n... and {extra} more."
        return notice
    if status["near_limit"]:
        return (
            f"The user memory index is near its load limit "
            f"({status['lines']} lines, the limit is {MAX_INDEX_LINES} lines). "
            "Shorten it by merging or dropping stale memories."
        )
    return ""

def format_index(records):
    """Render index lines for a list of memory records."""
    if not records:
        return ""
    return "\n".join(_index_line(record) for record in records)

def _public_record(record):
    copied = dict(record)
    copied.pop("path", None)
    return copied

def _status_from_text(index_text):
    lines = index_text.splitlines()
    kept, truncated = _truncate_index(index_text)
    over = truncated
    near = (not over) and len(lines) >= NEAR_INDEX_LINES
    return {
        "lines": len(lines),
        "near_limit": near,
        "over_limit": over,
        "dropped_lines": lines[len(kept):],
    }

def _truncate_index(index_text):
    """Keep the leading lines that fit in the 200-line cap."""
    if not index_text:
        return [], False
    all_lines = index_text.splitlines()
    kept = all_lines[:MAX_INDEX_LINES]
    return kept, len(kept) < len(all_lines)

def _resources_from_metadata_response(response):
    views = set()
    databases = set()
    tags = set()
    for entry in response.get("related_tables") or []:
        if not isinstance(entry, dict):
            continue
        view_json = entry.get("view_json") if isinstance(entry.get("view_json"), dict) else {}
        database = _clean_name(view_json.get("databaseName"))
        view_name = _clean_name(view_json.get("viewName"))
        table_name = _clean_name(view_json.get("tableName") or entry.get("view_name"))
        if database and view_name:
            views.add(_fold(f"{database}.{view_name}"))
        if table_name:
            views.add(_fold(table_name))
            if not database and "." in table_name:
                database = table_name.split(".", 1)[0]
        if database:
            databases.add(_fold(database))
        for tag_name in _tag_names(view_json):
            tags.add(_fold(tag_name))
    return views, databases, tags

def _tag_names(view_json):
    names = []
    for key in ("tagDetails", "tags"):
        for tag in view_json.get(key) or []:
            if isinstance(tag, dict) and tag.get("name"):
                names.append(str(tag["name"]).strip())
    for column in view_json.get("schema") or []:
        if not isinstance(column, dict):
            continue
        for tag in column.get("tags") or []:
            if isinstance(tag, dict) and tag.get("name"):
                names.append(str(tag["name"]).strip())
    return names

def _link_matches_resources(link, views, databases, tags):
    if not link:
        return False
    name = _fold(link.get("name"))
    kind = link.get("kind")
    if kind == "view":
        return name in views
    if kind == "database":
        return name in databases
    if kind == "tag":
        return name in tags
    return False

def _links_match_resources(links, views, databases, tags):
    return any(
        _link_matches_resources(link, views, databases, tags)
        for link in links or []
    )

def _matches_filter(record, link_kind, link_name, query):
    links = list(record.get("links") or [])
    if link_kind == "none":
        if links:
            return False
    elif link_kind:
        links = [link for link in links if link.get("kind") == link_kind]
        if not links:
            return False
    if link_name and not any(_same_name(link.get("name"), link_name) for link in links):
        return False
    if query:
        haystack = " ".join([
            record.get("name") or "",
            record.get("description") or "",
            record.get("body") or "",
            " ".join(link.get("name") or "" for link in (record.get("links") or [])),
        ])
        if query.casefold() not in haystack.casefold():
            return False
    return True

def _load_entries(username, memory_type, agent_id=GLOBAL_AGENT_ID):
    username = _validate_username(username)
    memory_type = _validate_type(memory_type)
    agent_id = _agent_id(agent_id)
    ensure_memory_store()
    return [
        _record_from_stored(row)
        for row in UserMemories.list_for_user(username, agent_id, memory_type)
    ]

def _record_from_stored(row):
    """Turn a database row into the record the rest of the engine expects."""
    links = []
    for link in row.get("links") or []:
        if link.get("kind") and link.get("name"):
            links.append({"kind": link["kind"], "name": link["name"]})
    record = {
        "name": row["name"],
        "description": row["description"],
        "type": row["memory_type"],
        "owner": row.get("owner") or row["user_id"],
        "agent_id": row.get("agent_id") or GLOBAL_AGENT_ID,
        "modified": row.get("modified") or "",
        "links": links,
        "body": row.get("body") or "",
        "filename": f"{row['name']}.md",
    }
    record["content"] = _render_file(record)
    return record

def _render_file(record):
    meta = {
        "name": _q(record["name"]),
        "description": _q(record["description"]),
        "type": _q(record["type"]),
        "owner": _q(record["owner"]),
        "agent": _q(record.get("agent_id") or GLOBAL_AGENT_ID),
        "modified": _q(record["modified"]),
    }
    if record.get("links"):
        meta["links"] = [
            {"kind": _q(link["kind"]), "name": _q(link["name"])}
            for link in record["links"]
        ]
    front = yaml.dump(meta, Dumper=_QuotedDumper, sort_keys=False, allow_unicode=True).strip()
    body = record["body"].strip()
    return f"---\n{front}\n---\n\n{body}\n"

def _index_line(record):
    line = f"- [{record['description']}]({record['name']}.md)"
    for link in record.get("links") or []:
        line += f" -{_LINK_SUFFIX[link['kind']]}: {link['name']}"
    return line

def _index_text(records):
    if not records:
        return ""
    return "\n".join(_index_line(record) for record in records) + "\n"

def _user_lock(username):
    with _locks_guard:
        lock = _user_locks.get(username)
        if lock is None:
            lock = threading.RLock()
            _user_locks[username] = lock
        return lock

def _validate_username(username):
    if not isinstance(username, str):
        raise MemoryError("A username is required.")
    username = username.strip()
    if (
        not username
        or username in (".", "..")
        or len(username) > 255
        or "/" in username
        or "\\" in username
        or "\x00" in username
    ):
        raise MemoryError("Invalid username.")
    return username

def _validate_type(memory_type):
    if memory_type not in MEMORY_TYPES:
        raise MemoryError("Memory type must be 'user', 'user-metadata', or 'metadata'.")
    return memory_type

def _validate_name(name):
    if not isinstance(name, str) or not _is_valid_name(name.strip() if isinstance(name, str) else name):
        raise MemoryError(
            "Invalid memory name. Use at most 64 characters: lowercase letters, "
            "numbers, and hyphens, and do not start or end with a hyphen."
        )
    return name.strip()

def _is_valid_name(name):
    return bool(name) and len(name) <= MAX_NAME_LENGTH and _NAME_PATTERN.match(name)

def _validate_description(description):
    if not isinstance(description, str):
        raise MemoryError("A description is required.")
    description = " ".join(description.split())
    if not description:
        raise MemoryError("A description is required.")
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise MemoryError(f"Description must be at most {MAX_DESCRIPTION_LENGTH} characters.")
    if any(character in description for character in "[]<>"):
        raise MemoryError("Description cannot contain '[', ']', '<', or '>'.")
    return description

def _validate_body(body):
    if not isinstance(body, str) or not body.strip():
        raise MemoryError("A memory note is required.")
    cleaned = body.strip()
    if len(cleaned) > MAX_BODY_LENGTH:
        raise MemoryError(f"A memory note must be at most {MAX_BODY_LENGTH} characters.")
    return cleaned + "\n"

def _validate_links(memory_type, links):
    """Return the stored link list.

    A ``user`` memory takes no links: a personal fact tied to specific
    metadata belongs in ``user-metadata`` instead. A ``user-metadata`` or
    ``metadata`` memory needs at least one link.
    """
    cleaned = []
    seen = set()
    for item in _coerce_links(links):
        if isinstance(item, str):
            kind_text, separator, name_text = item.partition(":")
            if not separator:
                raise MemoryError(
                    "A link must look like kind:name, for example view:sales.orders, "
                    "database:sales, or tag:revenue."
                )
        elif isinstance(item, dict):
            kind_text = item.get("kind")
            name_text = item.get("name")
        else:
            raise MemoryError("Each link must be a view, a database, or a tag.")
        if _blank_to_none(kind_text) is None or _blank_to_none(name_text) is None:
            raise MemoryError("A memory link needs both a kind and a name.")
        kind = _validate_link_kind(kind_text)
        name = _validate_link_name(kind, name_text)
        marker = (kind, name.casefold())
        if marker in seen:
            continue
        seen.add(marker)
        cleaned.append({"kind": kind, "name": name})
    if len(cleaned) > MAX_LINKS:
        raise MemoryError(f"A memory can have at most {MAX_LINKS} links.")
    if memory_type == "user" and cleaned:
        raise MemoryError(
            "A user memory cannot be linked to a view, database, or tag. "
            "Use type 'user-metadata' for a personal preference about specific metadata."
        )
    if memory_type in LINKED_MEMORY_TYPES and not cleaned:
        raise MemoryError(f"A {memory_type} memory must be linked to at least one view, database, or tag.")
    return cleaned

def _coerce_links(links):
    """Accept a list of links, or text with one ``kind:name`` entry per line."""
    if links is None:
        return []
    if isinstance(links, str):
        text = links.strip()
        if not text:
            return []
        if text[0] in "[{":
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                return [parsed]
            if isinstance(parsed, list):
                return parsed
        rows = []
        for line in text.replace(";", "\n").splitlines():
            line = line.strip().strip(",")
            if line:
                rows.append(line)
        return rows
    if isinstance(links, dict):
        return [links]
    if isinstance(links, (list, tuple)):
        return list(links)
    raise MemoryError("Links must be a list of view, database, or tag links.")

def _validate_link_kind(link_kind):
    if not isinstance(link_kind, str) or link_kind.strip() not in LINK_KINDS:
        raise MemoryError("Link kind must be 'view', 'database', or 'tag'.")
    return link_kind.strip()

def _validate_link_name(link_kind, link_name):
    if not isinstance(link_name, str):
        raise MemoryError("A link name is required.")
    cleaned = " ".join(link_name.replace('"', "").split())
    if not cleaned:
        raise MemoryError("A link name is required.")
    if len(cleaned) > MAX_LINK_NAME_LENGTH:
        raise MemoryError(f"A link name must be at most {MAX_LINK_NAME_LENGTH} characters.")
    if any(character in cleaned for character in "[]<>"):
        raise MemoryError("A link name cannot contain '[', ']', '<', or '>'.")
    if link_kind == "view":
        if " " in cleaned or cleaned.count(".") != 1 or cleaned.startswith(".") or cleaned.endswith("."):
            raise MemoryError("A view link must be database.view_name.")
    return cleaned

def _blank_to_none(value):
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value

def _clean_name(value):
    if value is None:
        return ""
    return str(value).strip().replace('"', "")

def _fold(value):
    return str(value or "").strip().casefold()

def _same_name(left, right):
    return _fold(left) == _fold(right)

def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
