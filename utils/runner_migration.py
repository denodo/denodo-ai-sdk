import os
import shutil
import time
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Confirm
from rich.table import Table
from utils.version import AI_SDK_VERSION

console = Console()
PANEL_WIDTH = 60

SDK_ENV_PATH = os.path.join(".", "api", "utils", "sdk_config.env")
CHATBOT_ENV_PATH = os.path.join(".", "sample_chatbot", "chatbot_config.env")

def print_migration_tool_header():
    header_content = Text.assemble(
        ("Migration Tool\n", "bold white"),
        (f"{AI_SDK_VERSION}", "bold cyan")
    )
    header_content.justify = "center"

    console.print(Panel(
        header_content,
        border_style="cyan",
        padding=(1, 2),
        width=PANEL_WIDTH
    ))

    warning_text = Text.assemble(
        ("WARNING: ", "bold yellow"),
        ("The migration tool is designed to detect and update configuration variable changes in the _config.env files. "
         "If your configuration files are older than 0.12, please review the changes carefully before applying.", "yellow")
    )

    console.print(Panel(
        warning_text,
        border_style="yellow",
        width=PANEL_WIDTH,
        padding=(1, 2)
    ))
    console.print()

def print_proposed_changes(all_changes):
    table = Table(title="Proposed Changes", show_header=True, header_style="bold magenta")
    table.add_column("File", style="dim", width=20)
    table.add_column("Before", style="red")
    table.add_column("After", style="green")

    for row in all_changes:
        table.add_row(*row)

    console.print(table)
    console.print()

def analyze_changes(content, app_type):
    """
    Analyzes content and returns a list of changes and the new content.
    """
    changes = []
    new_content = content

    if app_type == "sdk":
        if "AI_SDK_DATA_CATALOG_URL" in new_content:
            changes.append(("AI_SDK_DATA_CATALOG_URL", "AI_SDK_DATA_MARKETPLACE_URL"))
            new_content = new_content.replace("AI_SDK_DATA_CATALOG_URL", "AI_SDK_DATA_MARKETPLACE_URL")

        if "DATA_CATALOG_URL" in new_content:
            changes.append(("DATA_CATALOG_URL", "AI_SDK_DATA_MARKETPLACE_URL"))
            new_content = new_content.replace("DATA_CATALOG_URL", "AI_SDK_DATA_MARKETPLACE_URL")

    elif app_type == "chatbot":
        if "CHATBOT_DATA_CATALOG_URL" in new_content:
            changes.append(("CHATBOT_DATA_CATALOG_URL", "CHATBOT_DATA_MARKETPLACE_URL"))
            new_content = new_content.replace("CHATBOT_DATA_CATALOG_URL", "CHATBOT_DATA_MARKETPLACE_URL")

        if "DATA_CATALOG_URL" in new_content:
            changes.append(("DATA_CATALOG_URL", "CHATBOT_DATA_MARKETPLACE_URL"))
            new_content = new_content.replace("DATA_CATALOG_URL", "CHATBOT_DATA_MARKETPLACE_URL")

    if "DATA_CATALOG" in new_content:
        changes.append(("DATA_CATALOG","DATA_MARKETPLACE"))
        new_content = new_content.replace("DATA_CATALOG", "DATA_MARKETPLACE")

    return changes, new_content

def run_migration_tool():
    print_migration_tool_header()

    files_to_process = [
        (SDK_ENV_PATH, 'sdk'),
        (CHATBOT_ENV_PATH, 'chatbot')
    ]

    all_changes = []
    ready_updates = []

    for filepath, app_type in files_to_process:
        filename = os.path.basename(filepath)

        if not os.path.exists(filepath):
            console.print(f"[bold red]{filename}: File not found")
            continue

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        changes, new_content = analyze_changes(content, app_type)
        if changes:
            for before, after in changes:
                all_changes.append([filename, before, after])
            ready_updates.append((filepath, new_content))

    if not ready_updates and not all_changes:
        console.print("No automatic updates needed.")
        return True

    if all_changes:
        print_proposed_changes(all_changes)

        if not Confirm.ask("[bold yellow]Do you want to apply these changes?[/]"):
            console.print("\n[bold red]Migration cancelled by user.[/]")
            return False

    errors = 0
    for filepath, new_content in ready_updates:
        # Create backup
        timestamp = int(time.time())
        backup_path = f"{filepath}.{timestamp}.bak"

        try:
            shutil.copy2(filepath, backup_path)
            console.print(f"-> Backup created: [dim]{backup_path}[/]")

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            console.print(f"-> [bold green]{filepath} Updated[/]")

        except Exception as e:
            console.print(f"[bold red]Error updating {filepath}: {e}[/]")
            errors += 1

    if errors > 0:
        console.print("\n[bold red]Migration failed for some files.[/]")
        return False

    console.print(f"\n[bold green]Migration to {AI_SDK_VERSION} completed successfully.[/]")
    return True
