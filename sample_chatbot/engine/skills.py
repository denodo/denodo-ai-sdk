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
Skills manager for the sample chatbot.

A "skill" is a piece of reusable, on-demand guidance for the agent (for
example, how and when to use the DeepQuery tool). Skills come in two scopes:

- **System skills** live on disk under the AI SDK ``skills/`` directory
  (inside ``AI_SDK_DATA_DIR``), one folder per skill with a ``SKILL.md`` and
  optionally extra reference documents under a ``references/`` subfolder.
  They are visible to every user.
- **Personal skills** are created/uploaded by an individual user and stored
  in the same database as the conversation history (``user_skills`` table).
  They are only visible to their owner.

Layout of a system skill:

    skills/
      deepquery/
        SKILL.md
        references/
          interpret_results.md

Users can activate/deactivate any skill for themselves; deactivated skills
are excluded from the agent's system prompt. All file access is sandboxed to
the skills directory and skill/reference names are strictly validated to
prevent path traversal.
"""

import os
import re
import logging

from utils.database_utils import UserSkills

# Skill and reference names: max 64 chars, lowercase letters/numbers/hyphens,
# must not start or end with a hyphen. Keeps tools from escaping the skills dir.
MAX_SKILL_NAME_LENGTH = 64
MAX_SKILL_DESCRIPTION_LENGTH = 1024
_NAME_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_NAME_RULES = (
    "at most 64 characters, use lowercase letters, numbers, and hyphens only, "
    "and must not start or end with a hyphen"
)

SKILL_FILE_NAME = "SKILL.md"
REFERENCES_DIR_NAME = "references"

class SkillError(Exception):
    """Raised when a skill operation fails (not found, invalid name, etc.)."""

class PersonalSkillNotFoundError(SkillError):
    """The user has no personal skill with that name."""

def get_skills_dir():
    """Return the absolute path to the AI SDK skills directory.

    Lives under the centralized data directory (``AI_SDK_DATA_DIR``), like
    reports and conversation history. With the default data dir (``.``) this
    resolves to ``<repo_root>/skills``, preserving the original layout.
    """
    data_dir = os.getenv("AI_SDK_DATA_DIR", ".")
    return os.path.abspath(os.path.join(data_dir, "skills"))

def _is_valid_name(name):
    return bool(name and _NAME_PATTERN.match(name))

def _name_error_message(name, kind="skill"):
    return f"Invalid {kind} name '{name}'. Names must be {_NAME_RULES}."

def _validate_name(name, kind="skill"):
    """Validate a skill or reference name, raising SkillError if unsafe."""
    if not _is_valid_name(name):
        raise SkillError(_name_error_message(name, kind))
    return name

def _sandbox_skill_path(skill_name, *parts):
    """Resolve a path under the skills directory, rejecting path traversal."""
    skills_dir = get_skills_dir()
    candidate = os.path.abspath(os.path.join(skills_dir, skill_name, *parts))
    if os.path.commonpath([skills_dir, candidate]) != skills_dir:
        raise SkillError(f"Invalid skill name '{skill_name}'.")
    return candidate

def _skill_dir(name):
    return os.path.join(get_skills_dir(), _validate_name(name, "skill"))

def _skill_file(name):
    return os.path.join(_skill_dir(name), SKILL_FILE_NAME)

def _reference_file(skill_name, reference_name):
    return os.path.join(
        _skill_dir(skill_name),
        REFERENCES_DIR_NAME,
        f"{_validate_name(reference_name, 'reference')}.md",
    )

def _parse_description(content, skill_name):
    """Validate SKILL.md frontmatter and return its description.

    Requires a YAML frontmatter block with:
    - ``name``: must match ``skill_name`` and the skill name rules
    - ``description``: non-empty, at most 1024 characters
    """
    example = (
        f"Skill '{skill_name}' has an invalid SKILL.md: the file must start with a "
        f"YAML frontmatter block declaring name and description, e.g.:\n"
        f"---\n"
        f"name: {skill_name}\n"
        f"description: One-line summary of what this skill does and when to use it.\n"
        f"---"
    )
    text = content.lstrip()
    if not text.startswith("---"):
        raise SkillError(example)
    end = text.find("\n---", 3)
    if end == -1:
        raise SkillError(example)

    frontmatter_name = None
    description = None
    for line in text[3:end].splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("name:"):
            frontmatter_name = stripped.split(":", 1)[1].strip().strip('"').strip("'")
        elif stripped.lower().startswith("description:"):
            description = stripped.split(":", 1)[1].strip().strip('"').strip("'")

    if not frontmatter_name:
        raise SkillError(
            f"Skill '{skill_name}' has an invalid SKILL.md: frontmatter must declare a non-empty name."
        )
    if not _is_valid_name(frontmatter_name):
        raise SkillError(_name_error_message(frontmatter_name, "skill"))
    if frontmatter_name != skill_name:
        raise SkillError(
            f"Skill '{skill_name}' has an invalid SKILL.md: frontmatter name "
            f"'{frontmatter_name}' does not match the skill name '{skill_name}'."
        )
    if not description:
        raise SkillError(
            f"Skill '{skill_name}' has an invalid SKILL.md: frontmatter must declare a non-empty description."
        )
    if len(description) > MAX_SKILL_DESCRIPTION_LENGTH:
        raise SkillError(
            f"Skill '{skill_name}' description exceeds {MAX_SKILL_DESCRIPTION_LENGTH} characters."
        )
    return description

def list_reference_names(skill_name):
    """Return the sorted list of valid reference names available for a skill."""
    references_dir = os.path.join(_skill_dir(skill_name), REFERENCES_DIR_NAME)
    if not os.path.isdir(references_dir):
        return []
    names = []
    for entry in os.listdir(references_dir):
        if entry.endswith(".md") and os.path.isfile(os.path.join(references_dir, entry)):
            name = entry[:-3]
            if not _is_valid_name(name):
                logging.warning(
                    f"Skipping reference with invalid name in skill '{skill_name}': '{name}'"
                )
                continue
            names.append(name)
    return sorted(names)

def discover_skills():
    """Discover all skills on disk.

    Returns a dict::

        {skill_name: {"description", "references", "valid", "error"}}

    Invalid skills (bad folder name or frontmatter) are included with
    ``valid=False`` and an ``error`` message so the Skills Manager can show
    them, but they must not be loaded into the agent context.
    """
    skills_dir = get_skills_dir()
    discovered = {}
    if not os.path.isdir(skills_dir):
        return discovered

    for entry in sorted(os.listdir(skills_dir)):
        skill_path = os.path.join(skills_dir, entry)
        skill_file = os.path.join(skill_path, SKILL_FILE_NAME)
        if not os.path.isdir(skill_path) or not os.path.isfile(skill_file):
            continue

        description = ""
        references = []
        error = None
        if not _is_valid_name(entry):
            error = _name_error_message(entry, "skill")
            logging.warning(f"System skill has invalid name on disk: '{entry}'")
        else:
            try:
                with open(skill_file, "r", encoding="utf-8") as f:
                    content = f.read()
                description = _parse_description(content, entry)
                references = list_reference_names(entry)
            except Exception as e:
                logging.warning(f"Could not load skill '{entry}': {e}")
                error = str(e)

        discovered[entry] = {
            "description": description,
            "references": references,
            "valid": error is None,
            "error": error,
        }
    return discovered

# =============================================================================
# Per-user skill views (system + personal, with activation state)
# =============================================================================

def discover_skills_for_user(user_id, agent_id, allowed_system_skills=None, disabled_skills=None):
    """Return the merged skill view for a user on a given agent.

    Combines the on-disk system skills with the user's personal skills from
    the database. Each entry carries its scope, the activation state for this
    agent, whether that state is managed by the agent, and validity:

        {skill_name: {
            "description", "references", "scope", "active", "agent_managed",
            "valid", "error",
        }}

    When ``allowed_system_skills`` is None (the agent's YAML does not declare
    ``skills``), every system skill is user-toggleable and active by default
    (activation is per (user, agent), configured in the agent's settings).
    When the agent declares ``skills``, system skills are agent-managed and
    user preferences are ignored: declared skills are always active, the rest
    always inactive. Personal skills are always user-toggleable.

    Invalid skills (``valid=False``) are still listed for the Skills Manager
    but must not be injected into the agent context (see active_skills_for_user).

    Name collisions: if a user has a personal skill named like a system skill,
    the personal one wins for that user (it replaces the system entry in this
    view, and read_skill_for_user serves the personal content). This can only
    arise when a system skill is added AFTER a user already had a personal
    skill with that name — create_personal_skill rejects names that already
    exist as system skills.

    ``disabled_skills`` names skills force-deactivated by the agent's feature
    flags (e.g. 'deepquery' when DeepQuery is disabled). They are still listed
    for the Skills Manager but always inactive and never user-toggleable,
    regardless of scope or preferences.
    """
    prefs = UserSkills.get_prefs(user_id, agent_id)
    agent_managed = allowed_system_skills is not None
    merged = {}

    for name, meta in discover_skills().items():
        valid = meta.get("valid", True)
        merged[name] = {
            "description": meta.get("description", ""),
            "references": meta.get("references", []),
            "scope": "system",
            "active": (name in allowed_system_skills) if agent_managed else prefs.get(name, True),
            "agent_managed": agent_managed,
            "valid": valid,
            "error": meta.get("error"),
        }

    for personal in UserSkills.list_personal(user_id):
        name = personal["skill_name"]
        description = ""
        error = None
        if not _is_valid_name(name):
            error = _name_error_message(name, "skill")
        else:
            try:
                description = _parse_description(personal["content"] or "", name)
            except SkillError as e:
                error = str(e)
        merged[name] = {
            "description": description,
            "references": [],
            "scope": "personal",
            "active": prefs.get(name, True),
            "agent_managed": False,
            "valid": error is None,
            "error": error,
        }

    # Feature-disabled skills are forced inactive on the final merged entry
    # (whatever its scope) and locked, so no preference can re-enable them.
    for name in (disabled_skills or ()):
        if name in merged:
            merged[name]["active"] = False
            merged[name]["agent_managed"] = True
            merged[name]["feature_disabled"] = True

    return dict(sorted(merged.items()))

def active_skills_for_user(user_id, agent_id, allowed_system_skills=None, disabled_skills=None):
    """Like discover_skills_for_user but only valid skills the user has active."""
    return {
        name: meta
        for name, meta in discover_skills_for_user(
            user_id, agent_id, allowed_system_skills, disabled_skills
        ).items()
        if meta["active"] and meta.get("valid", True)
    }

def read_skill_for_user(user_id, skill_name):
    """Read a skill's content for a user: their personal skill first, else system."""
    personal = UserSkills.get_personal(user_id, skill_name)
    if personal is not None:
        return personal["content"]
    return read_skill(skill_name)

def create_personal_skill(user_id, skill_name, content):
    """Create a personal skill for a user, stored in the database."""
    _validate_name(skill_name, "skill")
    if not content or not content.strip():
        raise SkillError("Skill content cannot be empty.")
    _parse_description(content, skill_name)
    if skill_name in discover_skills():
        raise SkillError(
            f"'{skill_name}' is already a system skill. Choose a different name."
        )
    if not UserSkills.create_personal(user_id, skill_name, content):
        raise SkillError(
            f"You already have a personal skill named '{skill_name}'. "
            f"Use edit_skill to modify it."
        )

def update_personal_skill(user_id, skill_name, content):
    """Replace the full content of a user's personal skill."""
    if not _is_valid_name(skill_name):
        raise SkillError(
            f"Personal skill '{skill_name}' has an invalid name and cannot be updated. "
            f"Delete it and create a new skill with a valid name."
        )
    if not content or not content.strip():
        raise SkillError("Skill content cannot be empty.")
    _parse_description(content, skill_name)
    if not UserSkills.update_personal(user_id, skill_name, content):
        raise PersonalSkillNotFoundError(f"Personal skill '{skill_name}' was not found.")

def edit_personal_skill(user_id, skill_name, text_to_search, text_to_replace):
    """Replace ALL occurrences of text_to_search in a user's personal skill.

    Returns the number of occurrences replaced.
    """
    if not _is_valid_name(skill_name):
        raise SkillError(
            f"Personal skill '{skill_name}' has an invalid name and cannot be edited. "
            f"Delete it and create a new skill with a valid name."
        )
    personal = UserSkills.get_personal(user_id, skill_name)
    if personal is None:
        raise PersonalSkillNotFoundError(f"Personal skill '{skill_name}' was not found.")
    content = personal["content"] or ""
    if text_to_search not in content:
        raise SkillError(
            "The text to search was not found, no changes were made. "
            "Make sure it matches exactly (including whitespace)."
        )
    occurrences = content.count(text_to_search)
    new_content = content.replace(text_to_search, text_to_replace)
    _parse_description(new_content, skill_name)
    UserSkills.update_personal(user_id, skill_name, new_content)
    return occurrences

def delete_personal_skill(user_id, skill_name):
    """Delete a user's personal skill (including invalid ones, so they can be cleaned up)."""
    if not skill_name:
        raise SkillError("Skill name cannot be empty.")
    if not UserSkills.delete_personal(user_id, skill_name):
        raise PersonalSkillNotFoundError(f"Personal skill '{skill_name}' was not found.")

def set_skill_active(user_id, agent_id, skill_name, active):
    """Activate/deactivate a skill for a user on a given agent."""
    personal = UserSkills.get_personal(user_id, skill_name)
    system = discover_skills().get(skill_name)
    if personal is None and system is None:
        raise SkillError(f"Skill '{skill_name}' was not found.")
    if personal is not None:
        if not _is_valid_name(skill_name):
            raise SkillError(
                f"Skill '{skill_name}' is invalid and cannot be activated. "
                f"Fix or delete it in the Skills Manager."
            )
        try:
            _parse_description(personal.get("content") or "", skill_name)
        except SkillError as e:
            raise SkillError(
                f"Skill '{skill_name}' is invalid and cannot be activated: {e}"
            ) from e
    elif not system.get("valid", True):
        raise SkillError(
            f"Skill '{skill_name}' is invalid and cannot be activated. "
            f"{system.get('error') or 'Fix it in the Skills Manager.'}"
        )
    UserSkills.set_active(user_id, agent_id, skill_name, active)

# =============================================================================
# Read operations (available to all users)
# =============================================================================

def read_skill(skill_name):
    """Return the full content of a skill's SKILL.md (path-traversal safe).

    Does not require a valid skill name so the Skills Manager can still open
    invalid on-disk skills for inspection.
    """
    path = _sandbox_skill_path(skill_name, SKILL_FILE_NAME)
    if not os.path.isfile(path):
        raise SkillError(f"Skill '{skill_name}' was not found.")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def read_skill_reference(skill_name, reference_name):
    """Return the full content of a skill reference document."""
    if not os.path.isdir(_skill_dir(skill_name)):
        raise SkillError(f"Skill '{skill_name}' was not found.")
    path = _reference_file(skill_name, reference_name)
    if not os.path.isfile(path):
        raise SkillError(
            f"Reference '{reference_name}' was not found in skill '{skill_name}'."
        )
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

# =============================================================================
# Edit operations (replace ALL occurrences; authorized users only)
# =============================================================================

def _replace_all(path, text_to_search, text_to_replace, not_found_msg, validate=None):
    if not os.path.isfile(path):
        raise SkillError(not_found_msg)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if text_to_search not in content:
        raise SkillError(
            f"The text to search was not found, no changes were made. "
            f"Make sure it matches exactly (including whitespace)."
        )
    occurrences = content.count(text_to_search)
    new_content = content.replace(text_to_search, text_to_replace)
    if validate is not None:
        validate(new_content)
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)
    return occurrences

