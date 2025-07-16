import os
import re
import sys
import argparse
import requests
import threading
import subprocess
import platform
import time

from rich.text import Text
from rich.panel import Panel
from rich.console import Console

from datetime import datetime
from dotenv import dotenv_values

from utils.utils import normalize_root_path

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
    return parser.parse_args()

def empty_file(file_path):
    """Create an empty file at the specified path, creating parent directories if needed."""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8'):
        pass

def print_header():
    """Display a stylized header for the application."""
    console.print(Panel(
        Text("Denodo AI SDK", style="bold white", justify="center"),
        border_style="cyan",
        padding=(1, 2),
        width=60
    ))

def print_status(process_type, urls, version=None, root_path_prefix=""):
    """Display a styled status message for running services."""

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
            width=60
        )
    else:
        # Create the text content using Text.assemble instead of append
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
            width=60
        )
    console.print(panel)

def run_process(process_type, timeout=30, no_logs=False, max_log_size=1, production=False, background=False):
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'

    if background:
        no_logs = False

    env['LOG_FILE_PATH'] = os.path.join("logs", f"{process_type}.log")
    env['LOG_MAX_SIZE_MB'] = str(max_log_size)
    env['NO_LOGS_TO_FILE'] = str(no_logs)
    
    # Load environment variables from the appropriate .env file
    if process_type == "api":
        if os.path.exists("api/utils/sdk_config.env"):
            sdk_vars = dotenv_values("api/utils/sdk_config.env")
            HOST = sdk_vars.get("AI_SDK_HOST", "0.0.0.0")
            PORT = sdk_vars.get("AI_SDK_PORT", "8008")
            WORKERS = sdk_vars.get("AI_SDK_WORKERS", "1")
            SSL_CERT = sdk_vars.get("AI_SDK_SSL_CERT", None)
            SSL_KEY = sdk_vars.get("AI_SDK_SSL_KEY", None)
            ROOT_PATH = normalize_root_path(sdk_vars.get("AI_SDK_ROOT_PATH", ""))
        else:
            console.print("[yellow]Warning:[/] Environment file api/utils/sdk_config.env not found.")
    elif process_type == "sample_chatbot":
        if os.path.exists("sample_chatbot/chatbot_config.env"):
            chatbot_vars = dotenv_values("sample_chatbot/chatbot_config.env")
            HOST = chatbot_vars.get("CHATBOT_HOST", "0.0.0.0")
            PORT = chatbot_vars.get("CHATBOT_PORT", "9992")
            WORKERS = chatbot_vars.get("CHATBOT_WORKERS", "1")
            SSL_CERT = chatbot_vars.get("CHATBOT_SSL_CERT", None)
            SSL_KEY = chatbot_vars.get("CHATBOT_SSL_KEY", None)
            ROOT_PATH = normalize_root_path(chatbot_vars.get("CHATBOT_ROOT_PATH", ""))
        else:
            console.print("[yellow]Warning:[/] Environment file sample_chatbot/chatbot_config.env not found.")
        
    success_event = threading.Event()

    with console.status(f"[bold blue]Starting {process_type}...", spinner="dots"):
        if production:            
            venv_path = sys.prefix
            gunicorn_path = os.path.join(venv_path, "bin", "gunicorn")
            uvicorn_path = os.path.join(venv_path, "Scripts", "uvicorn.exe")

            if platform.system() == "Windows":
                server_path = uvicorn_path
            else:
                server_path = gunicorn_path

            cmd = [server_path, f"{process_type}.main:app", "--workers", WORKERS]

            if server_path == uvicorn_path:
                cmd.extend(["--host", HOST, "--port", PORT])
            else:
                cmd.extend(["--bind", f"{HOST}:{PORT}"])

            if process_type == "api" and server_path == gunicorn_path:
                cmd.extend(["--worker-class", "uvicorn.workers.UvicornWorker"])
            
            if SSL_CERT and SSL_KEY:
                if server_path == uvicorn_path:
                    cmd.extend(["--ssl-certfile", SSL_CERT, "--ssl-keyfile", SSL_KEY])
                else:
                    cmd.extend(["--certfile", SSL_CERT, "--keyfile", SSL_KEY])
        else:
            # Development mode using Python module directly
            cmd = [sys.executable, "-m", f"{process_type}.main"]

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=env
        )

    log_thread = threading.Thread(
        target=log_output, 
        args=(process, process_type, success_event, production, ROOT_PATH, no_logs)
    )

    if background:
        log_thread.daemon = True

    log_thread.start()

    # Wait for success signal or timeout
    if not success_event.wait(timeout):
        process.kill()
        log_thread.join()
        console.print(f"[bold red]Error:[/] {process_type} failed to start within {timeout} seconds")
        raise TimeoutError(f"{process_type} failed to start within {timeout} seconds")
    
    return process, log_thread

