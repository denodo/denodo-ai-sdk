from rich.text import Text
from rich.panel import Panel
from rich.console import Console

console = Console()

PANEL_WIDTH = 60

def _ok_list_segments(title, names):
    if not names:
        return []

    segments = [
        ("\n\n", ""),
        (f"{title}\n", "bold white"),
    ]
    for index, name in enumerate(names):
        segments.extend([
            ("[OK] ", "green"),
            (name, "white"),
        ])
        if index < len(names) - 1:
            segments.append(("\n", ""))
    return segments

def _build_chatbot_segments(urls, root_path_prefix="", imported_agent_names=None):
    imported_agent_names = imported_agent_names or []
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

    segments.extend(_ok_list_segments("Imported specialized agents:", imported_agent_names))
    return segments

def print_header():
    console.print(Panel(
        Text("Denodo AI SDK", style="bold white", justify="center"),
        border_style="cyan",
        padding=(1, 2),
        width=PANEL_WIDTH
    ))

def print_status(process_type, urls, version=None, root_path_prefix="", imported_agent_names=None, imported_space_names=None):
    server_url = urls[0]
    full_url = server_url.rstrip('/') + root_path_prefix
    imported_agent_names = imported_agent_names or []
    imported_space_names = imported_space_names or []

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
        segments.extend(_ok_list_segments("Imported AI Spaces:", imported_space_names))
        panel = Panel(
            Text.assemble(*segments),
            title="[bold]API status",
            border_style="red",
            width=PANEL_WIDTH
        )
    else:
        panel = Panel(
            Text.assemble(*_build_chatbot_segments(urls, root_path_prefix, imported_agent_names)),
            title="[bold]Chatbot status",
            border_style="blue",
            width=PANEL_WIDTH
        )
    console.print(panel)
