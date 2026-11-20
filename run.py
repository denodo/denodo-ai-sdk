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
from dotenv import dotenv_values, load_dotenv
from rich.panel import Panel
from rich.console import Console
from utils.chatbot_env import (
    LEGACY_ENV_WARNING_DETAIL,
    LEGACY_ENV_WARNING_TITLE,
    chatbot_env_startup_notice,
    resolve_chatbot_env_path,
)
from utils.runner_migration import run_migration_tool
from utils.runner_demo import load_demo_data
from utils.runner_display import print_header, PANEL_WIDTH
from utils.runner_process import (
    spawn_services,
    wait_for_services,
    shutdown_gracefully,
    command_listener,
    get_service_name,
    abort_sibling_services,
)
from utils.utils import is_in_venv, validate_data_dir, get_api_data_dir, get_chatbot_data_dir

console = Console()

def parse_arguments():
    parser = argparse.ArgumentParser(description="Run the AI SDK API and/or sample chatbot with configurable timeout.")
    parser.add_argument("mode", nargs="?", choices=["api", "sample_chatbot", "both"], help="Mode to run: api, sample_chatbot, or both. Not required with --migrate-only or --migrate-only-and-force")
    _migrate = parser.add_mutually_exclusive_group()
    _migrate.add_argument("--migrate", action="store_true", help="Run the interactive migration tool before starting services")
    _migrate.add_argument("--migrate-only", action="store_true", help="Run the interactive migration tool and exit without starting services")
    _migrate.add_argument("--migrate-force", action="store_true", help="Run the migration non-interactively and then start services. Unknown variables and duplicates are kept")
    _migrate.add_argument("--migrate-only-and-force", action="store_true", help="Run the migration non-interactively and exit without starting services. Unknown variables and duplicates are kept")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout in seconds (default: 30)")
    parser.add_argument("--host", default="localhost", help="GRPC host (default: localhost)")
    parser.add_argument("--grpc-port", type=int, default=9994, help="GRPC port (default: 9994)")
    parser.add_argument("--dm-port", "--dc-port", dest="dc_port", metavar="DM_PORT", type=int, default=9090, help="Data Marketplace port (default: 9090)")
    parser.add_argument("--server-id", type=int, default=1, help="Server ID (default: 1)")
    parser.add_argument("--dm-user", "--dc-user", dest="dc_user", metavar="DM_USER", default="admin", help="Data Marketplace user (default: admin)")
    parser.add_argument("--dm-password", "--dc-password", dest="dc_password", metavar="DM_PASSWORD", default="admin", help="Data Marketplace password (default: admin)")
    parser.add_argument("--no-logs", action="store_true", help="Output logs to console instead of files (interactive mode only)")
    parser.add_argument("--max-log-size", type=int, default=1, help="Maximum log file size in MB before rotation (default: 1)")
    parser.add_argument("--max-log-files", type=int, default=None, help="Maximum number of log files kept per application; the oldest are deleted (default: AI_SDK_LOG_MAX_FILES / CHATBOT_LOG_MAX_FILES env vars, else 5)")
    parser.add_argument("--production", action="store_true", help="Run in production mode")
    parser.add_argument("--background", action="store_true", help="Run processes in the background and exit after they start.")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO"], default="INFO", help="Set the logging level (default: INFO)")
    parser.add_argument("--mcp", nargs="?", const="remote", choices=["remote"], help="Enable remote MCP server via HTTP")
    _demo = parser.add_mutually_exclusive_group()
    _demo.add_argument("--load-demo", action="store_true", help="Load demo data (only with mode 'both'). Prompts before overwriting samples_bank if it exists.")
    _demo.add_argument("--load-demo-overwrite", action="store_true", help="Load demo data (only with mode 'both') and drop existing samples_bank without prompting. For non-interactive runs. Cannot be combined with --load-demo.")
    args = parser.parse_args()
    if args.mode is None and not (args.migrate_only or args.migrate_only_and_force):
        parser.error("mode is required unless --migrate-only or --migrate-only-and-force is set")
    return args


