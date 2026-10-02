import io
import os
import re
import sys
import shutil
import time
from datetime import date
from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.prompt import Confirm
from dotenv import parser as dotenv_parser
from utils.version import AI_SDK_VERSION

console = Console()
PANEL_WIDTH = 60

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------

SDK_ENV_PATH = os.path.join(".", "api", "utils", "sdk_config.env")
SDK_EXAMPLE_PATH = SDK_ENV_PATH + ".example"
CHATBOT_ENV_PATH = os.path.join(".", "sample_chatbot", "chatbot_config.env")
CHATBOT_EXAMPLE_PATH = CHATBOT_ENV_PATH + ".example"

# ---------------------------------------------------------------------------
# Rename rules  (applied in order — first match wins per variable)
# ---------------------------------------------------------------------------

SDK_RENAME_RULES = [
    ("LANGFUSE_HOST", "LANGFUSE_BASE_URL"),
    ("AI_SDK_DATA_CATALOG_URL", "AI_SDK_DATA_MARKETPLACE_URL"),
    ("DATA_CATALOG_URL", "AI_SDK_DATA_MARKETPLACE_URL"),
    ("DATA_CATALOG", "DATA_MARKETPLACE"),
]

CHATBOT_RENAME_RULES = [
    ("LANGFUSE_HOST", "LANGFUSE_BASE_URL"),
    ("CHATBOT_DATA_CATALOG_URL", "CHATBOT_DATA_MARKETPLACE_URL"),
    ("DATA_CATALOG_URL", "CHATBOT_DATA_MARKETPLACE_URL"),
    ("DATA_CATALOG", "DATA_MARKETPLACE"),
]

# ---------------------------------------------------------------------------
# Provider keys and dynamic variable suffixes
# ---------------------------------------------------------------------------

SDK_PROVIDER_KEYS = ["LLM_PROVIDER", "THINKING_LLM_PROVIDER", "EMBEDDINGS_PROVIDER"]
CHATBOT_PROVIDER_KEYS = ["CHATBOT_LLM_PROVIDER", "CHATBOT_EMBEDDINGS_PROVIDER"]

CUSTOM_OPENAI_SUFFIXES = ["_API_KEY", "_BASE_URL", "_PROXY", "_PROXY_VERIFY_SSL"]
CUSTOM_AZURE_SUFFIXES = [
    "_ENDPOINT", "_API_KEY", "_API_VERSION",
    "_PROXY", "_PROXY_VERIFY_SSL", "_EMBEDDINGS_DIMENSIONS",
]

# ---------------------------------------------------------------------------
# Provider list  (pulled from UniformLLM + UniformEmbeddings at runtime)
# ---------------------------------------------------------------------------

def _get_known_providers():
    from utils.uniformLLM import UniformLLM
    from utils.uniformEmbeddings import UniformEmbeddings
    providers = {p.lower() for p in UniformLLM.VALID_PROVIDERS}
    providers.update(p.lower() for p in UniformEmbeddings.VALID_PROVIDERS)
    return sorted(providers)

# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _read_text(filepath):
    """Read an env file. Skips the BOM that Windows editors add."""
    with open(filepath, encoding="utf-8-sig") as f:
        return f.read()

def _statement_from_binding(binding, active, raw_lines):
    """Build a config statement from a python-dotenv binding."""
    text = binding.original.string.rstrip("\r\n")
    head, _, raw_value = text.partition("=")
    return {
        "type": "config",
        "name": binding.key,
        "active": active,
        "value": raw_value.strip(),            # raw text, quotes included
        "clean_value": binding.value or "",    # value after quotes and escapes
        "export": head.lstrip().startswith("export "),
        "raw_lines": raw_lines,
    }

def _uncomment(lines):
    """Remove one leading '#' from each line."""
    out = []
    for line in lines:
        stripped = line.lstrip()
        out.append(stripped[1:] if stripped.startswith("#") else line)
    return out

_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]*$")

