from rich.text import Text
from rich.panel import Panel
from rich.console import Console

from utils.status import Status

console = Console()

PANEL_WIDTH = 60
STATUS_STYLES = {
    Status.OK: "green",
    Status.WARNING: "yellow",
    Status.ERROR: "red",
}

def _status_list_segments(title, items):
    if not items:
        return []

    segments = [
        ("\n\n", ""),
        (f"{title}\n", "bold white"),
    ]

    for index, item in enumerate(items):
        if not isinstance(item, dict):
            item = {"name": item, "status": Status.OK}

        raw_status = item.get("status", Status.OK)
        try:
            status = Status(str(raw_status).upper())
        except ValueError:
            status = Status.ERROR

        style = STATUS_STYLES.get(status, "white")

        segments.extend([
            (f"[{status}] ", style),
            (str(item.get("name")), "white"),
        ])

        if index < len(items) - 1:
            segments.append(("\n", ""))
    return segments

def _build_chatbot_segments(urls, root_path_prefix="", imported_agent_names=None, imported_skills=None):
    imported_agent_names = imported_agent_names or []
    imported_skills = imported_skills or []
    segments = []

    for i, url in enumerate(urls):
        full_chatbot_url = url.rstrip('/') + root_path_prefix
        segments.extend([
            ("Sample chatbot ", "bold blue"),
            ("is running at: ", "bold white"),
            (full_chatbot_url, "green")
        ])
        if i < len(urls) - 1:
            segments.append(("\n", ""))

    segments.extend(_status_list_segments("Specialized agents:", imported_agent_names))
    segments.extend(_status_list_segments("Skills:", imported_skills))
    return segments

def print_header():
    console.print(Panel(
        Text("Denodo AI SDK", style="bold white", justify="center"),
        border_style="cyan",
        padding=(1, 2),
        width=PANEL_WIDTH
    ))

def print_status(
    process_type,
    urls,
    version=None,
    root_path_prefix="",
    imported_agent_names=None,
    imported_space_names=None,
    imported_skills=None,
):
    server_url = urls[0]
    full_url = server_url.rstrip("/") + root_path_prefix
    imported_agent_names = imported_agent_names or []
    imported_space_names = imported_space_names or []
    imported_skills = imported_skills or []

    if process_type == "api":
        segments = [
            ("AI SDK ", "bold red"),
            ("is running at: ", "bold white"),
            (f"{full_url}\n", "green"),
            ("Swagger docs: ", "bold white"),
            (f"{full_url}/docs\n", "green"),
            ("AI SDK version: ", "bold white"),
            (f"{version or 'Unknown'}", "yellow"),
        ]
        segments.extend(_status_list_segments("AI Spaces:", imported_space_names))
        panel = Panel(
            Text.assemble(*segments),
            title="[bold]API status",
            border_style="red",
            width=PANEL_WIDTH
        )
    else:
        panel = Panel(
            Text.assemble(*_build_chatbot_segments(urls, root_path_prefix, imported_agent_names, imported_skills)),
            title="[bold]Chatbot status",
            border_style="blue",
            width=PANEL_WIDTH
        )
    console.print(panel)
