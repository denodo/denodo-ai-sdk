import os
import re
import sys
import platform
import threading
import subprocess
from rich.panel import Panel
from rich.console import Console
from dotenv import dotenv_values
from utils.utils import normalize_root_path
from utils.runner_display import print_status, PANEL_WIDTH

console = Console()

def run_process(process_type, args):
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'

    if args.background:
        no_logs = False
    else:
        no_logs = args.no_logs

    env['LOG_FILE_PATH'] = os.path.join("logs", f"{process_type}.log")
    env['LOG_MAX_SIZE_MB'] = str(args.max_log_size)
    env['NO_LOGS_TO_FILE'] = str(no_logs)
    env['LOG_LEVEL'] = args.log_level

    if process_type == "api":
        if os.path.exists("api/utils/sdk_config.env"):
            sdk_vars = dotenv_values("api/utils/sdk_config.env")
        else:
            console.print("[yellow]Warning:[/] Environment file api/utils/sdk_config.env not found.")
            sdk_vars = {}

        HOST = sdk_vars.get("AI_SDK_HOST") or os.getenv("AI_SDK_HOST", "0.0.0.0")
        PORT = sdk_vars.get("AI_SDK_PORT") or os.getenv("AI_SDK_PORT", "8008")
        WORKERS = sdk_vars.get("AI_SDK_WORKERS") or os.getenv("AI_SDK_WORKERS", "1")
        SSL_CERT = sdk_vars.get("AI_SDK_SSL_CERT") or os.getenv("AI_SDK_SSL_CERT")
        SSL_KEY = sdk_vars.get("AI_SDK_SSL_KEY") or os.getenv("AI_SDK_SSL_KEY")
        TIMEOUT = sdk_vars.get("AI_SDK_TIMEOUT") or os.getenv("AI_SDK_TIMEOUT", "1200")

        root_path_value = sdk_vars.get("AI_SDK_ROOT_PATH") or os.getenv("AI_SDK_ROOT_PATH")
        ROOT_PATH = normalize_root_path(root_path_value or "")

    elif process_type == "sample_chatbot":
        if os.path.exists("sample_chatbot/chatbot_config.env"):
            chatbot_vars = dotenv_values("sample_chatbot/chatbot_config.env")
        else:
            console.print("[yellow]Warning:[/] Environment file sample_chatbot/chatbot_config.env not found.")
            chatbot_vars = {}

        HOST = chatbot_vars.get("CHATBOT_HOST") or os.getenv("CHATBOT_HOST", "0.0.0.0")
        PORT = chatbot_vars.get("CHATBOT_PORT") or os.getenv("CHATBOT_PORT", "9992")
        WORKERS = chatbot_vars.get("CHATBOT_WORKERS") or os.getenv("CHATBOT_WORKERS", "1")
        SSL_CERT = chatbot_vars.get("CHATBOT_SSL_CERT") or os.getenv("CHATBOT_SSL_CERT")
        SSL_KEY = chatbot_vars.get("CHATBOT_SSL_KEY") or os.getenv("CHATBOT_SSL_KEY")
        TIMEOUT = chatbot_vars.get("CHATBOT_TIMEOUT") or os.getenv("CHATBOT_TIMEOUT", "1200")

        root_path_value = chatbot_vars.get("CHATBOT_ROOT_PATH") or os.getenv("CHATBOT_ROOT_PATH")
        ROOT_PATH = normalize_root_path(root_path_value or "")

    success_event = threading.Event()

    with console.status(f"[bold blue]Starting {process_type}...", spinner="dots"):
        if args.production:
            venv_path = sys.prefix
            app_target = f"{process_type}.main:app"
            cmd = []

            if platform.system() == "Windows":
                if process_type == "sample_chatbot":
                    # Flask WSGI app (sample_chatbot)
                    waitress_path = os.path.join(venv_path, "Scripts", "waitress-serve.exe")
                    cmd = [waitress_path, f"--host={HOST}", f"--port={PORT}", f"--threads={WORKERS}", app_target]
                else:
                    # ASGI app (api)
                    uvicorn_path = os.path.join(venv_path, "Scripts", "uvicorn.exe")
                    cmd = [uvicorn_path, app_target, "--host", HOST, "--port", PORT, "--workers", WORKERS]
                    if SSL_CERT and SSL_KEY:
                        cmd.extend(["--ssl-certfile", SSL_CERT, "--ssl-keyfile", SSL_KEY])

            else:
                gunicorn_path = os.path.join(venv_path, "bin", "gunicorn")
                cmd = [gunicorn_path, app_target, "--workers", WORKERS, "--bind", f"{HOST}:{PORT}"]
                cmd.extend(["--timeout", TIMEOUT, "--graceful-timeout", TIMEOUT])

                cmd.extend(["--access-logfile", "-", "--error-logfile", "-"])

                if process_type == "api":
                    cmd.extend(["--worker-class", "uvicorn.workers.UvicornWorker"])

                if SSL_CERT and SSL_KEY:
                    cmd.extend(["--certfile", SSL_CERT, "--keyfile", SSL_KEY])
        else:
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
        args=(process, process_type, success_event, args.production, ROOT_PATH, no_logs)
    )

    if args.background:
        log_thread.daemon = True

    log_thread.start()

    if not success_event.wait(args.timeout):
        process.kill()
        log_thread.join()
        raise TimeoutError(f"{process_type} failed to start within {args.timeout} seconds")

    return process, log_thread

def log_output(process, process_type, success_event, production=False, root_path_prefix="", print_to_console=False):
    urls = []
    version = None
    data_catalog_warning_shown = False

    try:
        for line in process.stdout:
            if print_to_console:
                sys.stdout.write(line)
                sys.stdout.flush()

            if (process_type == "api" and
                    not data_catalog_warning_shown and
                    "Could not establish connection to Data Catalog" in line):
                console.print(Panel(
                    "[bold yellow]WARNING: Data Catalog Connection Failed[/]\n"
                    "[yellow]Could not establish connection to Data Catalog. Please check your configuration.",
                    border_style="yellow",
                    width=PANEL_WIDTH
                ))
                data_catalog_warning_shown = True

            if process_type == "api":
                if "AI SDK Version" in line:
                    version_match = re.search(r"Version:\s(.*)", line)
                    if version_match:
                        version = version_match.group(1)

                if "Uvicorn running on" in line or "Listening at:" in line:
                    match = re.search(r"(https?://[\w.:]+)", line)
                    if match:
                        urls.append(match.group(1))
                        print_status("api", urls, version, root_path_prefix=root_path_prefix)
                        success_event.set()

            elif process_type == "sample_chatbot":
                # Waitress: "Serving on http://0.0.0.0:9992"
                # Flask Dev: "Running on http://127.0.0.1:9992"
                # Uvicorn: "Uvicorn running on http://0.0.0.0:9992"
                # Gunicorn: "Listening at: http://0.0.0.0:9992"
                if "Serving on" in line or "Running on" in line or "Listening at:" in line:
                    match = re.search(r"(https?://[\w.:]+)", line)
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

def shutdown_gracefully(processes_to_shutdown, timeout=5):
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
    while True:
        try:
            command = input()
            if command.strip().lower() == 'exit':
                shutdown_gracefully(processes_to_shutdown)
                break
        except (EOFError, KeyboardInterrupt):
            shutdown_gracefully(processes_to_shutdown)
            break