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
import psutil

from rich.console import Console

PROCESS_IDENTIFIERS = {
    'api': 'api.main',
    'sample_chatbot': 'sample_chatbot.main',
}

console = Console()

def find_and_terminate_process(identifier: str, service_name: str):
    """Finds and terminates a process by an identifier in its command line."""
    found_process = None
    try:
        for process in psutil.process_iter(['pid', 'name', 'cmdline']):
            if process.info['cmdline'] and any(identifier in cmd_part for cmd_part in process.info['cmdline']):
                found_process = process
                break
    except Exception as e:
        console.print(f"[bold red]Error while searching for processes: {e}")
        return

    if found_process:
        console.print(f"[bold green]Found {service_name} service (PID: {found_process.pid}). Terminating...")
        try:
            found_process.terminate()
            found_process.wait(timeout=5)
            console.print(f"[bold green]{service_name} service stopped successfully.\n")
        except psutil.TimeoutExpired:
            console.print(f"[bold yellow]! {service_name} did not terminate gracefully. Forcing kill...")
            found_process.kill()
            console.print(f"[bold green]{service_name} service killed.\n")
        except psutil.NoSuchProcess:
            console.print(f"[bold green]{service_name} service was already stopped during shutdown.\n")
    else:
        console.print(f"[bold yellow]{service_name} service not found. It might be already stopped.\n")

def main():
    parser = argparse.ArgumentParser(
        description="Stops the AI SDK API, the Sample Chatbot, or both.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "service",
        choices=["api", "sample_chatbot", "both"],
        help="The service to stop:\n"
             "  api            - Stops only the AI SDK API.\n"
             "  sample_chatbot - Stops only the Sample Chatbot.\n"
             "  both           - Stops both services."
    )
    args = parser.parse_args()

    if args.service == 'both':
        print("Attempting to stop both services...")
        find_and_terminate_process(PROCESS_IDENTIFIERS['api'], 'API')
        find_and_terminate_process(PROCESS_IDENTIFIERS['sample_chatbot'], 'Sample Chatbot')
    elif args.service == 'api':
        find_and_terminate_process(PROCESS_IDENTIFIERS['api'], 'API')
    elif args.service == 'sample_chatbot':
        find_and_terminate_process(PROCESS_IDENTIFIERS['sample_chatbot'], 'Sample Chatbot')

    console.print("[bold cyan]Stop script finished.")

if __name__ == "__main__":
    main()