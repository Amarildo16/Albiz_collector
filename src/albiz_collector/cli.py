from __future__ import annotations

import json
from datetime import date
from typing import Annotated, Any, Callable

import typer

from .audit import inventory_raw_fetch_integrity, list_qkb_search_runs
from .config import ensure_runtime_directories
from .db import SCHEMA_BOOTSTRAP_NOTE, SessionLocal, init_db
from .features import (
    materialize_all_features,
    materialize_app_features,
    materialize_joined_features,
    materialize_qkb_features,
)
from .normalization import materialize_all, materialize_app_exports, materialize_qkb_search
from .profiling import profile_all_data, profile_feature_data, profile_normalized_data
from .scheduler import start_scheduler
from .smoke import run_app_source_contract_smoke_check, run_qkb_search_source_contract_smoke_check
from .sources.app_exports import AppExportsCollector
from .sources.qkb_notices_experimental import ExperimentalQkbNoticesCollector
from .sources.qkb_search import QkbSearchCollector
from .utils.logging import configure_logging

app = typer.Typer(add_completion=False, help="Albanian business data collector")
run_app = typer.Typer(help="Run a collector once")
experimental_app = typer.Typer(
    help="Run explicitly experimental collectors that are not part of the supported production workflow"
)
normalize_app = typer.Typer(help="Materialize normalized datasets from stored snapshots")
features_app = typer.Typer(help="Materialize baseline analytical features from normalized datasets")
profile_app = typer.Typer(help="Profile normalized and feature datasets for analytical readiness")
audit_app = typer.Typer(help="Inspect persisted collector artifacts and integrity signals")
smoke_app = typer.Typer(help="Run opt-in live source-contract smoke checks for supported production collectors")
app.add_typer(run_app, name="run")
app.add_typer(experimental_app, name="experimental")
app.add_typer(normalize_app, name="normalize")
app.add_typer(features_app, name="features")
app.add_typer(profile_app, name="profile")
app.add_typer(audit_app, name="audit")
app.add_typer(smoke_app, name="smoke")


@app.callback()
def main() -> None:
    configure_logging()
    ensure_runtime_directories()


@app.command(
    "init-db",
    help="Create any missing tables for the current models. This bootstraps a fresh local database; it does not apply migrations. Prefer Alembic for managed schema changes.",
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


@experimental_app.command("qkb-notices")
def run_experimental_qkb_notices(
    playwright: Annotated[bool, typer.Option(help="Use Playwright to render and click search")] = False,
) -> None:
    with SessionLocal() as db:
        result = ExperimentalQkbNoticesCollector().collect(db, use_playwright=playwright)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))


@run_app.command("qkb-search")
def run_qkb_search(
    nipt: Annotated[str | None, typer.Option("--nipt", help="Filter by NIPT")] = None,
    data_nga: Annotated[str | None, typer.Option("--data-nga", help="Registration start date YYYY-MM-DD")] = None,
    data_ne: Annotated[str | None, typer.Option("--data-ne", help="Registration end date YYYY-MM-DD")] = None,
    restart: Annotated[
        bool,
        typer.Option(
            "--restart",
            help="Restart a resumable qkb-search date-range run from the beginning instead of resuming saved progress",
        ),
    ] = False,
) -> None:
    parsed_data_nga = _parse_date_option(data_nga, "--data-nga")
    parsed_data_ne = _parse_date_option(data_ne, "--data-ne")
    if restart and (nipt is not None or parsed_data_nga is None or parsed_data_ne is None):
        raise typer.BadParameter("--restart applies only to qkb-search date-range runs without --nipt")

    with SessionLocal() as db:
        result = QkbSearchCollector().collect(
            db,
            nipt=nipt,
            data_nga=parsed_data_nga,
            data_ne=parsed_data_ne,
            restart=restart,
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


@features_app.command("app")
def feature_app_command() -> None:
    with SessionLocal() as db:
        result = materialize_app_features(db)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))


@features_app.command("qkb")
def feature_qkb_command() -> None:
    with SessionLocal() as db:
        result = materialize_qkb_features(db)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))


@features_app.command("joined")
def feature_joined_command() -> None:
    with SessionLocal() as db:
        result = materialize_joined_features(db)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))


@features_app.command("all")
def feature_all_command() -> None:
    with SessionLocal() as db:
        result = materialize_all_features(db)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))


@profile_app.command("normalized")
def profile_normalized_command() -> None:
    with SessionLocal() as db:
        result = profile_normalized_data(db)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))


@profile_app.command("features")
def profile_features_command() -> None:
    with SessionLocal() as db:
        result = profile_feature_data(db)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))


@profile_app.command("all")
def profile_all_command() -> None:
    with SessionLocal() as db:
        result = profile_all_data(db)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))


@audit_app.command("raw-fetches")
def audit_raw_fetches_command(
    source_name: Annotated[str | None, typer.Option("--source-name", help="Filter by source name")] = None,
    limit: Annotated[int | None, typer.Option("--limit", min=1, help="Maximum issue rows to return")] = None,
    corrupted_only: Annotated[
        bool,
        typer.Option("--corrupted-only", help="List rows already marked corrupted, even without a newly detected issue"),
    ] = False,
    mark_corrupted: Annotated[
        bool,
        typer.Option("--mark-corrupted", help="Mark every detected issue row as corrupted and store the detected reason"),
    ] = False,
) -> None:
    with SessionLocal() as db:
        result = inventory_raw_fetch_integrity(
            db,
            source_name=source_name,
            limit=limit,
            corrupted_only=corrupted_only,
            mark_corrupted=mark_corrupted,
        )
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))


@audit_app.command("qkb-search-runs")
def audit_qkb_search_runs_command(
    status: Annotated[str | None, typer.Option("--status", help="Filter by run status")] = None,
    limit: Annotated[int | None, typer.Option("--limit", min=1, help="Maximum runs to return")] = None,
) -> None:
    with SessionLocal() as db:
        result = list_qkb_search_runs(db, status=status, limit=limit)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))


@smoke_app.command("app")
def smoke_app_exports_command() -> None:
    _run_smoke_checks([("app_exports", run_app_source_contract_smoke_check)])


@smoke_app.command("qkb-search")
def smoke_qkb_search_command() -> None:
    _run_smoke_checks([("qkb_search", run_qkb_search_source_contract_smoke_check)])


@smoke_app.command("all")
def smoke_all_command() -> None:
    _run_smoke_checks(
        [
            ("app_exports", run_app_source_contract_smoke_check),
            ("qkb_search", run_qkb_search_source_contract_smoke_check),
        ]
    )


def _parse_date_option(value: str | None, option_name: str) -> date | None:
    if value is None:
        return None

    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(f"{option_name} must be in YYYY-MM-DD format") from exc


def _run_smoke_checks(checks: list[tuple[str, Callable[[], dict[str, Any]]]]) -> None:
    results: list[dict[str, Any]] = []
    has_failures = False

    for name, runner in checks:
        try:
            result = runner()
            results.append({"check": name, "status": "ok", **result})
        except Exception as exc:
            has_failures = True
            results.append({"check": name, "status": "failed", "error": str(exc)})

    typer.echo(
        json.dumps(
            {
                "dataset": "source_contract_smoke_checks",
                "checks_run": len(checks),
                "failed_checks": sum(1 for result in results if result["status"] != "ok"),
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )

    if has_failures:
        raise typer.Exit(code=1)


@app.command("scheduler")
def scheduler_command() -> None:
    start_scheduler()


if __name__ == "__main__":
    app()