def _scan_commented_block(lines):
    """The dotenv parser does not return commented variables, so we need to scan for them manually."""
    as_comments = [{"type": "comment", "raw_lines": [line]} for line in lines]
    body = "\n".join(_uncomment(lines)) + "\n"
    try:
        bindings = list(dotenv_parser.parse_stream(io.StringIO(body)))
    except Exception:
        return as_comments

    statements = []
    cursor = 0
    for binding in bindings:
        span = binding.original.string.count("\n") or 1
        chunk = lines[cursor:cursor + span]
        cursor += span
        if binding.key and not binding.error and _NAME_RE.match(binding.key):
            statements.append(_statement_from_binding(binding, False, chunk))
        else:
            statements.extend({"type": "comment", "raw_lines": [line]} for line in chunk)
    statements.extend({"type": "comment", "raw_lines": [line]} for line in lines[cursor:])
    return statements

def _scan_statements(text):
    """Split an env file into statements.

    Each statement has a "type" of "blank", "comment" or "config", plus the
    "raw_lines" it came from. A config statement also carries name, active,
    value, clean_value and export. A statement the parser could not read is
    marked malformed=True, which usually means a quote was never closed.
    """
    statements = []
    if not text:
        return statements

    lines = text.rstrip("\n").split("\n")
    cursor = 0
    pending = []                      # '#' lines waiting to be checked

    def flush():
        if pending:
            statements.extend(_scan_commented_block(list(pending)))
            pending.clear()

    for binding in dotenv_parser.parse_stream(io.StringIO(text)):
        span = binding.original.string.count("\n") or 1
        chunk = lines[cursor:cursor + span]
        cursor += span

        if binding.key and not binding.error:
            flush()
            statements.append(_statement_from_binding(binding, True, chunk))
            continue

        if binding.error:
            flush()
            # One error is reported per line, so join them into one block.
            if statements and statements[-1].get("malformed"):
                statements[-1]["raw_lines"].extend(chunk)
            else:
                statements.append({
                    "type": "config", "name": None, "active": True, "value": "",
                    "clean_value": "", "export": False, "raw_lines": chunk,
                    "malformed": True,
                })
            continue

        for line in chunk:
            stripped = line.strip()
            if stripped.startswith("#") and not stripped.startswith("##"):
                pending.append(line)
                continue
            flush()
            statements.append({
                "type": "blank" if not stripped else "comment", "raw_lines": [line],
            })

    flush()
    for line in lines[cursor:]:
        statements.append({"type": "comment" if line.strip() else "blank", "raw_lines": [line]})

    return statements

def _scan_file(filepath):
    if not os.path.exists(filepath):
        return []
    return _scan_statements(_read_text(filepath))

def _parse_env_variables(filepath):
    """Parse an env file into {var_name: {"active", "value", "clean_value", "export"}}.

    Returns (variables, duplicates, parse_error).
    When a variable appears more than once, the one kept is the one the SDK
    reads: the last active assignment, or the last commented one if none is
    active. The rest are returned as duplicates. parse_error is True if the
    file is not a valid env file.
    """
    variables = {}
    duplicates = []
    parse_error = False
    occurrences = {}

    for st in _scan_file(filepath):
        if st["type"] != "config":
            continue
        if st.get("malformed"):
            parse_error = True
            continue
        occurrences.setdefault(st["name"], []).append({
            "active": st["active"], "value": st["value"],
            "clean_value": st["clean_value"], "export": st["export"],
        })

    for name, occ in occurrences.items():
        actives = [o for o in occ if o["active"]]
        primary = actives[-1] if actives else occ[-1]
        variables[name] = primary
        duplicates.extend({"var_name": name, **o} for o in occ if o is not primary)

    return variables, duplicates, parse_error

def _parse_example_template(filepath):
    """Parse a .env.example into an ordered list of template lines and a variable dict.

    Returns (template_lines, example_vars).
    Each template line is {"raw": str, "type": "blank"|"comment"|"config",
                           "var_name": str|None, "active": bool,
                           "substitute": bool}.
    If the template lists the same variable more than once, only the first one
    is filled in with the user's value. The others are left as they are.
    """
    template_lines = []
    example_vars = {}

    for st in _scan_file(filepath):
        if st["type"] == "config" and not st.get("malformed"):
            first = st["name"] not in example_vars
            template_lines.append({
                "raw": "\n".join(st["raw_lines"]), "type": "config",
                "var_name": st["name"], "active": st["active"], "substitute": first,
            })
            if first:
                example_vars[st["name"]] = {
                    "active": st["active"], "value": st["value"],
                    "clean_value": st["clean_value"], "export": st["export"],
                }
        else:
            for raw in st["raw_lines"]:
                template_lines.append({
                    "raw": raw, "type": "blank" if not raw.strip() else "comment",
                    "var_name": None, "active": False, "substitute": False,
                })

    return template_lines, example_vars

