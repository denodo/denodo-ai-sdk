import sys
import requests
from rich.panel import Panel
from rich.console import Console
from rich.prompt import Confirm
from utils.runner_display import PANEL_WIDTH

console = Console()

def split_vql_statements(script):
    """
    Split a VQL script into individual statements.

    Statements end at semicolons. Semicolons inside single-quoted literals (e.g.
    DESCRIPTION = '...') do not count, so prose can safely contain ';'. Inside a
    string, a doubled quote '' is one escaped quote, same as SQL.
    """
    statements = []
    current = []
    position = 0
    length = len(script)
    inside_single_quoted_string = False

    def emit_current_statement_if_any():
        text = "".join(current).strip()
        current.clear()
        if text:
            statements.append(text)

    while position < length:
        char = script[position]

        if not inside_single_quoted_string:
            if char == "'":
                inside_single_quoted_string = True
                current.append(char)
            elif char == ";":
                emit_current_statement_if_any()
            else:
                current.append(char)
            position += 1
            continue

        # We are inside '...' — copy every character until the string ends.
        current.append(char)
        if char == "'" and position + 1 < length and script[position + 1] == "'":
            current.append(script[position + 1])
            position += 2
        elif char == "'":
            inside_single_quoted_string = False
            position += 1
        else:
            position += 1

    emit_current_statement_if_any()
    return statements

def _check_database_exists(cursor, database_name):
    """Return True if database exists."""
    cursor.execute("CALL GET_DATABASES();")
    databases = cursor.fetchall()
    for db in databases:
        if db[1] == database_name:
            return True
    return False

def _reconnect_admin(cursor):
    cursor.execute("CONNECT DATABASE admin;")
    cursor.fetchall()

def _samples_bank_exists_and_prompt_overwrite(cursor, demo_overwrite=False):
    """
    If samples_bank exists, return to admin, ask to drop (unless demo_overwrite), and run DROP when confirmed.
    Returns False if the user declines.
    """
    if not _check_database_exists(cursor, "samples_bank"):
        console.print("[dim]   samples_bank not found — VQL will create it.[/]")
        return True

    console.print("[dim]   samples_bank detected …[/]")
    _reconnect_admin(cursor)

    if demo_overwrite:
        proceed = True
        console.print("[dim]   [--load-demo-overwrite] Dropping existing samples_bank …[/]")
    elif sys.stdin.isatty():
        console.print("[yellow]   Confirmation required (existing samples_bank).[/]")
        proceed = Confirm.ask(
            "[bold yellow]VDB [cyan]samples_bank[/cyan] already exists. "
            "Loading the demo will [bold]drop and recreate[/bold] it. Any changes made to samples_bank will be lost. Continue?[/]",
            default=False,
        )
    else:
        console.print(
            "[bold red]samples_bank[/] exists. Refusing to drop without confirmation "
            "(stdin is not a TTY). Use [cyan]--load-demo-overwrite[/] to drop non-interactively, "
            "or run from a terminal for a prompt."
        )
        return False

    if not proceed:
        console.print("[dim]Demo load cancelled (existing samples_bank left unchanged).[/]")
        return False

    console.print("[dim]   Executing DROP DATABASE IF EXISTS samples_bank CASCADE …[/]")
    cursor.execute("DROP DATABASE IF EXISTS samples_bank CASCADE;")
    cursor.fetchall()
    console.print("[dim]   Drop finished.[/]")
    return True

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
        response = requests.post(full_url, headers=headers, json=payload, auth=(dc_user, dc_password), timeout=120)
        response.raise_for_status()
        console.print("[bold green]✓[/] Database synchronization successful.")
        return True
    except Exception as e:
        console.print(f"[bold red]Error:[/] Error synchronizing database: {e}")
        return False

def _vql_statement_preview(statement, max_len=100):
    one_line = " ".join(statement.strip().split())
    if len(one_line) > max_len:
        return one_line[: max_len - 3] + "..."
    return one_line

def load_demo_data(host, grpc_port, catalog_port, server_id, dc_user, dc_password, demo_overwrite=False):
    console.print(Panel(
        "[bold blue]Demo Data Loading",
        border_style="blue",
        width=PANEL_WIDTH
    ))

    from adbc_driver_flightsql.dbapi import connect
    success = False
    try:
        console.print(f"[bold cyan]Step 1/5[/] Opening Flight SQL connection [dim]grpc://{host}:{grpc_port}[/] …")
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
        console.print("[bold green]   ✓[/] Connected.")

        with conn.cursor() as cur:
            console.print("[bold cyan]Step 2/5[/] METADATA ENCRYPTION PASSWORD (session) …")
            cur.execute("METADATA ENCRYPTION PASSWORD 'denodo';")
            cur.fetchall()
            console.print("[bold green]   ✓[/] Metadata encryption applied.")

            console.print("[bold cyan]Step 3/5[/] Existing [cyan]samples_bank[/] check / overwrite …")
            if not _samples_bank_exists_and_prompt_overwrite(cur, demo_overwrite=demo_overwrite):
                return False
            console.print("[bold green]   ✓[/] Overwrite step done (or skipped).")

            console.print("[bold cyan]Step 4/5[/] Executing [cyan]samples_bank.vql[/] …")
            with open('sample_chatbot/sample_data/structured/samples_bank.vql', encoding='utf-8') as f:
                vql_text = f.read()
            statements = [s for s in split_vql_statements(vql_text) if s.strip()]
            total = len(statements)
            console.print(f"[dim]   {total} statement(s) after split.[/]")
            for idx, statement in enumerate(statements, start=1):
                preview = _vql_statement_preview(statement)
                console.print(f"[dim]   [{idx}/{total}][/] {preview}")
                cur.execute(statement.strip() + ";")
                cur.fetchall()

            console.print("[bold cyan]Step 5/5[/] METADATA ENCRYPTION DEFAULT …")
            cur.execute("METADATA ENCRYPTION DEFAULT;")
            cur.fetchall()
            console.print("[bold green]   ✓[/] Session encryption reset.")

        console.print("[bold green]✓[/] Demo data loaded successfully!")
        success = True
    except Exception as e:
        console.print(f"[bold red]Error:[/] Failed to load demo data: {str(e)}")
        return False

    if success:
        catalog_url = f"http://{host}:{catalog_port}"
        console.print(f"[bold cyan]Sync[/] Data Marketplace: [dim]{catalog_url}[/] …")
        if not sync_vdp(catalog_url, server_id, dc_user, dc_password):
            console.print("[bold yellow]Warning:[/] Data Marketplace synchronization failed.")
            return False

    return success