if __name__ == "__main__":
    args = parse_arguments()
    exit_code = 0

    force_migration = args.migrate_force or args.migrate_only_and_force
    exit_after_migration = args.migrate_only or args.migrate_only_and_force
    if args.migrate or args.migrate_only or force_migration:
        migrated = run_migration_tool(force=force_migration)
        if exit_after_migration or (force_migration and not migrated):
            sys.exit(0 if migrated else 1)
        console.print("[dim]Continuing with startup...[/dim]\n")

    processes_to_run = []
    processes = []
    log_threads = []

    print_header()

    # The API configuration is listed first so that its values win when both
    # files define the same variable.
    config_files = []
    chatbot_env_path = resolve_chatbot_env_path()
    if args.mode in ["api", "both"]:
        config_files.append('api/utils/sdk_config.env')
    if args.mode in ["sample_chatbot", "both"]:
        config_files.append(chatbot_env_path)

    if args.mode == "both":
        dir_api = dotenv_values('api/utils/sdk_config.env').get("AI_SDK_DATA_DIR")
        dir_chat = dotenv_values(chatbot_env_path).get("AI_SDK_DATA_DIR")

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

    for config_file in config_files:
        if os.path.exists(config_file):
            load_dotenv(config_file)
        else:
            console.print(f"[yellow]Warning:[/] Environment file {config_file} not found.")

    DATA_DIR = validate_data_dir()

    startup_warnings = []
    if not is_in_venv():
        startup_warnings.append(
            "[bold]Not running in virtual environment[/]. "
            "The AI SDK was executed outside a virtual environment. "
            "Please be aware that this may cause dependency conflicts. "
            "You can ignore this warning if using a Denodo-provided image of the AI SDK."
        )
    if args.mode in ["sample_chatbot", "both"] and chatbot_env_startup_notice():
        startup_warnings.append(
            f"[bold]{LEGACY_ENV_WARNING_TITLE}[/]. {LEGACY_ENV_WARNING_DETAIL}"
        )
    if startup_warnings:
        warning_lines = "\n\n".join(f"- {item}" for item in startup_warnings)
        console.print(Panel(
            warning_lines,
            title="[bold]Warnings",
            border_style="yellow",
            width=PANEL_WIDTH
        ))

    os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "true"

    # Set the tiktoken cache dir to be able to use the AI SDK in offline environments
    # The tiktoken dependency tries to download from the Internet the tokenizer model for the LLM if not
    # Comment out if you're fine with this behavior
    os.environ["TIKTOKEN_CACHE_DIR"] = os.path.join(get_api_data_dir(), "cache", "tiktoken")

    # Configure MCP mode if enabled
    if args.mcp == "remote":
        os.environ["AI_SDK_MCP_MODE"] = "remote"
        console.print(Panel(
            "[bold green]Remote MCP Server with HTTP[/]\n"
            "[white]MCP accessible at:[/]\n"
            "[white]- /mcp[/]\n"
            "[white]- /database/{database_name}/mcp[/]\n"
            "[white]- /tag/{tag_name}/mcp[/]\n"
            "[white]- /space/{space_name}/mcp[/]",
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

        # Spawn all subprocesses concurrently so the API and the sample
        # chatbot can warm up in parallel
        specs = spawn_services(processes_to_run, args)
        succeeded, failed = wait_for_services(specs, args)

        display_name = {"api": "API", "sample_chatbot": "chatbot"}
        for process_name, spec in succeeded:
            processes.append((display_name.get(process_name, process_name), spec["process"]))
            if spec["log_thread"] is not None:
                log_threads.append(spec["log_thread"])

        if failed:
            for process_name, _spec in failed:
                service_display_name = get_service_name(process_name)
                if process_name == "api":
                    log_dir = os.path.join(get_api_data_dir(), "logs")
                else:
                    log_dir = os.path.join(get_chatbot_data_dir(), "logs")
                log_file_path = os.path.join(log_dir, f"{process_name}_<YYYYMMDD_HHMMSS>.log")
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

            failed_types = {name for name, _ in failed}
            for spec in specs:
                if spec["process_type"] not in failed_types:
                    if spec["log_thread"] is not None and spec["log_thread"] not in log_threads:
                        log_threads.append(spec["log_thread"])
                    if not any(p[1] == spec["process"] for p in processes):
                        processes.append((display_name.get(spec["process_type"], spec["process_type"]), spec["process"]))

            abort_sibling_services(processes_to_run, failed_types, processes)
            console.print("\n[bold red]Startup aborted due to failures.[/]")
            sys.exit(1)

        if args.background:
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
                    if not getattr(shutdown_gracefully, 'called', False):
                        console.print(f"[bold red]ERROR:[/] {name} process ended unexpectedly.")
                        exit_code = 1
                    processes.remove((name, process))
            time.sleep(1)

    except SystemExit as se:
        if se.code is not None:
            if isinstance(se.code, int):
                exit_code = se.code
            else:
                exit_code = 1

    except KeyboardInterrupt:
        shutdown_gracefully(processes)

    except Exception as e:
        console.print(f"[bold red]Error:[/] {e}")
        shutdown_gracefully(processes)
        exit_code = 1

    finally:
        # Cleanup for interactive mode
        if not args.background:
            for thread in log_threads:
                if thread.is_alive():
                    thread.join()

            console.print("[bold green]Shutdown complete.[/]")

        sys.exit(exit_code)
