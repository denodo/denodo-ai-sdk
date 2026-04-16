"""
 Copyright (c) 2025. DENODO Technologies.
 http://www.denodo.com
 All rights reserved.

 This software is the confidential and proprietary information of DENODO
 Technologies ("Confidential Information"). You shall not disclose such
 Confidential Information and shall use it only in accordance with the terms
 of the license agreement you entered into with DENODO.
"""

import os
import sys
import time
import signal
import argparse
import threading
from dotenv import dotenv_values
from rich.panel import Panel
from rich.console import Console
from utils.runner_migration import run_migration_tool
from utils.runner_demo import load_demo_data
from utils.runner_display import print_header, PANEL_WIDTH
from utils.runner_process import run_process, shutdown_gracefully, command_listener
from utils.utils import is_in_venv, validate_data_dir

console = Console()

def parse_arguments():
    parser = argparse.ArgumentParser(description="Run the AI SDK API and/or sample chatbot with configurable timeout.")
    parser.add_argument("mode", choices=["api", "sample_chatbot", "both"], help="Mode to run: api, sample_chatbot, or both")
    parser.add_argument("--migrate", action="store_true", help="Run the migration tool before starting services")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout in seconds (default: 30)")
    parser.add_argument("--host", default="localhost", help="GRPC host (default: localhost)")
    parser.add_argument("--grpc-port", type=int, default=9994, help="GRPC port (default: 9994)")
    parser.add_argument("--dm-port", "--dc-port", dest="dc_port", metavar="DM_PORT", type=int, default=9090, help="Data Marketplace port (default: 9090)")
    parser.add_argument("--server-id", type=int, default=1, help="Server ID (default: 1)")
    parser.add_argument("--dm-user", "--dc-user", dest="dc_user", metavar="DM_USER", default="admin", help="Data Marketplace user (default: admin)")
    parser.add_argument("--dm-password", "--dc-password", dest="dc_password", metavar="DM_PASSWORD", default="admin", help="Data Marketplace password (default: admin)")
    parser.add_argument("--no-logs", action="store_true", help="Output logs to console instead of files (interactive mode only)")
    parser.add_argument("--max-log-size", type=int, default=1, help="Maximum log file size in MB before rotation (default: 1)")
    parser.add_argument("--production", action="store_true", help="Run in production mode")
    parser.add_argument("--background", action="store_true", help="Run processes in the background and exit after they start.")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO"], default="INFO", help="Set the logging level (default: INFO)")
    parser.add_argument("--mcp", nargs="?", const="remote", choices=["remote"], help="Enable remote MCP server via HTTP")
    _demo = parser.add_mutually_exclusive_group()
    _demo.add_argument("--load-demo", action="store_true", help="Load demo data (only with mode 'both'). Prompts before overwriting samples_bank if it exists.")
    _demo.add_argument("--load-demo-overwrite", action="store_true", help="Load demo data (only with mode 'both') and drop existing samples_bank without prompting. For non-interactive runs. Cannot be combined with --load-demo.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()

    if args.migrate:
        run_migration_tool()
        console.print("[dim]Continuing with startup...[/dim]\n")

    processes_to_run = []
    processes = []
    log_threads = []

    print_header()

    env_api = dotenv_values('api/utils/sdk_config.env') if args.mode in ["api", "both"] else {}
    env_chat = dotenv_values('sample_chatbot/chatbot_config.env') if args.mode in ["sample_chatbot", "both"] else {}

    if args.mode == "both":
        dir_api = env_api.get("AI_SDK_DATA_DIR")
        dir_chat = env_chat.get("AI_SDK_DATA_DIR")

        if dir_api and dir_chat and dir_api != dir_chat:
            console.print(Panel(
                f"[bold yellow]WARNING: Data Directory Mismatch[/]\n\n"
                f"You are running in 'both' mode but have different paths configured:\n"
                f" • sdk_config.env: [cyan]{dir_api}[/]\n"
                f" • chatbot_config.env: [cyan]{dir_chat}[/]\n\n"
                f"To prevent data separation, the system will force the sdk_config.env path:\n"
                f"[bold white]{dir_api}[/]\n\n"
                f"[italic]Please fix your .env files to ensure consistent data persistence.[/]",
                border_style="yellow",
                width=PANEL_WIDTH
            ))
            env_chat["AI_SDK_DATA_DIR"] = dir_api

    env_dict = {**env_api, **env_chat}
    if "AI_SDK_DATA_DIR" in env_dict:
        os.environ["AI_SDK_DATA_DIR"] = env_dict["AI_SDK_DATA_DIR"]

    DATA_DIR = validate_data_dir()

    # Check if running in a virtual environment
    if not is_in_venv():
        console.print(Panel(
            "[bold yellow]WARNING: Not running in virtual environment[/]\n"
            "[yellow]This application is not running inside a virtual environment.\n"
            "This may cause dependency conflicts in the AI SDK.\n"
            "If using the provided image of the AI SDK, you can ignore this warning, as all dependencies are included already.",
            border_style="yellow",
            width=PANEL_WIDTH
        ))

    os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "true"

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
        if args.load_demo or args.load_demo_overwrite:
            if args.mode != "both":
                console.print(
                    "[bold red]ERROR:[/] Demo loading is only supported with mode [cyan]both[/] "
                    "(e.g. [cyan]python run.py both --load-demo[/] or [cyan]both --load-demo-overwrite[/])."
                )
                sys.exit(1)
            if not load_demo_data(
                args.host,
                args.grpc_port,
                args.dc_port,
                args.server_id,
                args.dc_user,
                args.dc_password,
                demo_overwrite=args.load_demo_overwrite,
            ):
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
                    processes.append(("chatbot", process))
                log_threads.append(log_thread)
            except TimeoutError:
                # Display formatted error panel with debugging instructions
                service_display_name = "AI SDK" if process_name == "api" else "Sample chatbot"
                log_file_path = os.path.join(DATA_DIR, "logs", f"{process_name}.log") if DATA_DIR != "." else f"logs/{process_name}.log"
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
