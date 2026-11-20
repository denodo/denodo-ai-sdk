"""
Windows service wrapper for the Denodo AI SDK.

Usage (from an elevated prompt):
    python service.py --startup auto install
    python service.py start
    python service.py stop
    python service.py remove
    python service.py debug
    python service.py console
"""

import contextlib
import datetime
import glob
import logging
from logging.handlers import RotatingFileHandler
import os
import subprocess
import sys
import threading
import traceback

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "service.env")


def _get_early_env(key, default=None):
    """Read *key* from the environment or service.env (before CONFIG is available)."""
    val = os.environ.get(key)
    if not val and os.path.exists(ENV_FILE):
        with contextlib.suppress(Exception):
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        if k.strip() == key:
                            val = v
                            break
    if val:
        return val.strip().strip('"').strip("'")
    return default


_raw_data_dir = _get_early_env("AI_SDK_DATA_DIR", "data/")
if os.path.isabs(_raw_data_dir):
    DATA_DIR = _raw_data_dir
else:
    DATA_DIR = os.path.join(PROJECT_ROOT, _raw_data_dir)

LOGS_DIR = os.path.join(DATA_DIR, "windows_service", "logs")
SYSTEM_ROOT = os.environ.get("SystemRoot", r"C:\Windows")
TASKKILL_EXE = os.path.join(SYSTEM_ROOT, "System32", "taskkill.exe")
CUSTOM_VENV_DIR = _get_early_env("DENODO_AI_SDK_SERVICE_VENV_DIR")


def _bootstrap_venv_paths():
    """pythonservice.exe runs on the base interpreter and does not know about
    the virtual environment. Add the venv packages and pywin32 DLL folders to
    sys.path / PATH before importing pywin32 modules (avoids error 1053)."""
    candidates = []
    if CUSTOM_VENV_DIR:
        candidates.extend([CUSTOM_VENV_DIR, os.path.join(PROJECT_ROOT, CUSTOM_VENV_DIR)])
    candidates.extend([os.path.join(PROJECT_ROOT, "venv"), os.path.join(PROJECT_ROOT, ".venv"), sys.prefix])

    for venv in candidates:
        site = os.path.join(venv, "Lib", "site-packages")
        if not os.path.isdir(site):
            continue

        extra = [
            site,
            os.path.join(site, "win32"),
            os.path.join(site, "win32", "lib"),
            os.path.join(site, "Pythonwin"),
        ]
        dlls = [os.path.join(site, "pywin32_system32"), os.path.join(site, "win32"), venv]

        for p in extra:
            if os.path.isdir(p) and p not in sys.path:
                sys.path.append(p)

        for d in dlls:
            if os.path.isdir(d):
                os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
                if hasattr(os, "add_dll_directory"):
                    with contextlib.suppress(OSError):
                        os.add_dll_directory(d)
        break


_bootstrap_venv_paths()

import servicemanager  # noqa: E402
import win32event  # noqa: E402
import win32service  # noqa: E402
import win32serviceutil  # noqa: E402
from dotenv import dotenv_values  # noqa: E402

CONFIG = dotenv_values(ENV_FILE) if os.path.exists(ENV_FILE) else {}


def get_config_val(key, default=""):
    """Retrieve config value sanitized of surrounding quotes and whitespace."""
    val = CONFIG.get(key) or os.environ.get(key, default)
    if isinstance(val, str):
        return val.strip().strip('"').strip("'")
    return val


def is_truthy(val):
    return str(val).strip().lower() in ("1", "true", "yes")


def get_python_executable():
    """Locate the actual python.exe interpreter inside the virtual environment."""
    if sys.prefix != sys.base_prefix:
        return sys.executable

    venv_python = os.path.join(sys.prefix, "Scripts", "python.exe")
    if os.path.exists(venv_python):
        return venv_python

    candidates = []
    if CUSTOM_VENV_DIR:
        candidates.extend([
            os.path.join(CUSTOM_VENV_DIR, "Scripts", "python.exe"),
            os.path.join(PROJECT_ROOT, CUSTOM_VENV_DIR, "Scripts", "python.exe"),
        ])

    candidates.extend([
        os.path.join(PROJECT_ROOT, "venv", "Scripts", "python.exe"),
        os.path.join(PROJECT_ROOT, ".venv", "Scripts", "python.exe"),
    ])

    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    return sys.executable