def _format_assignment(var_name, info):
    """Turn a variable back into env-file text.

    The value is written as it was read. An inactive variable gets a '#' on
    every one of its lines, so a multi-line value is commented as a whole.
    """
    prefix = "export " if info.get("export") else ""
    line = f"{prefix}{var_name}={info['value']}"
    if info.get("active", True):
        return line
    return "\n".join("#" + part for part in line.split("\n"))

# ---------------------------------------------------------------------------
# Rename logic
# ---------------------------------------------------------------------------

def _rename(var_name, rename_rules):
    for old_sub, new_sub in rename_rules:
        if old_sub in var_name:
            return var_name.replace(old_sub, new_sub)
    return var_name

def _apply_renames(variables, rename_rules):
    """Apply ordered rename rules (substring replacement) to variable names.

    Returns (renamed_dict, rename_log, conflicts).
    A variable is renamed only when the new name is not already in the file. If
    it is, the value already set is kept and the old one is returned as a
    conflict, to be written back commented out under the new name.
    """
    renamed = {}
    rename_log = []
    conflicts = []

    for var_name, info in variables.items():
        new_name = _rename(var_name, rename_rules)

        if new_name == var_name:
            renamed[new_name] = info
            continue

        if new_name in variables or new_name in renamed:
            conflicts.append({"old": var_name, "new": new_name, "info": info})
            continue

        rename_log.append((var_name, new_name))
        renamed[new_name] = info

    return renamed, rename_log, conflicts

def _apply_renames_to_duplicates(duplicates, rename_rules):
    """Apply rename rules to duplicate variable names."""
    renamed = []
    for dup in duplicates:
        new_name = dup["var_name"]
        for old_sub, new_sub in rename_rules:
            if old_sub in new_name:
                new_name = new_name.replace(old_sub, new_sub)
                break
        renamed.append({**dup, "var_name": new_name})
    return renamed

# ---------------------------------------------------------------------------
# Extra-variable classification
# ---------------------------------------------------------------------------

def _get_active_custom_providers(env_vars, provider_keys, known_providers):
    providers = set()
    for key in provider_keys:
        if key in env_vars and env_vars[key].get("clean_value", env_vars[key]["value"]):
            pname = env_vars[key].get("clean_value", env_vars[key]["value"]).strip()
            if pname.lower() not in known_providers:
                providers.add(pname.upper())
    return providers

def _detect_orphaned_providers(unknown_vars, known_providers):
    candidates = {}
    all_suffixes = CUSTOM_OPENAI_SUFFIXES + CUSTOM_AZURE_SUFFIXES
    for var in unknown_vars:
        for suffix in all_suffixes:
            if var.endswith(suffix):
                prefix = var[: -len(suffix)]
                if prefix and prefix.lower() not in known_providers:
                    candidates.setdefault(prefix, set()).add(suffix)

    orphans = {}
    for prefix, suffixes in candidates.items():
        if prefix.startswith("AZURE_") and {"_ENDPOINT", "_API_KEY"} & suffixes:
            orphans[prefix] = "azure"
        elif {"_API_KEY"} & suffixes:
            orphans[prefix] = "openai"
    return orphans

def _classify_extra_var(var_name, active_providers, orphaned_providers):
    """Returns (category, detail) or None."""
    vu = var_name.upper()

    for provider in active_providers:
        suffixes = CUSTOM_AZURE_SUFFIXES if provider.startswith("AZURE_") else CUSTOM_OPENAI_SUFFIXES
        for s in suffixes:
            if vu == provider + s:
                return ("custom_provider", f"Provider '{provider}'")

    for provider, ptype in orphaned_providers.items():
        suffixes = CUSTOM_AZURE_SUFFIXES if ptype == "azure" else CUSTOM_OPENAI_SUFFIXES
        for s in suffixes:
            if vu == provider + s:
                return ("orphaned_provider", f"Provider '{provider}'")

    if "_HEADER_" in var_name:
        provider_part = var_name.split("_HEADER_", 1)[0]
        return ("custom_header", f"Header for '{provider_part}'")

    return None

# ---------------------------------------------------------------------------
# Full analysis
# ---------------------------------------------------------------------------