def log_output(process, process_type, success_event, production=False, root_path_prefix="", print_to_console=False):
    urls = []
    version = None
    
    try:
        for line in process.stdout:
            if print_to_console:
                sys.stdout.write(line)
                sys.stdout.flush()
            
            if process_type == "api":
                if production and platform.system() != "Windows":
                    # Production mode patterns (Gunicorn)
                    if "AI SDK Version" in line:
                        version_match = re.search(r"Version:\s(.*)", line)
                        if version_match:
                            version = version_match.group(1)
                            if urls and not success_event.is_set():
                                print_status("api", urls, version, root_path_prefix=root_path_prefix)
                                success_event.set()
                    
                    if "Listening at:" in line:
                        match = re.search(r"Listening at: (https?://[\w.:]+)", line)
                        if match:
                            urls.append(match.group(1))
                            if version is not None:
                                print_status("api", urls, version, root_path_prefix=root_path_prefix)
                                success_event.set()
                            elif not success_event.is_set():
                                def delayed_status():
                                    if not success_event.is_set():
                                        print_status("api", urls, version, root_path_prefix=root_path_prefix)
                                        success_event.set()
                                t = threading.Timer(5.0, delayed_status)
                                t.daemon = True
                                t.start()
                else:
                    # Development mode patterns (Uvicorn)
                    if "AI SDK Version" in line:
                        version_match = re.search(r"Version:\s(.*)", line)
                        if version_match:
                            version = version_match.group(1)
                            if urls and not success_event.is_set():
                                print_status("api", urls, version, root_path_prefix=root_path_prefix)
                                success_event.set()
                    
                    if "Uvicorn running on" in line:
                        match = re.search(r"Uvicorn running on (https?://[\w.:]+)", line)
                        if match:
                            urls.append(match.group(1))
                            if version is not None:
                                print_status("api", urls, version, root_path_prefix=root_path_prefix)
                                success_event.set()
                            elif not success_event.is_set():
                                def delayed_status():
                                    if not success_event.is_set():
                                        print_status("api", urls, version, root_path_prefix=root_path_prefix)
                                        success_event.set()
                                t = threading.Timer(5.0, delayed_status)
                                t.daemon = True
                                t.start()
            
            elif process_type == "sample_chatbot":
                if production and platform.system() != "Windows":
                    # Production mode patterns (Gunicorn)
                    if "Listening at:" in line:
                        match = re.search(r"Listening at: (https?://[\w.:]+)", line)
                        if match:
                            urls.append(match.group(1))
                            if not success_event.is_set():
                                print_status("sample_chatbot", urls, root_path_prefix=root_path_prefix)
                                success_event.set()
                elif production and platform.system() == "Windows":
                    if "running on" in line:
                        match = re.search(r"running on (https?://[\w.:]+)", line)
                        if match:
                            urls.append(match.group(1))
                            if not success_event.is_set():
                                print_status("sample_chatbot", urls, root_path_prefix=root_path_prefix)
                                success_event.set()
                else:
                    # Development mode patterns
                    if "Running on" in line:
                        match = re.search(r"Running on (https?://[\w.:]+)", line)
                        if match:
                            urls.append(match.group(1))
                            if not success_event.is_set():
                                print_status("sample_chatbot", urls, root_path_prefix=root_path_prefix)
                                success_event.set()
                    
    except ValueError as e:
        if "I/O operation on closed file" in str(e):
            console.print("[yellow]Warning:[/] Log file was closed before all output was written.")
        else:
            raise

