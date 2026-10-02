"""
 Copyright (c) 2025. DENODO Technologies.
 http://www.denodo.com
 All rights reserved.

 This software is the confidential and proprietary information of DENODO
 Technologies ("Confidential Information"). You shall not disclose such
 Confidential Information and shall use it only in accordance with the terms
 of the license agreement you entered into with DENODO.
"""

import argparse
import os
import sys
import psutil

from rich.console import Console
from rich.prompt import Confirm

PROCESS_IDENTIFIERS = {
    'api': 'api.main',
    'sample_chatbot': 'sample_chatbot.main',
}

console = Console()

def _process_cwd(process):
    try:
        return process.cwd()
    except (psutil.Error, OSError):
        return "unknown"

def find_matching_processes(identifier):
    matches = []
    current_pid = os.getpid()
    for process in psutil.process_iter(['pid', 'name', 'cmdline']):
        if process.info['pid'] == current_pid:
            continue
        cmdline = process.info['cmdline']
        if cmdline and any(identifier in cmd_part for cmd_part in cmdline):
            matches.append(process)
    return matches

def terminate_process(process, service_name):
    try:
        console.print(f"[bold green]Terminating {service_name} (PID: {process.pid})...")
        process.terminate()
        process.wait(timeout=5)
        console.print(f"[bold green]{service_name} (PID: {process.pid}) stopped successfully.")
    except psutil.TimeoutExpired:
        console.print(f"[bold yellow]! {service_name} (PID: {process.pid}) did not terminate gracefully. Forcing kill...")
        process.kill()
        console.print(f"[bold green]{service_name} (PID: {process.pid}) killed.")
    except psutil.NoSuchProcess:
        console.print(f"[bold green]{service_name} (PID: {process.pid}) was already stopped during shutdown.")

def find_and_terminate_process(identifier: str, service_name: str):
    """Finds and terminates processes by an identifier in their command line."""
    try:
        matches = find_matching_processes(identifier)
    except Exception as e:
        console.print(f"[bold red]Error while searching for processes: {e}")
        return

    if not matches:
        console.print(f"[bold yellow]{service_name} service not found. It might be already stopped.\n")
        return

    console.print(f"[bold green]Found {len(matches)} {service_name} process(es):")
    for process in matches:
        cwd = _process_cwd(process)
        console.print(f"  PID {process.pid}  cwd={cwd}")
    console.print()

    if len(matches) > 1:
        if sys.stdin.isatty():
            if not Confirm.ask(f"[bold yellow]Stop all {len(matches)} {service_name} processes?[/]"):
                console.print(f"[bold red]Skipped stopping {service_name}.\n")
                return
        else:
            console.print(f"[bold yellow]Multiple {service_name} processes found; stopping all (non-interactive).")

    for process in matches:
        terminate_process(process, service_name)
    console.print()

def main():
    parser = argparse.ArgumentParser(
        description="Stops the AI SDK API, the sample chatbot, or both.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "service",
        choices=["api", "sample_chatbot", "both"],
        help="The service to stop:\n"
             "  api            - Stops only the AI SDK API.\n"
             "  sample_chatbot - Stops only the sample chatbot.\n"
             "  both           - Stops both services."
    )
    args = parser.parse_args()

    if args.service == 'both':
        print("Attempting to stop both services...")
        find_and_terminate_process(PROCESS_IDENTIFIERS['api'], 'API')
        find_and_terminate_process(PROCESS_IDENTIFIERS['sample_chatbot'], 'sample chatbot')
    elif args.service == 'api':
        find_and_terminate_process(PROCESS_IDENTIFIERS['api'], 'API')
    elif args.service == 'sample_chatbot':
        find_and_terminate_process(PROCESS_IDENTIFIERS['sample_chatbot'], 'sample chatbot')

    console.print("[bold cyan]Stop script finished.")

if __name__ == "__main__":
    main()