import os
import sys
import time
import socket
import logging
import platform
import threading
import subprocess
import requests
from datetime import datetime
import urllib3
from rich.console import Console
from utils.utils import normalize_root_path, get_api_data_dir, get_chatbot_data_dir
from utils.version import AI_SDK_VERSION
from utils.yaml.validate_and_parse import load_and_validate_agents
from utils.runner_display import print_status
from api.mcp.spaces import load_spaces

console = Console()

SERVICE_NAMES = {
    "api": "AI SDK",
    "sample_chatbot": "Sample chatbot",
}

def get_service_name(process_type):
    return SERVICE_NAMES.get(process_type, process_type)

def abort_sibling_services(requested_types, failed_types, running_processes, log_threads=None):
    """
    Notify and stop any sibling services when a companion service fails to start.
    """
    stopped_types = [p for p in requested_types if p not in failed_types]
    if stopped_types:
        stopped = ", ".join(get_service_name(p) for p in stopped_types)
        failed = ", ".join(get_service_name(p) for p in failed_types)
        console.print(f"\n[yellow]Stopping {stopped} because {failed} failed to start.[/]")

    if running_processes:
        shutdown_gracefully(running_processes)
        running_processes.clear()

    for thread in log_threads or []:
        if thread.is_alive():
            thread.join()

# The readiness probe targets the service on loopback, so a self-signed
# certificate is the norm rather than a problem worth warning about.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def spawn_services(process_types, args):
    """
    Spawn one subprocess per process_type in quick succession (no waiting)
    so both API and chatbot can warm up concurrently. Returns the list of
    spec dicts which can be passed to `wait_for_services`.
    """
    specs = []
    for p in process_types:
        spec = _spawn_service(p, args)
        if spec is not None:
            specs.append(spec)

    if len(specs) != len(process_types):
        started_types = {s["process_type"] for s in specs}
        failed_types = [p for p in process_types if p not in started_types]
        running = [(s["process_type"], s["process"]) for s in specs]
        threads = [s["log_thread"] for s in specs if s["log_thread"] is not None]

        abort_sibling_services(process_types, failed_types, running, threads)
        console.print("\n[bold red]Startup aborted due to failures.[/]")
        sys.exit(1)

    return specs

def wait_for_services(specs, args):
    """
    Wait for every spawned service to answer its /health endpoint.
    Returns (succeeded, failed) lists of (process_type, spec) tuples.

    The timeout budget is shared across all services from a single wall-clock
    deadline: services that boot quickly do not eat into the budget of
    slower siblings. If any service fails, checking stops immediately so the
    caller can gracefully shut down all sibling processes together.
    """
    succeeded = []
    failed = []
    deadline = time.monotonic() + args.timeout
    for spec in specs:
        if _wait_until_healthy(spec, deadline):
            print_status(
                spec["process_type"],
                [spec["display_url"]],
                AI_SDK_VERSION if spec["process_type"] == "api" else None,
                root_path_prefix=spec["root_path"],
                imported_agent_names=spec["imported_agent_names"],
                imported_space_names=spec["imported_space_names"],
                imported_skills=spec.get("imported_skills"),
            )
            succeeded.append((spec["process_type"], spec))
        else:
            spec["process"].kill()
            if spec["log_thread"] is not None:
                spec["log_thread"].join()
            failed.append((spec["process_type"], spec))
            break

    return succeeded, failed

def _wait_until_healthy(spec, deadline):
    """
    Poll the service's /health endpoint until it answers with 200, the service
    dies, or the shared deadline elapses.
    """
    while time.monotonic() < deadline:
        if spec["process"].poll() is not None:
            return False

        remaining = deadline - time.monotonic()
        try:
            response = requests.get(
                spec["health_url"],
                verify=False, # noqa: S501
                timeout=max(0.5, min(2.0, remaining)),
            )
            if response.status_code == 200:
                return True
        except requests.RequestException:
            pass

        time.sleep(min(0.5, max(0.0, deadline - time.monotonic())))
    return False

def _build_service_urls(host, port, root_path, ssl_enabled):
    """
    Return the URL shown to the user and the /health URL run.py polls.
    """
    scheme = "https" if ssl_enabled else "http"
    display_url = f"{scheme}://{host}:{port}"

    probe_host = {"0.0.0.0": "127.0.0.1", "::": "::1"}.get(host, host)
    if ":" in probe_host:
        probe_host = f"[{probe_host}]"

    return display_url, f"{scheme}://{probe_host}:{port}{root_path}/health"

