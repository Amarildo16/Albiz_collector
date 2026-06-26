from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from albiz_collector.db import engine  # noqa: E402


def clean_nipt(value: Any) -> str | None:
    if value is None:
        return None

    nipt = str(value).strip().upper()
    nipt = re.sub(r"[^A-Z0-9]", "", nipt)

    if len(nipt) < 8 or len(nipt) > 16:
        return None

    return nipt


def fetch_category(conn, category: str, sql: str, limit: int, used: set[str]) -> list[dict[str, Any]]:
    rows = conn.execute(text(sql), {"limit": limit * 5}).mappings().all()

    selected: list[dict[str, Any]] = []

    for row in rows:
        nipt = clean_nipt(row.get("company_nipt"))
        if not nipt or nipt in used:
            continue

        used.add(nipt)
        selected.append(
            {
                "category": category,
                "nipt": nipt,
                "business_name": row.get("business_name"),
                "legal_form": row.get("legal_form"),
                "subject_status": row.get("subject_status"),
                "registration_date": row.get("registration_date"),
                "active_procurement_count": row.get("active_procurement_count"),
            }
        )

        if len(selected) >= limit:
            break

    return selected


def load_remaining_missing_nipts(path: Path, limit: int, used: set[str]) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    selected: list[dict[str, Any]] = []

    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        nipt = clean_nipt(line)
        if not nipt or nipt in used:
            continue

        used.add(nipt)
        selected.append(
            {
                "category": "remaining_missing_after_qkb_lookup",
                "nipt": nipt,
                "business_name": None,
                "legal_form": None,
                "subject_status": None,
                "registration_date": None,
                "active_procurement_count": None,
            }
        )

        if len(selected) >= limit:
            break

    return selected


def write_outputs(rows: list[dict[str, Any]], doc_type: str, save: bool) -> None:
    reports_dir = PROJECT_ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)

    nipts_path = reports_dir / "qkb_document_probe_nipts.txt"
    commands_path = reports_dir / "qkb_document_probe_commands.ps1"
    table_path = reports_dir / "qkb_document_probe_selection.tsv"

    save_flag = "--save" if save else "--no-save"

    nipts_path.write_text(
        "\n".join(row["nipt"] for row in rows) + "\n",
        encoding="utf-8",
    )

    command_lines: list[str] = [
        "# Generated QKB document probe commands",
        "# Review the selected NIPTs before running.",
        "",
    ]

    current_category = None
    for row in rows:
        if row["category"] != current_category:
            current_category = row["category"]
            command_lines.append("")
            command_lines.append(f"# {current_category}")

        command_lines.append(
            ".\\.venv\\Scripts\\python.exe -m albiz_collector.cli "
            f"experimental qkb-document-fetch-one --nipt {row['nipt']} "
            f"--doc-type {doc_type} {save_flag}"
        )

    commands_path.write_text("\n".join(command_lines) + "\n", encoding="utf-8")

    header = [
        "category",
        "nipt",
        "business_name",
        "legal_form",
        "subject_status",
        "registration_date",
        "active_procurement_count",
    ]

    lines = ["\t".join(header)]
    for row in rows:
        lines.append("\t".join(str(row.get(col) or "") for col in header))

    table_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Wrote: {nipts_path}")
    print(f"Wrote: {commands_path}")
    print(f"Wrote: {table_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Select a small, safe NIPT probe set for QKB historical document testing."
    )
    parser.add_argument("--per-category", type=int, default=2)
    parser.add_argument("--doc-type", default="historical", choices=["historical", "simple", "rpp"])
    parser.add_argument("--save", action="store_true", help="Generate commands with --save instead of --no-save.")
    parser.add_argument(
        "--remaining-file",
        default="reports/app_missing_from_qkb_all_remaining_nipts.txt",
        help="Optional file containing remaining unmatched NIPTs.",
    )

    args = parser.parse_args()

    used: set[str] = set()
    selected: list[dict[str, Any]] = []

    queries = [
        (
            "joined_high_procurement_activity",
            """
            SELECT
                company_nipt,
                business_name,
                legal_form,
                subject_status,
                registration_date,
                active_procurement_count
            FROM joined_company_features
            WHERE company_nipt IS NOT NULL
            ORDER BY active_procurement_count DESC, company_nipt ASC
            LIMIT :limit
            """,
        ),
        (
            "joined_old_registered_company",
            """
            SELECT
                company_nipt,
                business_name,
                legal_form,
                subject_status,
                registration_date,
                active_procurement_count
            FROM joined_company_features
            WHERE company_nipt IS NOT NULL
              AND registration_date < '2015-01-01'
            ORDER BY registration_date ASC, active_procurement_count DESC, company_nipt ASC
            LIMIT :limit
            """,
        ),
        (
            "joined_recent_registered_company",
            """
            SELECT
                company_nipt,
                business_name,
                legal_form,
                subject_status,
                registration_date,
                active_procurement_count
            FROM joined_company_features
            WHERE company_nipt IS NOT NULL
              AND registration_date >= '2022-01-01'
            ORDER BY registration_date DESC, active_procurement_count DESC, company_nipt ASC
            LIMIT :limit
            """,
        ),
        (
            "qkb_only_shpk_not_in_app_join",
            """
            SELECT
                q.company_nipt,
                q.business_name,
                q.legal_form,
                q.subject_status,
                q.registration_date,
                NULL AS active_procurement_count
            FROM qkb_company_features q
            LEFT JOIN joined_company_features j
              ON j.company_nipt = q.company_nipt
            WHERE j.company_nipt IS NULL
              AND UPPER(COALESCE(q.legal_form, '')) = 'SHPK'
            ORDER BY q.registration_date DESC, q.company_nipt ASC
            LIMIT :limit
            """,
        ),
        (
            "qkb_person_fizik_sample",
            """
            SELECT
                q.company_nipt,
                q.business_name,
                q.legal_form,
                q.subject_status,
                q.registration_date,
                NULL AS active_procurement_count
            FROM qkb_company_features q
            WHERE q.company_nipt IS NOT NULL
              AND UPPER(COALESCE(q.legal_form, '')) LIKE '%PERSON%FIZIK%'
            ORDER BY q.registration_date DESC, q.company_nipt ASC
            LIMIT :limit
            """,
        ),
    ]

    with engine.connect() as conn:
        for category, sql in queries:
            selected.extend(fetch_category(conn, category, sql, args.per_category, used))

    remaining_file = PROJECT_ROOT / args.remaining_file
    selected.extend(load_remaining_missing_nipts(remaining_file, args.per_category, used))

    if not selected:
        raise SystemExit("No NIPTs selected. Check DB connection and feature tables.")

    print("\nSelected probe NIPTs:\n")
    for row in selected:
        print(
            f"{row['category']:38} "
            f"{row['nipt']:16} "
            f"{str(row.get('legal_form') or ''):14} "
            f"{str(row.get('registration_date') or ''):12} "
            f"{str(row.get('business_name') or '')[:80]}"
        )

    print()
    write_outputs(selected, doc_type=args.doc_type, save=args.save)


if __name__ == "__main__":
    main()