def build_service_arguments():
    """Construct argument list for run.py from service configuration."""
    mode = get_config_val("DENODO_AI_SDK_SERVICE_MODE", "both")
    args = [mode, "--production"]

    if is_truthy(get_config_val("DENODO_AI_SDK_SERVICE_MCP", "0")):
        args.extend(["--mcp", "remote"])

    mappings = [
        ("DENODO_AI_SDK_SERVICE_LOG_LEVEL", "--log-level"),
        ("DENODO_AI_SDK_SERVICE_TIMEOUT", "--timeout"),
        ("DENODO_AI_SDK_SERVICE_MAX_LOG_SIZE", "--max-log-size"),
        ("DENODO_AI_SDK_SERVICE_MAX_LOG_FILES", "--max-log-files"),
    ]

    for env_var, flag in mappings:
        val = get_config_val(env_var)
        if val:
            args.extend([flag, str(val)])

    return args


def _pump_to_rotating_log(stream, path, max_bytes, backups):
    """Copy subprocess stream into a size-rotated log file."""
    handler = RotatingFileHandler(path, maxBytes=max_bytes, backupCount=backups, encoding="utf-8")
    handler.terminator = "\n"
    try:
        for raw in iter(stream.readline, b""):
            text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            handler.emit(logging.makeLogRecord({"msg": text, "levelno": logging.INFO}))
    except Exception as exc:
        servicemanager.LogWarningMsg(f"Error pumping logs to {path}: {exc}")
    finally:
        handler.close()


class DenodoAISDKService(win32serviceutil.ServiceFramework):
    _exe_name_ = getattr(sys, "_base_executable", sys.executable)
    _exe_args_ = f'"{os.path.abspath(__file__)}"'
    _svc_name_ = "DenodoAISDK"
    _svc_display_name_ = "Denodo AI SDK"
    _svc_description_ = "Denodo AI SDK and Chatbot running as a Windows service."

    def __init__(self, args):
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.process = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING, waitHint=10000)
        win32event.SetEvent(self.stop_event)
        self._terminate_process()

    def _terminate_process(self):
        if self.process is None or self.process.poll() is not None:
            return
        try:
            # Terminate the entire process tree forcefully (/F /T) to kill run.py
            # and ALL child workers (API, Chatbot) using absolute system taskkill path.
            subprocess.run(  # nosec B603 # noqa: S603
                [TASKKILL_EXE, "/PID", str(self.process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            self.process.wait(timeout=5)
        except Exception as exc:
            servicemanager.LogErrorMsg(f"Error stopping Denodo AI SDK process: {exc}")

    def SvcDoRun(self):
        try:
            self._run()
        except Exception:
            servicemanager.LogErrorMsg(traceback.format_exc())
            raise

    def _run(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )
        os.makedirs(LOGS_DIR, exist_ok=True)

        python_exe = get_python_executable()
        run_script = os.path.join(PROJECT_ROOT, "run.py")
        cmd = [python_exe, run_script] + build_service_arguments()

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        try:
            max_bytes = int(float(get_config_val("DENODO_AI_SDK_SERVICE_MAX_LOG_SIZE", 5)) * 1024 * 1024)
            backups = max(int(get_config_val("DENODO_AI_SDK_SERVICE_MAX_LOG_FILES", 5)), 1)
        except ValueError:
            max_bytes, backups = 5 * 1024 * 1024, 5

        # Purge older session files before creating the new session file
        old_logs = sorted(glob.glob(os.path.join(LOGS_DIR, "service_2*.log*")), key=os.path.getmtime, reverse=True)
        for stale in old_logs[max(backups - 1, 0):]:
            with contextlib.suppress(OSError):
                os.remove(stale)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = os.path.join(LOGS_DIR, f"service_{timestamp}.log")

        self.process = subprocess.Popen(  # nosec B603 # noqa: S603
            cmd,
            cwd=PROJECT_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        threading.Thread(
            target=_pump_to_rotating_log,
            args=(self.process.stdout, log_path, max_bytes, backups),
            daemon=True,
        ).start()

        while True:
            rc = win32event.WaitForSingleObject(self.stop_event, 1000)
            if rc == win32event.WAIT_OBJECT_0:
                break
            if self.process.poll() is not None:
                servicemanager.LogErrorMsg(
                    f"Denodo AI SDK process exited unexpectedly with code {self.process.returncode}"
                )
                break

        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STOPPED,
            (self._svc_name_, ""),
        )


def run_console():
    """Run run.py in the foreground (no SCM) to check that the SDK starts."""
    python_exe = get_python_executable()
    run_script = os.path.join(PROJECT_ROOT, "run.py")
    cmd = [python_exe, run_script] + build_service_arguments()
    print("Running:", " ".join(cmd))
    sys.exit(subprocess.call(cmd, cwd=PROJECT_ROOT))  # nosec B603 # noqa: S603


if __name__ == "__main__":
    if len(sys.argv) == 1:
        # Started by the Service Control Manager
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(DenodoAISDKService)
        servicemanager.StartServiceCtrlDispatcher()
    elif sys.argv[1].lower() == "console":
        run_console()
    else:
        win32serviceutil.HandleCommandLine(DenodoAISDKService)