def _analyze(example_path, env_path, rename_rules, provider_keys, known_providers):
    template_lines, example_vars = _parse_example_template(example_path)
    user_vars_raw, duplicates_raw, parse_error = _parse_env_variables(env_path)
    user_vars, rename_log, rename_conflicts = _apply_renames(user_vars_raw, rename_rules)
    duplicates = _apply_renames_to_duplicates(duplicates_raw, rename_rules)

    example_names = set(example_vars)
    user_names = set(user_vars)

    new_vars = sorted(example_names - user_names)
    matching_vars = sorted(example_names & user_names)
    extra_names = sorted(user_names - example_names)

    active_providers = _get_active_custom_providers(user_vars, provider_keys, known_providers)
    orphaned_providers = _detect_orphaned_providers(extra_names, known_providers)
    orphaned_providers = {k: v for k, v in orphaned_providers.items() if k not in active_providers}

    extra_classified = {
        "custom_provider": [],
        "orphaned_provider": [],
        "custom_header": [],
        "deprecated": [],
    }
    for var in extra_names:
        result = _classify_extra_var(var, active_providers, orphaned_providers)
        if result:
            extra_classified[result[0]].append((var, result[1]))
        else:
            extra_classified["deprecated"].append((var, None))

    return {
        "template_lines": template_lines,
        "example_vars": example_vars,
        "user_vars": user_vars,
        "rename_log": rename_log,
        "new_vars": new_vars,
        "matching_vars": matching_vars,
        "extra_classified": extra_classified,
        "duplicates": duplicates,
        "rename_conflicts": rename_conflicts,
        "parse_error": parse_error,
    }

# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _truncate(value, max_len=25):
    if not value:
        return "(empty)"
    flat = " ".join(value.split())          # keep multi-line values on one row
    if not flat:
        return "(empty)"
    return flat[:max_len] + ("…" if len(flat) > max_len else "")

def _display_value(info):
    """The value without its quotes and inline comment."""
    return info.get("clean_value", info.get("value", ""))

def _print_migration_header():
    header = Text.assemble(
        ("Migration Tool\n", "bold white"),
        (f"Upgrading to AI SDK version: {AI_SDK_VERSION}", "bold cyan"),
    )
    header.justify = "center"
    console.print(Panel(header, border_style="cyan", padding=(1, 2), width=PANEL_WIDTH))

    console.print(Panel(
        Text.assemble(
            ("WARNING: ", "bold yellow"),
            ("The migration tool rebuilds your .env files from the latest .env.example "
             "templates while preserving your configuration values to keep up with the new changes. "
             "A backup is always created before any changes are written.\n\n", "yellow"),
            ("PARSING: ", "bold yellow"),
            ("Only lines with no leading # or with a single # are parsed as "
             "variables. Lines starting with ## are treated as comments and "
             "ignored. If a variable appears more than once, the last "
             "occurrence is used as the primary value and earlier duplicates "
             "are shown in the review for you to keep or remove (kept by "
             "default).", "yellow"),
        ),
        border_style="yellow", width=PANEL_WIDTH, padding=(1, 2),
    ))
    console.print()

def _print_summary_line(analysis):
    matching = len(analysis["matching_vars"])
    renames = len(analysis["rename_log"])
    new = len(analysis["new_vars"])
    extra = analysis["extra_classified"]
    custom = len(extra["custom_provider"]) + len(extra["orphaned_provider"]) + len(extra["custom_header"])
    deprecated = len(extra["deprecated"])
    dupes = len(analysis.get("duplicates", []))

    parts = [f"[green]{matching} preserved[/]"]
    if new:
        parts.append(f"[cyan]{new} new[/]")
    if renames:
        parts.append(f"[magenta]{renames} rename{'s' if renames != 1 else ''}[/]")
    if custom:
        parts.append(f"[blue]{custom} custom[/]")
    if deprecated:
        parts.append(f"[red]{deprecated} deprecated/unknown[/]")
    if dupes:
        parts.append(f"[yellow]{dupes} duplicate{'s' if dupes != 1 else ''}[/]")

    console.print("  " + "  |  ".join(parts))
    console.print()

