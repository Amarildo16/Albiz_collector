from __future__ import annotations

import json
from datetime import date
from typing import Annotated

import typer

from .db import SessionLocal, init_db
from .scheduler import start_scheduler
from .sources.app_exports import AppExportsCollector
from .sources.qkb_notices import QkbNoticesCollector
from .sources.qkb_search import QkbSearchCollector
from .utils.logging import configure_logging

app = typer.Typer(add_completion=False, help="Albanian business data collector")
run_app = typer.Typer(help="Run a collector once")
app.add_typer(run_app, name="run")


@app.callback()
def main() -> None:
    configure_logging()


@app.command("init-db")
def init_db_command() -> None:
    init_db()
    typer.echo("Database initialized.")


@run_app.command("app-exports")
def run_app_exports(
    years: Annotated[list[int] | None, typer.Option(help="Specific years to fetch")] = None,
) -> None:
    with SessionLocal() as db:
        result = AppExportsCollector().collect(db, years=years or None)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))


@run_app.command("qkb-notices")
def run_qkb_notices(
    playwright: Annotated[bool, typer.Option(help="Use Playwright to render and click search")] = False,
) -> None:
    with SessionLocal() as db:
        result = QkbNoticesCollector().collect(db, use_playwright=playwright)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))


@run_app.command("qkb-search")
def run_qkb_search(
    nipt: Annotated[str | None, typer.Option("--nipt", help="Filter by NIPT")] = None,
    data_nga: Annotated[str | None, typer.Option("--data-nga", help="Registration start date YYYY-MM-DD")] = None,
    data_ne: Annotated[str | None, typer.Option("--data-ne", help="Registration end date YYYY-MM-DD")] = None,
    playwright: Annotated[bool, typer.Option(help="Use Playwright to submit the search form")] = False,
) -> None:
    parsed_data_nga = _parse_date_option(data_nga, "--data-nga")
    parsed_data_ne = _parse_date_option(data_ne, "--data-ne")

    with SessionLocal() as db:
        result = QkbSearchCollector().collect(
            db,
            nipt=nipt,
            data_nga=parsed_data_nga,
            data_ne=parsed_data_ne,
            use_playwright=playwright,
        )
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))


def _parse_date_option(value: str | None, option_name: str) -> date | None:
    if value is None:
        return None

    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(f"{option_name} must be in YYYY-MM-DD format") from exc


@app.command("scheduler")
def scheduler_command() -> None:
    start_scheduler()


if __name__ == "__main__":
    app()
