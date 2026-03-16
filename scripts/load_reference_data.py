#!/usr/bin/env python3
"""
Load auxiliary reference files into database tables.

Supports both local SQLite and remote Postgres/RDS by passing --database-url.
"""

from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path
from typing import Iterable

from flask import Flask

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.extensions import db
from modules.models import AllDeck, InputOption, MultifacedCard

ALLOWED_MULT_TYPES = {"SPLIT", "TRANSFORM", "DFC", "MDFC", "ADVENTURE"}

def build_db_app(database_url: str) -> Flask:
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    return app

def dedupe_keep_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output

def parse_multifaced_cards(path: Path) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    current_type: str | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue

        upper = line.upper()
        if upper in ALLOWED_MULT_TYPES:
            current_type = upper
            continue

        if current_type and " // " in line:
            front_nm, back_nm = (token.strip() for token in line.split(" // ", 1))
            rows.append((front_nm, back_nm, current_type))

    # Remove duplicates while preserving order
    unique_rows = list(dict.fromkeys(rows))
    return unique_rows

def parse_input_options(path: Path) -> list[tuple[str, str, list[str]]]:
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    rows: list[tuple[str, str, list[str]]] = []

    idx = 0
    total = len(lines)
    while idx < total:
        # Skip blank and separator lines until we find table_nm.
        while idx < total and (not lines[idx] or lines[idx].startswith("-")):
            idx += 1
        if idx >= total:
            break
        table_nm = lines[idx]
        idx += 1

        # Skip blank separators before var_nm (defensive).
        while idx < total and (not lines[idx] or lines[idx].startswith("-")):
            idx += 1
        if idx >= total:
            break
        var_nm = lines[idx]
        idx += 1

        # Skip until options section begins (after dashed delimiter).
        while idx < total and (not lines[idx] or lines[idx].startswith("-")):
            idx += 1

        options: list[str] = []
        while idx < total and not lines[idx].startswith("-"):
            if lines[idx]:
                options.append(lines[idx])
            idx += 1

        rows.append((table_nm, var_nm, dedupe_keep_order(options)))

    return rows

def parse_all_decks(path: Path) -> list[tuple[str, str, str, list[str]]]:
    data = pickle.loads(path.read_bytes())
    if not isinstance(data, dict):
        raise ValueError("ALL_DECKS does not contain the expected dictionary payload.")

    rows: list[tuple[str, str, str, list[str]]] = []
    for yyyy_mm, deck_rows in data.items():
        if not isinstance(deck_rows, list):
            continue
        for row in deck_rows:
            if not isinstance(row, (list, tuple)) or len(row) < 3:
                continue

            deck_nm = str(row[0])
            format_nm = str(row[1])
            deck_cards = row[2]

            if isinstance(deck_cards, set):
                deck_lst = sorted(str(card) for card in deck_cards)
            elif isinstance(deck_cards, (list, tuple)):
                deck_lst = [str(card) for card in deck_cards]
            else:
                deck_lst = [str(deck_cards)]

            rows.append((str(yyyy_mm), deck_nm, format_nm, deck_lst))

    return rows

def validate_lengths(
    multifaced_rows: list[tuple[str, str, str]],
    input_rows: list[tuple[str, str, list[str]]],
    all_decks_rows: list[tuple[str, str, str, list[str]]],
) -> None:
    too_long_decks = [row for row in all_decks_rows if len(row[1]) > 60]
    if too_long_decks:
        sample = too_long_decks[0]
        raise ValueError(
            "ALL_DECKS contains deck_nm values longer than 60 characters. "
            f"Example: '{sample[1]}' (length={len(sample[1])}). "
            "Increase all_decks.deck_nm column size or clean the source file."
        )

    too_long_mult_front = [row for row in multifaced_rows if len(row[0]) > 50]
    too_long_mult_back = [row for row in multifaced_rows if len(row[1]) > 50]
    if too_long_mult_front or too_long_mult_back:
        raise ValueError("MULTIFACED_CARDS has values longer than 50 chars.")

    too_long_input = [row for row in input_rows if len(row[0]) > 20 or len(row[1]) > 40]
    if too_long_input:
        raise ValueError("INPUT_OPTIONS has table_nm/var_nm values longer than configured limits.")

def upsert_multifaced_cards(rows: list[tuple[str, str, str]]) -> int:
    for front_nm, back_nm, mult_type in rows:
        db.session.merge(
            MultifacedCard(
                front_nm=front_nm,
                back_nm=back_nm,
                mult_type=mult_type,
            )
        )
    db.session.commit()
    return len(rows)

def upsert_input_options(rows: list[tuple[str, str, list[str]]]) -> int:
    for table_nm, var_nm, options_lst in rows:
        db.session.merge(
            InputOption(
                table_nm=table_nm,
                var_nm=var_nm,
                options_lst=options_lst,
            )
        )
    db.session.commit()
    return len(rows)

def upsert_all_decks(rows: list[tuple[str, str, str, list[str]]]) -> int:
    for yyyy_mm, deck_nm, format_nm, deck_lst in rows:
        db.session.merge(
            AllDeck(
                yyyy_mm=yyyy_mm,
                deck_nm=deck_nm,
                format_nm=format_nm,
                deck_lst=deck_lst,
            )
        )
    db.session.commit()
    return len(rows)

def main() -> None:
    default_sqlite_url = f"sqlite:///{(PROJECT_ROOT / 'instance' / 'local_database.db').as_posix()}"

    parser = argparse.ArgumentParser(description="Load reference data into DB tables.")
    parser.add_argument(
        "--database-url",
        default=default_sqlite_url,
        help=(
            "SQLAlchemy database URL. "
            "Example for RDS: postgresql+psycopg2://user:pass@host:5432/dbname"
        ),
    )
    parser.add_argument(
        "--aux-dir",
        default="auxiliary",
        help="Directory that contains MULTIFACED_CARDS.txt, INPUT_OPTIONS.txt, and ALL_DECKS.",
    )
    args = parser.parse_args()

    aux_dir = Path(args.aux_dir)
    multifaced_path = aux_dir / "MULTIFACED_CARDS.txt"
    input_options_new_path = aux_dir / "INPUT_OPTIONS_new.txt"
    input_options_path = input_options_new_path if input_options_new_path.exists() else aux_dir / "INPUT_OPTIONS.txt"
    all_decks_path = aux_dir / "ALL_DECKS"

    for required_path in (multifaced_path, input_options_path, all_decks_path):
        if not required_path.exists():
            raise SystemExit(f"Missing required input file: {required_path}")

    multifaced_rows = parse_multifaced_cards(multifaced_path)
    input_rows = parse_input_options(input_options_path)
    all_decks_rows = parse_all_decks(all_decks_path)
    validate_lengths(multifaced_rows, input_rows, all_decks_rows)

    app = build_db_app(args.database_url)
    with app.app_context():
        multifaced_count = upsert_multifaced_cards(multifaced_rows)
        input_options_count = upsert_input_options(input_rows)
        all_decks_count = upsert_all_decks(all_decks_rows)

    print(f"Upserted {multifaced_count} rows into multifaced_cards")
    print(f"Upserted {input_options_count} rows into input_options")
    print(f"Upserted {all_decks_count} rows into all_decks")

if __name__ == "__main__":
    main()