def _section_table(col1_header="Variable", extra_cols=None):
    """Create a standard section table with Variable + Status + Value columns,
    plus any extra leading columns (like # for deprecated).
    """
    table = Table(show_header=True, header_style="bold", show_lines=False, padding=(0, 1))
    if extra_cols:
        for name, width in extra_cols:
            table.add_column(name, style="dim", width=width, justify="right")
    table.add_column(col1_header, no_wrap=True, overflow="ellipsis")
    table.add_column("Status", width=10, no_wrap=True)
    table.add_column("Value", no_wrap=True, overflow="ellipsis")
    return table

def _status_cell(active):
    return "[green]active[/]" if active else "[dim]inactive[/]"

def _render_sections(analysis, kept_indices=None, title=None):
    """Render the full analysis as grouped sections, one per category.

    kept_indices uses combined numbering: 1..n_dep are deprecated items,
    n_dep+1..n_dep+n_dup are duplicate items.  When None, deprecated items
    default to Remove and duplicate items default to Keep.
    """
    example_vars = analysis["example_vars"]
    user_vars = analysis["user_vars"]
    extra = analysis["extra_classified"]
    dups = analysis.get("duplicates", [])
    n_dep = len(extra["deprecated"])
    n_dup = len(dups)

    if kept_indices is None:
        kept_indices = set(range(n_dep + 1, n_dep + n_dup + 1))

    if title:
        console.print(f"  [bold]{title}[/]")

    # ── RENAME ──
    if analysis["rename_log"] or analysis.get("rename_conflicts"):
        console.print("  [bold magenta]RENAME[/] [dim]— These variables have been renamed in the new version.[/]")
        table = _section_table(col1_header="Old name")
        table.add_column("Rename to", no_wrap=True, overflow="ellipsis")
        for old_name, new_name in analysis["rename_log"]:
            info = user_vars.get(new_name, {})
            table.add_row(
                old_name,
                _status_cell(info.get("active", False)),
                _truncate(_display_value(info)),
                f"[magenta]{new_name}[/]",
            )
        for conflict in analysis.get("rename_conflicts", []):
            table.add_row(
                conflict["old"],
                _status_cell(conflict["info"]["active"]),
                _truncate(_display_value(conflict["info"])),
                f"[yellow]{conflict['new']} [dim](already set)[/][/]",
            )
        console.print(table)
        console.print()

    # ── NEW ──
    if analysis["new_vars"]:
        console.print("  [bold cyan]NEW[/] [dim]— These variables will be added with their example defaults.[/]")
        table = Table(show_header=True, header_style="bold", show_lines=False, padding=(0, 1))
        table.add_column("Variable", no_wrap=True, overflow="ellipsis")
        table.add_column("Default status", width=16, no_wrap=True)
        table.add_column("Default value", no_wrap=True, overflow="ellipsis")
        for var in analysis["new_vars"]:
            info = example_vars[var]
            table.add_row(var, _status_cell(info["active"]), _truncate(_display_value(info)))
        console.print(table)
        console.print()

    # ── CUSTOM ──
    custom_vars = extra["custom_provider"] + extra["orphaned_provider"] + extra["custom_header"]
    if custom_vars:
        console.print("  [bold green]CUSTOM[/] [dim]— Custom provider and header variables will be preserved.[/]")
        table = _section_table()
        for var, _ in custom_vars:
            info = user_vars[var]
            table.add_row(var, _status_cell(info["active"]), _truncate(_display_value(info)))
        console.print(table)
        console.print()

    # ── DEPRECATED/UNKNOWN + DUPLICATES ──
    dep = extra["deprecated"]
    if dep or dups:
        console.print(
            "  [bold red]DEPRECATED/UNKNOWN[/] [dim]— Not in the new config file or duplicate entries. "
            "Review actions below.[/]"
        )
        table = _section_table(extra_cols=[("#", 4)])
        table.add_column("Action", width=8, no_wrap=True)

        for i, (var, _) in enumerate(dep, 1):
            info = user_vars[var]
            is_kept = i in kept_indices
            action = "[white]Keep[/]" if is_kept else "[red]Remove[/]"
            table.add_row(str(i), var, _status_cell(info["active"]), _truncate(_display_value(info)), action)

        for j, dup in enumerate(dups, 1):
            idx = n_dep + j
            is_kept = idx in kept_indices
            action = "[white]Keep[/]" if is_kept else "[red]Remove[/]"
            label = f"{dup['var_name']} [dim](duplicate)[/]"
            table.add_row(
                str(idx), label, _status_cell(dup["active"]),
                _truncate(_display_value(dup)), action,
            )

        console.print(table)
        console.print()

