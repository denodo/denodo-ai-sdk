from rich.text import Text
from rich.panel import Panel
from rich.console import Console

console = Console()

PANEL_WIDTH = 60

def print_header():
    console.print(Panel(
        Text("Denodo AI SDK", style="bold white", justify="center"),
        border_style="cyan",
        padding=(1, 2),
        width=PANEL_WIDTH
    ))

def print_status(process_type, urls, version=None, root_path_prefix=""):
    server_url = urls[0]
    full_url = server_url.rstrip('/') + root_path_prefix

    if process_type == "api":
        panel = Panel(
            Text.assemble(
                ("AI SDK ", "bold red"),
                ("is running at: ", "bold white"),
                (f"{full_url}\n", "green"),
                ("Swagger docs: ", "bold white"),
                (f"{full_url}/docs\n", "green"),
                ("AI SDK version: ", "bold white"),
                (f"{version or 'Unknown'}", "yellow")
            ),
            title="[bold]API Status",
            border_style="red",
            width=PANEL_WIDTH
        )
    else:
        segments = []
        for i, url in enumerate(urls):
            full_chatbot_url = url.rstrip('/') + root_path_prefix
            segments.extend([
                ("Sample Chatbot ", "bold blue"),
                ("is running at: ", "bold white"),
                (full_chatbot_url, "green")
            ])
            if i < len(urls) - 1:
                segments.append(("\n", ""))

        panel = Panel(
            Text.assemble(*segments),
            title="[bold]Chatbot Status",
            border_style="blue",
            width=PANEL_WIDTH
        )
    console.print(panel)