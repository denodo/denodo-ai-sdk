import requests
from rich.panel import Panel
from rich.console import Console
from utils.runner_display import PANEL_WIDTH

console = Console()

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
        console.print("[bold green]✓[/] Database synchronization successful")
        return True
    except Exception as e:
        console.print(f"[bold red]Error:[/] Error synchronizing database: {e}")
        return False

def load_demo_data(host, grpc_port, catalog_port, server_id, dc_user, dc_password):
    console.print(Panel(
        "[bold blue]Demo Data Loading",
        border_style="blue",
        width=PANEL_WIDTH
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