def _prompt_deprecated_selection(deprecated_count, duplicate_count=0):
    """Ask which deprecated/duplicate vars to keep. Returns a set of 1-based indices.

    Combined numbering: 1..deprecated_count are deprecated (default Remove),
    deprecated_count+1..total are duplicates (default Keep).
    """
    total = deprecated_count + duplicate_count
    if total == 0:
        return set()

    default_kept = set(range(deprecated_count + 1, total + 1))

    if default_kept:
        default_str = ",".join(str(i) for i in sorted(default_kept))
        console.print(
            f"[bold yellow]Select variables to KEEP by #[/] "
            f"[dim](duplicates kept by default: {default_str})[/]\n"
            "  Comma-separated numbers (e.g. 1,3,5) keep only those, "
            "[bold]all[/], [bold]none[/], or press Enter for the defaults:"
        )
    else:
        console.print(
            "[bold yellow]Select deprecated variables to KEEP (by #).[/]\n"
            "  Comma-separated numbers (e.g. 1,3,5), [bold]all[/], or press Enter to remove all:"
        )

    try:
        choice = console.input("  > ").strip().lower()
    except EOFError:
        console.print("  [dim]No input available, using defaults.[/]")
        return default_kept

    if choice == "all":
        return set(range(1, total + 1))
    if choice == "none":
        return set()
    if not choice:
        return default_kept

    indices = set()
    for part in choice.split(","):
        part = part.strip()
        if part.isdigit():
            idx = int(part)
            if 1 <= idx <= total:
                indices.add(idx)
    return indices

# ---------------------------------------------------------------------------
# Build migrated .env content
# ---------------------------------------------------------------------------

def _build_migrated_content(analysis, kept_deprecated_names, kept_duplicates=None):
    """Walk the .env.example template and fill in user values where they exist.

    - Config lines present in user env: user's value and active/commented state.
    - Config lines NOT in user env (new): kept as-is from the example.
    - Comment / blank lines: kept as-is from the example.
    - Extra vars (custom providers, headers, kept deprecated)
    - Kept duplicates
    """
    if kept_duplicates is None:
        kept_duplicates = []

    template_lines = analysis["template_lines"]
    user_vars = analysis["user_vars"]
    extra = analysis["extra_classified"]
    conflicts = analysis.get("rename_conflicts", [])

    out = []
    for tl in template_lines:
        if tl["type"] in ("blank", "comment"):
            out.append(tl["raw"])
            continue

        var = tl["var_name"]
        if var and var in user_vars and tl.get("substitute", True):
            out.append(_format_assignment(var, user_vars[var]))
        else:
            out.append(tl["raw"])

    extras_to_append = []
    for cat in ("custom_provider", "orphaned_provider", "custom_header"):
        extras_to_append.extend(var for var, _ in extra[cat])
    extras_to_append.extend(kept_deprecated_names)

    has_extras = extras_to_append or kept_duplicates or conflicts
    if has_extras:
        out.append("")
        out.append("## ==============================")
        out.append("## Variables preserved by migration tool")
        out.append(f"## Date: {date.today().isoformat()}")
        out.append(f"## Target AI SDK version: {AI_SDK_VERSION}")
        out.append("## ==============================")
        out.append("")
        for var in extras_to_append:
            if var in user_vars:
                out.append(_format_assignment(var, user_vars[var]))
        if conflicts:
            if out[-1]:
                out.append("")
            out.append("## Renamed variables whose new name was already in use.")
            out.append("## The value in use was kept. These are the old values.")
            for conflict in conflicts:
                out.append(_format_assignment(
                    conflict["new"], {**conflict["info"], "active": False}))
        if kept_duplicates:
            if out[-1]:
                out.append("")
            out.append("## Duplicate entries, kept for reference only.")
            for dup in kept_duplicates:
                out.append(_format_assignment(dup["var_name"], {**dup, "active": False}))

    return "\n".join(out) + "\n"

# ---------------------------------------------------------------------------
# Check that the migrated file still holds the same configuration
# ---------------------------------------------------------------------------

def _effective_values(text):
    """{name: value} as python-dotenv reads the file."""
    return {
        b.key: b.value
        for b in dotenv_parser.parse_stream(io.StringIO(text))
        if b.key and not b.error
    }