def edit_skill(skill_name, text_to_search, text_to_replace):
    """Replace ALL occurrences of text_to_search with text_to_replace in SKILL.md.

    Returns the number of occurrences replaced.
    """
    path = _skill_file(skill_name)
    return _replace_all(
        path,
        text_to_search,
        text_to_replace,
        f"Skill '{skill_name}' was not found.",
        validate=lambda new_content: _parse_description(new_content, skill_name),
    )

def edit_skill_reference(skill_name, reference_name, text_to_search, text_to_replace):
    """Replace ALL occurrences of text_to_search with text_to_replace in a reference.

    Returns the number of occurrences replaced.
    """
    if not os.path.isdir(_skill_dir(skill_name)):
        raise SkillError(f"Skill '{skill_name}' was not found.")
    path = _reference_file(skill_name, reference_name)
    return _replace_all(
        path,
        text_to_search,
        text_to_replace,
        f"Reference '{reference_name}' was not found in skill '{skill_name}'.",
    )

# =============================================================================
# Create operations (authorized users only)
# =============================================================================

def create_skill_reference(skill_name, reference_name, content):
    """Create a new reference document inside an existing skill.

    Raises SkillError if the skill does not exist or the reference already exists.
    """
    if not os.path.isdir(_skill_dir(skill_name)):
        raise SkillError(
            f"Skill '{skill_name}' was not found. Create the skill first with create_skill."
        )
    path = _reference_file(skill_name, reference_name)
    if os.path.exists(path):
        raise SkillError(
            f"Reference '{reference_name}' already exists in skill '{skill_name}'. "
            f"Use edit_skill_reference to modify it."
        )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path

