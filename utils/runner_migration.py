import os
import re
import shutil
import time
from datetime import date
from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.prompt import Confirm
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
    ("AI_SDK_DATA_CATALOG_URL", "AI_SDK_DATA_MARKETPLACE_URL"),
    ("DATA_CATALOG_URL", "AI_SDK_DATA_MARKETPLACE_URL"),
    ("DATA_CATALOG", "DATA_MARKETPLACE"),
]

CHATBOT_RENAME_RULES = [
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

_VAR_RE = re.compile(r'^([A-Za-z_][A-Za-z0-9_\-]*)\s*=\s*(.*)')

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

def _parse_env_variables(filepath):
    """Parse an env file into {var_name: {"active": bool, "value": str}}.
    Skips ## explanation lines and blank lines.
    When a variable appears more than once, the last occurrence is kept as
    primary and earlier occurrences are returned separately as duplicates.
    """
    variables = {}
    duplicates = []
    if not os.path.exists(filepath):
        return variables, duplicates

    with open(filepath, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("##"):
                continue
            commented = stripped.startswith("#")
            cleaned = stripped.lstrip("#").strip()
            m = _VAR_RE.match(cleaned)
            if m:
                var_name = m.group(1)
                info = {"active": not commented, "value": m.group(2).strip()}
                if var_name in variables:
                    duplicates.append({"var_name": var_name, **variables[var_name]})
                variables[var_name] = info
    return variables, duplicates


def _parse_example_template(filepath):
    """Parse a .env.example into an ordered list of template lines and a variable dict.

    Returns (template_lines, example_vars).
    Each template line is {"raw": str, "type": "blank"|"comment"|"config",
                           "var_name": str|None, "active": bool}.
    """
    template_lines = []
    example_vars = {}

    if not os.path.exists(filepath):
        return template_lines, example_vars

    with open(filepath, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n\r")
            stripped = line.strip()

            if not stripped:
                template_lines.append({"raw": line, "type": "blank", "var_name": None, "active": False})
                continue

            if stripped.startswith("##"):
                template_lines.append({"raw": line, "type": "comment", "var_name": None, "active": False})
                continue

            commented = stripped.startswith("#")
            cleaned = stripped.lstrip("#").strip()
            m = _VAR_RE.match(cleaned)
            if m:
                var_name, value = m.group(1), m.group(2).strip()
                template_lines.append({
                    "raw": line, "type": "config",
                    "var_name": var_name, "active": not commented,
                })
                example_vars[var_name] = {"active": not commented, "value": value}
            else:
                template_lines.append({"raw": line, "type": "comment", "var_name": None, "active": False})

    return template_lines, example_vars

# ---------------------------------------------------------------------------
# Rename logic
# ---------------------------------------------------------------------------

def _apply_renames(variables, rename_rules):
    """Apply ordered rename rules (substring replacement) to variable names.

    Returns (renamed_dict, rename_log) where rename_log is [(old, new), ...].
    If two old names map to the same new name, the first one seen wins.
    """
    renamed = {}
    rename_log = []

    for var_name, info in variables.items():
        new_name = var_name
        for old_sub, new_sub in rename_rules:
            if old_sub in new_name:
                new_name = new_name.replace(old_sub, new_sub)
                break

        if new_name != var_name:
            rename_log.append((var_name, new_name))

        if new_name not in renamed:
            renamed[new_name] = info

    return renamed, rename_log


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
        if key in env_vars and env_vars[key]["value"]:
            pname = env_vars[key]["value"].strip().strip('"').strip("'")
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
    user_vars_raw, duplicates_raw = _parse_env_variables(env_path)
    user_vars, rename_log = _apply_renames(user_vars_raw, rename_rules)
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
    }

# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _truncate(value, max_len=25):
    if not value:
        return "(empty)"
    return value[:max_len] + ("…" if len(value) > max_len else "")


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
    if analysis["rename_log"]:
        console.print("  [bold magenta]RENAME[/] [dim]— These variables have been renamed in the new version.[/]")
        table = _section_table(col1_header="Old name")
        table.add_column("Rename to", no_wrap=True, overflow="ellipsis")
        for old_name, new_name in analysis["rename_log"]:
            info = user_vars.get(new_name, {})
            table.add_row(
                old_name,
                _status_cell(info.get("active", False)),
                _truncate(info.get("value", "")),
                f"[magenta]{new_name}[/]",
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
            table.add_row(var, _status_cell(info["active"]), _truncate(info["value"]))
        console.print(table)
        console.print()

    # ── CUSTOM ──
    custom_vars = extra["custom_provider"] + extra["orphaned_provider"] + extra["custom_header"]
    if custom_vars:
        console.print("  [bold green]CUSTOM[/] [dim]— Custom provider and header variables will be preserved.[/]")
        table = _section_table()
        for var, _ in custom_vars:
            info = user_vars[var]
            table.add_row(var, _status_cell(info["active"]), _truncate(info["value"]))
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
            table.add_row(str(i), var, _status_cell(info["active"]), _truncate(info["value"]), action)

        for j, dup in enumerate(dups, 1):
            idx = n_dep + j
            is_kept = idx in kept_indices
            action = "[white]Keep[/]" if is_kept else "[red]Remove[/]"
            label = f"{dup['var_name']} [dim](duplicate)[/]"
            table.add_row(
                str(idx), label, _status_cell(dup["active"]),
                _truncate(dup["value"]), action,
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
            "  Comma-separated numbers (e.g. 1,3,5), [bold]all[/], [bold]none[/], "
            "or press Enter for defaults:"
        )
    else:
        console.print(
            "[bold yellow]Select deprecated variables to KEEP (by #).[/]\n"
            "  Comma-separated numbers (e.g. 1,3,5), [bold]all[/], or press Enter to remove all:"
        )

    choice = console.input("  > ").strip().lower()

    if choice == "all":
        return set(range(1, total + 1))
    if choice == "none":
        return set()
    if not choice:
        return default_kept

    indices = set(default_kept)
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
    - Extra vars (custom providers, headers, kept deprecated, kept duplicates):
      appended at the end.
    """
    if kept_duplicates is None:
        kept_duplicates = []

    template_lines = analysis["template_lines"]
    user_vars = analysis["user_vars"]
    extra = analysis["extra_classified"]

    out = []
    for tl in template_lines:
        if tl["type"] in ("blank", "comment"):
            out.append(tl["raw"])
            continue

        var = tl["var_name"]
        if var and var in user_vars:
            info = user_vars[var]
            prefix = "" if info["active"] else "#"
            out.append(f"{prefix}{var}={info['value']}")
        else:
            out.append(tl["raw"])

    extras_to_append = []
    for cat in ("custom_provider", "orphaned_provider", "custom_header"):
        extras_to_append.extend(var for var, _ in extra[cat])
    extras_to_append.extend(kept_deprecated_names)

    has_extras = extras_to_append or kept_duplicates
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
                info = user_vars[var]
                prefix = "" if info["active"] else "#"
                out.append(f"{prefix}{var}={info['value']}")
        for dup in kept_duplicates:
            prefix = "" if dup["active"] else "#"
            out.append(f"{prefix}{dup['var_name']}={dup['value']}")

    return "\n".join(out) + "\n"

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
                table.add_row(str(i), var, _status_cell(info["active"]), _truncate(info["value"]), action)

            for j, dup in enumerate(dups, 1):
                idx = n_dep + j
                is_kept = idx in kept
                action = "[white]Keep[/]" if is_kept else "[red]Remove[/]"
                label = f"{dup['var_name']} [dim](duplicate)[/]"
                table.add_row(
                    str(idx), label, _status_cell(dup["active"]),
                    _truncate(dup["value"]), action,
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