def _verify_migration(original_text, new_text, analysis, kept_deprecated_names):
    """List the variables the migration would change or lose.

    Every active variable must still have the same value afterwards, unless the
    user chose to drop it or it was renamed. An empty list means the migrated
    file is safe to write.
    """
    before = _effective_values(original_text)
    after = _effective_values(new_text)
    renames = dict(analysis.get("rename_log") or [])
    dropped = {
        var for var, _ in analysis["extra_classified"]["deprecated"]
        if var not in kept_deprecated_names
    }
    dropped.update(c["old"] for c in analysis.get("rename_conflicts", []))

    problems = []
    for name, value in before.items():
        target = renames.get(name, name)
        if target in dropped or name in dropped:
            continue
        if target not in after:
            problems.append(f"{name}: lost (no longer set)")
        elif after[target] != value:
            problems.append(
                f"{name}: value changed ({_truncate(value, 20)} -> {_truncate(after[target], 20)})"
            )
    return problems

# ---------------------------------------------------------------------------
# Backup (incrementing: .bak  →  .2.bak  →  .3.bak  …)
# ---------------------------------------------------------------------------

def _create_backup(filepath):
    """Create incremental backups: .bak, .2.bak, .3.bak, … (all match *.bak in .gitignore)."""
    base = filepath + ".bak"
    if not os.path.exists(base):
        shutil.copy2(filepath, base)
        return base

    counter = 2
    while True:
        candidate = f"{filepath}.{counter}.bak"
        if not os.path.exists(candidate):
            shutil.copy2(filepath, candidate)
            return candidate
        counter += 1

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_migration_tool():
    if not sys.stdin.isatty():
        console.print(Panel(
            Text.assemble(
                ("--migrate needs an interactive terminal.\n\n", "bold yellow"),
                ("The migration tool asks which deprecated and duplicate variables to "
                 "keep before rewriting your .env files, so it will not run "
                 "unattended. No files were modified. Re-run it from a terminal.",
                 "yellow"),
            ),
            border_style="yellow", width=PANEL_WIDTH, padding=(1, 2),
        ))
        return False

    _print_migration_header()
    known_providers = _get_known_providers()

    configs = [
        {
            "env_path": SDK_ENV_PATH,
            "example_path": SDK_EXAMPLE_PATH,
            "rename_rules": SDK_RENAME_RULES,
            "provider_keys": SDK_PROVIDER_KEYS,
            "label": "sdk_config.env",
        },
        {
            "env_path": CHATBOT_ENV_PATH,
            "example_path": CHATBOT_EXAMPLE_PATH,
            "rename_rules": CHATBOT_RENAME_RULES,
            "provider_keys": CHATBOT_PROVIDER_KEYS,
            "label": "chatbot_config.env",
        },
    ]

    # Phase 1 — Analyze each file, show sections, prompt for deprecated selection
    file_plans = []

    for cfg in configs:
        env_path = cfg["env_path"]
        example_path = cfg["example_path"]
        filename = cfg["label"]

        if not os.path.exists(env_path):
            console.print(f"  [dim]{filename}: not found, skipping.[/]\n")
            continue
        if not os.path.exists(example_path):
            console.print(f"  [dim]{os.path.basename(example_path)}: not found, skipping.[/]\n")
            continue

        analysis = _analyze(
            example_path, env_path,
            cfg["rename_rules"], cfg["provider_keys"], known_providers,
        )

        if analysis["parse_error"]:
            console.print(
                f"  [bold red]{filename} could not be parsed correctly.[/] "
                f"[red]It was left unchanged.[/]\n"
            )
            continue

        has_work = (
            analysis["rename_log"]
            or analysis["new_vars"]
            or any(analysis["extra_classified"][k] for k in analysis["extra_classified"])
            or analysis["duplicates"]
        )

        with console.status(f"[bold cyan]Analyzing {filename}…[/]", spinner="dots"):
            time.sleep(2)

        console.print(Panel(
            Text(f"  {filename}", style="bold white"),
            border_style="cyan", width=PANEL_WIDTH,
        ))
        _print_summary_line(analysis)

        if not has_work:
            console.print(f"  [green]Up to date — no migration needed.[/]\n")
            continue

        _render_sections(analysis)

        deprecated_items = analysis["extra_classified"]["deprecated"]
        duplicate_items = analysis["duplicates"]
        n_dep = len(deprecated_items)
        n_dup = len(duplicate_items)

        kept_indices = _prompt_deprecated_selection(n_dep, n_dup)

        kept_dep_indices = {i for i in kept_indices if i <= n_dep}
        kept_dup_indices = {i - n_dep for i in kept_indices if i > n_dep}
        kept_deprecated_names = [
            deprecated_items[i - 1][0] for i in sorted(kept_dep_indices)
        ]
        kept_duplicates = [
            duplicate_items[i - 1] for i in sorted(kept_dup_indices)
        ]

        console.print()
        file_plans.append({
            "env_path": env_path,
            "filename": filename,
            "analysis": analysis,
            "kept_indices": kept_indices,
            "kept_deprecated_names": kept_deprecated_names,
            "kept_duplicates": kept_duplicates,
        })

    if not file_plans:
        console.print("[green]All configuration files are up to date.[/]")
        return True

    # Phase 2 — Final summary (deprecated + duplicate selections)
    summary_title = Text("Migration summary\n", style="bold white", justify="center")
    summary_body = Text.assemble(
        ("Please review the deprecated/unknown and duplicate variables that\n", ""),
        ("will be kept or removed. When in doubt, keep the variable. If you\n", ""),
        ("want to change anything, exit now and re-run with the ", ""),
        ("--migrate", "bold cyan"),
        (" flag.", ""),
    )
    console.print(Panel(
        Group(summary_title, summary_body),
        border_style="green", width=PANEL_WIDTH, padding=(1, 2),
    ))

    for plan in file_plans:
        analysis = plan["analysis"]
        dep = analysis["extra_classified"]["deprecated"]
        dups = analysis.get("duplicates", [])
        n_dep = len(dep)
        console.print(f"  [bold]{plan['filename']}[/]")

        if dep or dups:
            kept = plan["kept_indices"]
            table = _section_table(extra_cols=[("#", 4)])
            table.add_column("Action", width=8, no_wrap=True)

            for i, (var, _) in enumerate(dep, 1):
                info = analysis["user_vars"][var]
                is_kept = i in kept
                action = "[white]Keep[/]" if is_kept else "[red]Remove[/]"
                table.add_row(str(i), var, _status_cell(info["active"]), _truncate(_display_value(info)), action)

            for j, dup in enumerate(dups, 1):
                idx = n_dep + j
                is_kept = idx in kept
                action = "[white]Keep[/]" if is_kept else "[red]Remove[/]"
                label = f"{dup['var_name']} [dim](duplicate)[/]"
                table.add_row(
                    str(idx), label, _status_cell(dup["active"]),
                    _truncate(_display_value(dup)), action,
                )

            console.print(table)
            console.print()
        else:
            console.print("  [dim]No deprecated or duplicate variables.[/]\n")

    if not Confirm.ask("[bold yellow]Apply the migration(s) shown above?[/]"):
        console.print("\n[bold red]Migration cancelled by user.[/]")
        return False

    # Phase 3 — Apply
    errors = 0
    for plan in file_plans:
        filepath = plan["env_path"]
        filename = plan["filename"]
        content = _build_migrated_content(
            plan["analysis"], plan["kept_deprecated_names"],
            plan.get("kept_duplicates", []),
        )
        try:
            problems = _verify_migration(
                _read_text(filepath), content, plan["analysis"],
                plan["kept_deprecated_names"],
            )
            if problems:
                console.print(Panel(
                    Text.assemble(
                        (f"{filename} was NOT migrated.\n\n", "bold red"),
                        ("The rewritten file would not resolve to the same "
                         "configuration, so it was left untouched:\n", "red"),
                        ("\n".join(f"  - {p}" for p in problems), "dim"),
                    ),
                    border_style="red", width=PANEL_WIDTH, padding=(1, 2),
                ))
                errors += 1
                continue

            backup = _create_backup(filepath)
            console.print(f"  -> Backup created: [dim]{backup}[/]")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            console.print(f"  -> [bold green]{filename} migrated[/]")
        except Exception as exc:
            console.print(f"  [bold red]Error migrating {filename}: {exc}[/]")
            errors += 1

    console.print()
    if errors:
        console.print(f"[bold red]Migration finished with {errors} error(s).[/]")
        return False

    console.print(f"[bold green]Migration to {AI_SDK_VERSION} completed successfully.[/]")
    return True
