import os
import sys
import time
import signal
import argparse
import threading
from rich.panel import Panel
from rich.console import Console
from utils.runner_demo import load_demo_data
from utils.runner_display import print_header, PANEL_WIDTH
from utils.runner_process import run_process, shutdown_gracefully, command_listener
from utils.utils import is_in_venv

console = Console()

def parse_arguments():
    parser = argparse.ArgumentParser(description="Run the AI SDK API and/or sample chatbot with configurable timeout.")
    parser.add_argument("mode", choices=["api", "sample_chatbot", "both"], help="Mode to run: api, sample_chatbot, or both")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout in seconds (default: 30)")
    parser.add_argument("--load-demo", action="store_true", help="Load demo data before starting (only works with 'both' mode)")
    parser.add_argument("--host", default="localhost", help="GRPC host (default: localhost)")
    parser.add_argument("--grpc-port", type=int, default=9994, help="GRPC port (default: 9994)")
    parser.add_argument("--dc-port", type=int, default=9090, help="Data Catalog port (default: 9090)")
    parser.add_argument("--server-id", type=int, default=1, help="Server ID (default: 1)")
    parser.add_argument("--dc-user", default="admin", help="Data Catalog user (default: admin)")
    parser.add_argument("--dc-password", default="admin", help="Data Catalog password (default: admin)")
    parser.add_argument("--no-logs", action="store_true", help="Output logs to console instead of files (interactive mode only)")
    parser.add_argument("--max-log-size", type=int, default=1, help="Maximum log file size in MB before rotation (default: 1)")
    parser.add_argument("--production", action="store_true", help="Run in production mode")
    parser.add_argument("--background", action="store_true", help="Run processes in the background and exit after they start.")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO"], default="INFO", help="Set the logging level (default: INFO)")
    parser.add_argument("--mcp", nargs="?", const="remote", choices=["local", "remote"], help="Enable MCP server mode: local or remote (default: remote if flag is present)")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()
    processes_to_run = []
    processes = []
    log_threads = []

    print_header()

    # Check if running in a virtual environment
    if not is_in_venv():
        console.print(Panel(
            "[bold yellow]WARNING: Not Running in Virtual Environment[/]\n"
            "[yellow]You are not running this application inside a virtual environment.\n"
            "This may cause dependency conflicts in the AI SDK that may cause it to not work properly.\n"
            "It is strongly recommended to use a virtual environment.",
            border_style="yellow",
            width=PANEL_WIDTH
        ))

    # Set the tiktoken cache dir to be able to use the AI SDK in offline environments
    # The tiktoken dependency tries to download from the Internet the tokenizer model for the LLM if not
    # Comment out if you're fine with this behavior
    os.environ["TIKTOKEN_CACHE_DIR"] = "./cache/tiktoken/"

    # Configure MCP mode if enabled
    if args.mcp == "remote":
        os.environ["AI_SDK_MCP_MODE"] = "remote"
        console.print(Panel(
            "[bold green]Remote MCP Server with HTTP[/]\n"
            "[white]The API will include remote HTTP MCP endpoints at /mcp[/]",
            border_style="green",
            width=PANEL_WIDTH
        ))

    # Show production mode warning if enabled
    if args.production:
        console.print(Panel(
            "[bold yellow]Production mode uses Gunicorn ASGI server on UNIX systems and Uvicorn ASGI server on Windows.",
            border_style="yellow",
            width=PANEL_WIDTH
        ))

    try:
        if args.load_demo:
            if not load_demo_data(args.host, args.grpc_port, args.dc_port, args.server_id, args.dc_user, args.dc_password):
                console.print("[bold red]ERROR:[/] Failed to load demo data. Please check the logs for more information.")
                sys.exit(1)

        if args.mode in ["api", "both"]:
            processes_to_run.append("api")
        if args.mode in ["sample_chatbot", "both"]:
            processes_to_run.append("sample_chatbot")

        any_failures = False
        for process_name in processes_to_run:
            try:
                process, log_thread = run_process(process_name, args)
                if process_name == "api":
                    processes.append(("API", process))
                elif process_name == "sample_chatbot":
                    processes.append(("Chatbot", process))
                log_threads.append(log_thread)
            except TimeoutError:
                # Display formatted error panel with debugging instructions
                service_display_name = "AI SDK" if process_name == "api" else "Sample Chatbot"
                log_file_path = f"logs/{process_name}.log"
                debug_command = f"python -m {process_name}.main"

                console.print(Panel(
                    f"[bold red]{service_display_name} failed to start within {args.timeout} seconds[/]\n\n"
                    f"[white]Check the logs at [cyan]{log_file_path}[/cyan] for more details.[/]\n\n"
                    f"[white]If that doesn't give any details, you can also run the module directly to debug the startup error:[/]\n"
                    f"[yellow]{debug_command}[/]\n\n"
                    f"[italic]Reminder: You should only execute this way to debug, not for execution purposes.[/]",
                    title=f"[bold red]Startup Error - {service_display_name}[/]",
                    border_style="red",
                    width=PANEL_WIDTH
                ))
                any_failures = True

        if args.background:
            if any_failures:
                console.print("\n[bold red]One or more services failed to start. Check the logs. Processes that started successfully are running in the background.[/]")
                sys.exit(1)
            else:
                console.print("\n[bold green]All services started successfully in the background.[/]")
                console.print("[bold cyan]Use stop.py to stop the services.[/bold cyan]")
                sys.exit(0)

        if processes:
            if sys.stdin.isatty():
                if args.mcp == "local":
                    console.print(Panel(
                        "[white]To run a local MCP server, please refer to the official Denodo AI SDK documentation in the README.[/]\n\n"
                        "[white]The documentation contains detailed instructions on configuring and running local MCP servers with stdio.[/]",
                        border_style="green",
                        width=PANEL_WIDTH,
                        title="[bold]Local MCP Server with stdio[/]"
                    ))
                console.print("\n[bold cyan]Type 'exit' and press Enter to stop the application(s).[/bold cyan]")
                cmd_listener_thread = threading.Thread(
                    target=command_listener,
                    args=(processes,),
                    daemon=True
                )
                cmd_listener_thread.start()
            else:
                signal.signal(signal.SIGTERM, lambda *_: shutdown_gracefully(processes))
                signal.signal(signal.SIGINT, lambda *_: shutdown_gracefully(processes))

        while any(p[1].poll() is None for p in processes):
            for name, process in list(processes):
                if process.poll() is not None:
                    console.print(f"[yellow]{name} process ended unexpectedly.[/]")
                    processes.remove((name, process))
            time.sleep(1)

    except KeyboardInterrupt:
        shutdown_gracefully(processes)

    except Exception as e:
        console.print(f"[bold red]Error:[/] {e}")
        shutdown_gracefully(processes)
        sys.exit(1)

    finally:
        # Cleanup for interactive mode
        if not args.background:
            for thread in log_threads:
                thread.join()

            console.print("[bold green]Shutdown complete.[/]")
            sys.exit(0)