def sync_vdp(url, server_id = 1, dc_user = 'admin', dc_password = 'admin'):
    endpoint = "/denodo-data-catalog/public/api/element-management/VIEWS/synchronize"
    full_url = f"{url}{endpoint}?serverId={server_id}"
    
    payload = {
        "proceedWithConflicts": "SERVER",
    }

    headers = {
        'Content-Type': 'application/json'
    }

    try:
        response = requests.post(full_url, headers=headers, json=payload, auth=(dc_user, dc_password))
        response.raise_for_status()
        console.print("[bold green]✓[/] Database synchronization successful")
        return True
    except Exception as e:
        console.print(f"[bold red]Error:[/] Error synchronizing database: {e}")
        return False

def load_demo_data(host, grpc_port, catalog_port, server_id, dc_user, dc_password):
    """Load demo data with visual feedback"""
    console.print(Panel(
        "[bold blue]Demo Data Loading",
        border_style="blue",
        width=60
    ))
    
    from adbc_driver_flightsql.dbapi import connect
    console.print("[bold blue]Loading demo banking data into samples_bank VDB...")
    success = False
    try:
        with console.status("[bold blue]Loading demo data...", spinner="dots"):
            conn = connect(
                f"grpc://{host}:{grpc_port}",
                db_kwargs={
                    "username": dc_user,
                    "password": dc_password,
                    "adbc.flight.sql.rpc.call_header.database": 'admin',
                    "adbc.flight.sql.rpc.call_header.timePrecision": 'milliseconds',
                },
                autocommit=True
            )
            
            with conn.cursor() as cur:
                cur.execute("METADATA ENCRYPTION PASSWORD 'denodo';")
                cur.fetchall()
                
                with open('sample_chatbot/sample_data/structured/samples_bank.vql', 'r', encoding='utf-8') as f:
                    sql_statements = f.read().split(';')
                    for statement in sql_statements:
                        if statement.strip():
                            cur.execute(statement.strip() + ";")
                            cur.fetchall()
                            
                cur.execute("METADATA ENCRYPTION DEFAULT;")
                cur.fetchall()
            
        console.print("[bold green]✓[/] Demo data loaded successfully!")
        success = True
    except Exception as e:
        console.print(f"[bold red]Error:[/] Failed to load demo data: {str(e)}")
        return False

    if success:
        with console.status("[bold blue]Synchronizing database...", spinner="dots"):
            catalog_url = f"http://{host}:{catalog_port}"
            if not sync_vdp(catalog_url, server_id, dc_user, dc_password):
                console.print("[bold yellow]Warning:[/] Data Catalog synchronization failed.")
                return False
            console.print("[bold green]✓[/] Database synchronized successfully!")
    
    return success

def shutdown_gracefully(processes_to_shutdown, timeout=5):
    """Gracefully shuts down all running subprocesses, ensuring it only runs once."""
    if getattr(shutdown_gracefully, 'called', False):
        return
    shutdown_gracefully.called = True

    console.print("\n[bold yellow]Shutting down gracefully...[/]")
    for name, process in processes_to_shutdown:
        if process.poll() is None:
            console.print(f"[yellow]Stopping {name} process...[/]")
            process.terminate()
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                console.print(f"[red]Force killing {name} process...[/]")
                process.kill()

def command_listener(processes_to_shutdown):
    """Waits for the user to type 'exit' and then shuts down processes."""
    while True:
        try:
            command = input()
            if command.strip().lower() == 'exit':
                shutdown_gracefully(processes_to_shutdown)
                break
        except (EOFError, KeyboardInterrupt):
            shutdown_gracefully(processes_to_shutdown)
            break

if __name__ == "__main__":
    args = parse_arguments()
    processes_to_run = []
    processes = []
    log_threads = []

    print_header()
    
    # Show production mode warning if enabled
    if args.production:
        console.print(Panel(
            "[bold yellow]Production mode uses Gunicorn ASGI server on UNIX systems and Uvicorn ASGI server on Windows.",
            border_style="yellow",
            width=60
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
                process, log_thread = run_process(process_name, args.timeout, args.no_logs, args.max_log_size, args.production, args.background)
                if process_name == "api":
                    processes.append(("API", process))
                elif process_name == "sample_chatbot":
                    processes.append(("Chatbot", process))
                log_threads.append(log_thread)
            except TimeoutError as e:
                console.print(f"[bold red]Error:[/] {e}")
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
            console.print("\n[bold cyan]Type 'exit' and press Enter to stop the application(s).[/bold cyan]")
            cmd_listener_thread = threading.Thread(
                target=command_listener,
                args=(processes,),
                daemon=True
            )
            cmd_listener_thread.start()

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