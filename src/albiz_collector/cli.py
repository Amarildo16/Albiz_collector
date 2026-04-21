from __future__ import annotations

import json
from datetime import date
from typing import Annotated

import typer

from .config import ensure_runtime_directories
from .db import SCHEMA_BOOTSTRAP_NOTE, SessionLocal, init_db
from .normalization import materialize_all, materialize_app_exports, materialize_qkb_search
from .scheduler import start_scheduler
from .sources.app_exports import AppExportsCollector
from .sources.qkb_notices import QkbNoticesCollector
from .sources.qkb_search import QkbSearchCollector
from .utils.logging import configure_logging

app = typer.Typer(add_completion=False, help="Albanian business data collector")
run_app = typer.Typer(help="Run a collector once")
normalize_app = typer.Typer(help="Materialize normalized datasets from stored snapshots")
app.add_typer(run_app, name="run")
app.add_typer(normalize_app, name="normalize")


@app.callback()
def main() -> None:
    configure_logging()
    ensure_runtime_directories()


@app.command(
    "init-db",
    help="Create any missing tables for the current models. This bootstraps a fresh local database; it does not apply migrations.",
)
def init_db_command() -> None:
    init_db()
    typer.echo("Database schema bootstrapped for current models.")
    typer.echo(SCHEMA_BOOTSTRAP_NOTE)


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


@normalize_app.command("app-exports")
def normalize_app_exports_command() -> None:
    with SessionLocal() as db:
        result = materialize_app_exports(db)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))


@normalize_app.command("qkb-search")
def normalize_qkb_search_command() -> None:
    with SessionLocal() as db:
        result = materialize_qkb_search(db)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))


@normalize_app.command("all")
def normalize_all_command() -> None:
    with SessionLocal() as db:
        result = materialize_all(db)
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