def _port_is_free(host, port):
    family = socket.AF_INET6 if host and ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        if family == socket.AF_INET6:
            sock.bind((host, int(port), 0, 0))
        else:
            sock.bind((host, int(port)))
        return True
    except OSError:
        return False
    finally:
        sock.close()

def _spawn_service(process_type, args):
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'

    if args.background:
        no_logs = False
    else:
        no_logs = args.no_logs

    if process_type == "api":
        log_dir = os.path.join(get_api_data_dir(), "logs")
    elif process_type == "sample_chatbot":
        log_dir = os.path.join(get_chatbot_data_dir(), "logs")
    else:
        log_dir = os.path.join(env.get("AI_SDK_DATA_DIR", "data/"), "logs")
    env['LOG_FILE_PATH'] = os.path.join(log_dir, f"{process_type}.log")
    # One session id per launch: every worker of the service appends to the
    # same <service>_<session id>.log file instead of creating its own.
    env['LOG_SESSION_ID'] = datetime.now().strftime("%Y%m%d_%H%M%S")
    env['LOG_MAX_SIZE_MB'] = str(args.max_log_size)
    # --max-log-files overrides AI_SDK_LOG_MAX_FILES / CHATBOT_LOG_MAX_FILES
    if getattr(args, "max_log_files", None):
        env['AI_SDK_LOG_MAX_FILES' if process_type == "api" else 'CHATBOT_LOG_MAX_FILES'] = str(args.max_log_files)
    env['NO_LOGS_TO_FILE'] = str(no_logs)
    env['LOG_LEVEL'] = args.log_level

    # When run.py is launching the chatbot alongside the API (`mode == both`),
    # hand the chatbot the same startup budget that run.py uses for its own
    # `success_event.wait` so the chatbot's end-of-startup AI SDK probe keeps
    # retrying until the sibling API comes up. When the chatbot is launched
    # alone (`mode == sample_chatbot`) we use a short probe so the chatbot
    # doesn't hang for the full timeout when no API is around.
    if process_type == "sample_chatbot":
        if getattr(args, "mode", None) == "both":
            env['CHATBOT_AI_SDK_WAIT_TIMEOUT'] = str(args.timeout)
        else:
            # Solo mode: a single short probe matches the prior fast-fail
            # behavior — `requests` returns immediately on connection
            # refused, so this adds no latency when the AI SDK isn't there.
            env.setdefault('CHATBOT_AI_SDK_WAIT_TIMEOUT', '0')

    # Settings are read from the environment, which run.py has already
    # populated from the service configuration files.
    if process_type == "api":
        env_prefix = "AI_SDK"
        config_file = "sdk_config.env"
        HOST = os.getenv("AI_SDK_HOST")
        PORT = os.getenv("AI_SDK_PORT")
        WORKERS = os.getenv("AI_SDK_WORKERS")
        SSL_CERT = os.getenv("AI_SDK_SSL_CERT")
        SSL_KEY = os.getenv("AI_SDK_SSL_KEY")
        TIMEOUT = os.getenv("AI_SDK_TIMEOUT")
        ROOT_PATH = normalize_root_path(os.getenv("AI_SDK_ROOT_PATH") or "")

    elif process_type == "sample_chatbot":
        env_prefix = "CHATBOT"
        config_file = "chatbot_config.env"
        HOST = os.getenv("CHATBOT_HOST")
        PORT = os.getenv("CHATBOT_PORT")
        WORKERS = os.getenv("CHATBOT_WORKERS")
        SSL_CERT = os.getenv("CHATBOT_SSL_CERT")
        SSL_KEY = os.getenv("CHATBOT_SSL_KEY")
        TIMEOUT = os.getenv("CHATBOT_TIMEOUT")
        ROOT_PATH = normalize_root_path(os.getenv("CHATBOT_ROOT_PATH") or "")

    missing_vars = []
    if not HOST:
        missing_vars.append(f"{env_prefix}_HOST")
    if not PORT:
        missing_vars.append(f"{env_prefix}_PORT")

    if args.production:
        if not WORKERS:
            missing_vars.append(f"{env_prefix}_WORKERS")
        if platform.system() != "Windows" and not TIMEOUT:
            missing_vars.append(f"{env_prefix}_TIMEOUT")

    if missing_vars:
        console.print(
            f"\n[bold red]ERROR:[/] Missing required environment variables for [bold]{process_type}[/].\n"
            f"Please ensure the following variables are set and uncommented in your [cyan]{config_file}[/] file:\n"
            f"[yellow]{', '.join(missing_vars)}[/]\n"
        )
        return None

    if not _port_is_free(HOST, PORT):
        console.print(
            f"[bold red]ERROR:[/] Port {PORT} on {HOST} is already in use ({process_type}).\n"
            f"Stop the existing service first: [cyan]python stop.py {process_type}[/]\n"
        )
        return None

    display_url, health_url = _build_service_urls(HOST, PORT, ROOT_PATH, bool(SSL_CERT and SSL_KEY))

    imported_agent_names = []
    imported_space_names = []
    imported_skills = []
    # Collect status entries silently in the parent runner process; the
    # spawned service subprocesses emit the validation logs to their log
    # files (or to the console when `--no-logs` is active).
    logging.disable(logging.CRITICAL)
    try:
        if process_type == "sample_chatbot":
            load_and_validate_agents(report=imported_agent_names)
            try:
                from sample_chatbot.engine.skills import load_skills_report
                load_skills_report(report=imported_skills)
            except Exception:  # noqa: S110
                pass
        elif process_type == "api":
            load_spaces(report=imported_space_names)
    finally:
        logging.disable(logging.NOTSET)

    with console.status(f"[bold blue]Starting {process_type}...", spinner="dots"):
        if args.production:
            app_target = f"{process_type}.main:app"
            cmd = []

            if platform.system() == "Windows":
                if process_type == "sample_chatbot":
                    # Flask WSGI app (sample_chatbot) - Waitress
                    cmd = [
                        sys.executable, "-m", "waitress",
                        f"--host={HOST}",
                        f"--port={PORT}",
                        f"--threads={WORKERS}",
                        app_target
                    ]
                else:
                    # ASGI app (api) - Uvicorn
                    cmd = [
                        sys.executable, "-m", "uvicorn",
                        app_target,
                        "--host", HOST,
                        "--port", PORT,
                        "--workers", WORKERS
                    ]
                    if SSL_CERT and SSL_KEY:
                        cmd.extend(["--ssl-certfile", SSL_CERT, "--ssl-keyfile", SSL_KEY])

            else:
                # Linux / Docker - Gunicorn
                cmd = [
                    sys.executable, "-m", "gunicorn",
                    app_target,
                    "--workers", WORKERS,
                    "--bind", f"{HOST}:{PORT}"
                ]
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
            stdout=subprocess.PIPE if no_logs else subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=env
        )

    log_thread = None
    if no_logs:
        log_thread = threading.Thread(target=log_output, args=(process,))
        log_thread.start()

    return {
        "process_type": process_type,
        "process": process,
        "log_thread": log_thread,
        "display_url": display_url,
        "health_url": health_url,
        "root_path": ROOT_PATH,
        "imported_agent_names": imported_agent_names,
        "imported_space_names": imported_space_names,
        "imported_skills": imported_skills,
    }

def log_output(process):
    """Echo the service's output to the console. Only used with `--no-logs`."""
    try:
        for line in process.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()

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
            killed_with_taskkill = False

            if platform.system() == "Windows":
                system_root = os.environ.get("SystemRoot", "C:\\Windows")
                taskkill_path = os.path.join(system_root, "System32", "taskkill.exe")

                if os.path.exists(taskkill_path):
                    subprocess.run( # noqa: S603
                        [taskkill_path, '/F', '/T', '/PID', str(process.pid)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False
                    )
                    killed_with_taskkill = True
                else:
                    console.print("[yellow]Warning: expected system path to taskkill.exe not found. Using internal terminate.[/]")

            if not killed_with_taskkill:
                process.terminate()
                try:
                    process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    console.print(f"[red]Force killing {name} process...[/]")
                    process.kill()
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        pass

            if process.stdout:
                try:
                    process.stdout.close()
                except Exception: # noqa: S110
                    pass
            if process.stderr:
                try:
                    process.stderr.close()
                except Exception: # noqa: S110
                    pass

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