# =============================================================================
# Prompt / startup helpers
# =============================================================================

def build_skills_prompt_section(skills, can_manage_skills=False):
    """Build the <skills> section injected into the chatbot system prompt.

    Args:
        skills: dict as returned by active_skills_for_user() (or
            discover_skills(), whose entries default to the system scope).
        can_manage_skills: whether the current user may edit SYSTEM skills.
    """
    if not skills:
        listing = "There are no skills available."
    else:
        lines = []
        for name, meta in skills.items():
            description = meta.get("description") or "(no description)"
            refs = meta.get("references") or []
            scope = meta.get("scope", "system")
            line = f"- {name} [{scope.upper()}]: {description}"
            if refs:
                line += f" (references: {', '.join(refs)})"
            lines.append(line)
        listing = "\n".join(lines)

    manage_tools = (
        "\nManaging skills:\n"
        "- create_skill(skill_name, content): create a new PERSONAL skill for this user, only visible to them.\n"
        "- edit_skill(skill_name, text_to_search, text_to_replace): replace ALL occurrences of a piece of text in one of the user's PERSONAL skills.\n"
    )
    if can_manage_skills:
        manage_tools += (
            "You are also authorized to manage the shared SYSTEM skills, visible to every user:\n"
            "- edit_skill also works on SYSTEM skills.\n"
            "- create_skill_reference(skill_name, reference_name, content): add a reference document to a SYSTEM skill.\n"
            "- edit_skill_reference(skill_name, reference_name, text_to_search, text_to_replace): replace ALL occurrences of a piece of text in a SYSTEM skill reference.\n"
        )
    manage_tools += "Only create or edit a skill when the user explicitly asks you to.\n"

    return f"""<skills>
Skills are pieces of reusable, on-demand guidance that teach you how to handle specific tasks.
There are two categories of skills: PERSONAL and SYSTEM. System skills are shared with every user, personal skills belong to this user only.
You must read the relevant skill BEFORE acting on a task it covers, so you follow the correct process.
System skills (not personal) may have additional reference documents.

Available skills:
{listing}

How to use skills:
- read_skill(skill_name): read a skill's full instructions. Example: read_skill("skill_name"). Only the skills listed above can be read.
- read_skill_reference(skill_name, reference_name): read one of a system skill's reference documents. Example: read_skill_reference("skill_name", "reference_name").

Guidelines:
- When a user's request matches a skill's description, read that skill first and follow its instructions for the rest of the task.
- Do not guess a skill's content; always read it. You only see the names and descriptions above, not the full instructions.
{manage_tools}</skills>"""

def log_skills(logger):
    """Log the discovered system skills at startup, mirroring the agents config log."""
    skills = discover_skills()
    valid = {n: m for n, m in skills.items() if m.get("valid", True)}
    invalid = {n: m for n, m in skills.items() if not m.get("valid", True)}
    count = len(valid)
    logger.info(f"{count} system skill{'' if count == 1 else 's'} loaded from {get_skills_dir()}")
    for name, meta in valid.items():
        refs = meta.get("references") or []
        ref_text = f" ({len(refs)} reference{'' if len(refs) == 1 else 's'})" if refs else ""
        logger.info(f"    - {name}: {meta.get('description', '')}{ref_text}")
    if invalid:
        logger.warning(
            f"{len(invalid)} system skill{'' if len(invalid) == 1 else 's'} "
            f"failed validation and will not be loaded into agent context:"
        )
        for name, meta in invalid.items():
            logger.warning(f"    - {name}: {meta.get('error') or 'invalid'}")
