import os
import sys
import time
import platform
import threading
import subprocess
import requests
import urllib3
from rich.console import Console
from utils.utils import normalize_root_path
from utils.version import AI_SDK_VERSION
from utils.yaml.validate_and_parse import load_and_validate_agents
from utils.runner_display import print_status

console = Console()

# The readiness probe targets the service on loopback, so a self-signed
# certificate is the norm rather than a problem worth warning about.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def spawn_services(process_types, args):
    """
    Spawn one subprocess per process_type in quick succession (no waiting)
    so both API and chatbot can warm up concurrently. Returns the list of
    spec dicts which can be passed to `wait_for_services`.
    """
    return [_spawn_service(p, args) for p in process_types]

def wait_for_services(specs, args):
    """
    Wait for every spawned service to answer its /health endpoint.
    Returns (succeeded, failed) lists of (process_type, spec) tuples.

    The timeout budget is shared across all services from a single wall-clock
    deadline: services that boot quickly do not eat into the budget of
    slower siblings.
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
            )
            succeeded.append((spec["process_type"], spec))
        else:
            spec["process"].kill()
            if spec["log_thread"] is not None:
                spec["log_thread"].join()
            failed.append((spec["process_type"], spec))
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

def _spawn_service(process_type, args):
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'

    if args.background:
        no_logs = False
    else:
        no_logs = args.no_logs

    data_dir = env.get("AI_SDK_DATA_DIR", ".")
    log_dir = os.path.join(data_dir, "logs") if data_dir != "." else "logs"
    env['LOG_FILE_PATH'] = os.path.join(log_dir, f"{process_type}.log")
    env['LOG_MAX_SIZE_MB'] = str(args.max_log_size)
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
        HOST = os.getenv("AI_SDK_HOST")
        PORT = os.getenv("AI_SDK_PORT")
        WORKERS = os.getenv("AI_SDK_WORKERS")
        SSL_CERT = os.getenv("AI_SDK_SSL_CERT")
        SSL_KEY = os.getenv("AI_SDK_SSL_KEY")
        TIMEOUT = os.getenv("AI_SDK_TIMEOUT")
        ROOT_PATH = normalize_root_path(os.getenv("AI_SDK_ROOT_PATH") or "")

    elif process_type == "sample_chatbot":
        HOST = os.getenv("CHATBOT_HOST")
        PORT = os.getenv("CHATBOT_PORT")
        WORKERS = os.getenv("CHATBOT_WORKERS")
        SSL_CERT = os.getenv("CHATBOT_SSL_CERT")
        SSL_KEY = os.getenv("CHATBOT_SSL_KEY")
        TIMEOUT = os.getenv("CHATBOT_TIMEOUT")
        ROOT_PATH = normalize_root_path(os.getenv("CHATBOT_ROOT_PATH") or "")

    display_url, health_url = _build_service_urls(HOST, PORT, ROOT_PATH, bool(SSL_CERT and SSL_KEY))

    imported_agent_names = []
    if process_type == "sample_chatbot":
        imported_agent_names = [
            agent_config.get("name") or agent_config.get("id", "Unnamed agent")
            for agent_config in load_and_validate_agents()
        ]

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
    }

def log_output(process):
    """
    Echo the service's output to the console. Only used with `--no-logs`.
    """
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
