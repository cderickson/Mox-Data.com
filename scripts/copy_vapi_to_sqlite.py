import argparse
import json
import os
import sqlite3
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


DEFAULT_TABLES = [
    "[vapi].EVENTS",
    "[vapi].MATCHES",
    "[vapi].EVENT_STANDINGS",
    "[vapi].VALID_DECKS",
    "[vapi].VALID_EVENT_TYPES",
]


def get_engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True, future=True)


def parse_simple_cfg(path: str) -> dict:
    values = {}
    if not path or not os.path.exists(path):
        return values

    with open(path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if (value.startswith("'") and value.endswith("'")) or (
                value.startswith('"') and value.endswith('"')
            ):
                value = value[1:-1]
            values[key] = value

    return values


def parse_sqlite_path_from_uri(uri: str, project_root: str = "."):
    if not uri:
        return None
    normalized = uri.strip().strip('"').strip("'")
    if normalized.startswith("sqlite:////"):
        # Absolute path form, e.g. sqlite:////var/data/app.db
        return normalized[len("sqlite:///") :]
    if normalized.startswith("sqlite:///"):
        # Flask-SQLAlchemy interprets relative sqlite paths under app.instance_path.
        # For this repo that is <project_root>/instance/.
        raw_path = normalized[len("sqlite:///") :]
        if os.path.isabs(raw_path):
            return raw_path
        return os.path.join(project_root, "instance", raw_path)
    return None


def quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def sqlite_type_for_python_value(value) -> str:
    if value is None:
        return "TEXT"
    if isinstance(value, bool):
        return "INTEGER"
    if isinstance(value, int):
        return "INTEGER"
    if isinstance(value, float):
        return "REAL"
    if isinstance(value, (bytes, bytearray, memoryview)):
        return "BLOB"
    return "TEXT"


def to_sqlite_value(value):
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, default=str)
    if isinstance(value, memoryview):
        return bytes(value)
    return value


def infer_column_types(sample_row, column_names):
    if sample_row is None:
        return {col: "TEXT" for col in column_names}
    return {
        col: sqlite_type_for_python_value(sample_row[idx])
        for idx, col in enumerate(column_names)
    }


def create_target_table(conn, table_name: str, column_names, col_types):
    quoted_table = quote_ident(table_name)
    quoted_cols_with_types = ", ".join(
        f'{quote_ident(col)} {col_types.get(col, "TEXT")}' for col in column_names
    )
    conn.execute(f"DROP TABLE IF EXISTS {quoted_table}")
    conn.execute(f"CREATE TABLE {quoted_table} ({quoted_cols_with_types})")


def copy_table(
    src_engine: Engine,
    sqlite_conn,
    source_table_name: str,
    target_table_name: str,
    batch_size: int,
) -> int:
    quoted_source_table = quote_ident(source_table_name)
    select_sql = text(f"SELECT * FROM {quoted_source_table}")

    rows_copied = 0
    with src_engine.connect() as src_conn:
        result = src_conn.execution_options(stream_results=True).execute(select_sql)
        column_names = list(result.keys())
        if not column_names:
            create_target_table(sqlite_conn, target_table_name, [], {})
            return 0

        first_row = result.fetchone()
        col_types = infer_column_types(first_row, column_names)
        create_target_table(sqlite_conn, target_table_name, column_names, col_types)

        quoted_target_table = quote_ident(target_table_name)
        insert_sql = (
            f"INSERT INTO {quoted_target_table} ("
            + ", ".join(quote_ident(col) for col in column_names)
            + ") VALUES ("
            + ", ".join("?" for _ in column_names)
            + ")"
        )

        pending_rows = []
        if first_row is not None:
            pending_rows.append(tuple(to_sqlite_value(v) for v in first_row))

        while True:
            chunk = result.fetchmany(batch_size)
            if not chunk:
                break
            for row in chunk:
                pending_rows.append(tuple(to_sqlite_value(v) for v in row))
            if len(pending_rows) >= batch_size:
                sqlite_conn.executemany(insert_sql, pending_rows)
                rows_copied += len(pending_rows)
                pending_rows = []

        if pending_rows:
            sqlite_conn.executemany(insert_sql, pending_rows)
            rows_copied += len(pending_rows)

    return rows_copied


def main():
    parser = argparse.ArgumentParser(
        description="Copy external [vapi] tables from Postgres to local SQLite."
    )
    parser.add_argument(
        "--postgres-url",
        default=None,
        help="Source Postgres SQLAlchemy URL. Defaults to PROD_DATABASE_URL or SQLALCHEMY_DATABASE_URI env var.",
    )
    parser.add_argument(
        "--sqlite-path",
        default=None,
        help=(
            "Target local SQLite DB path. "
            "Defaults to SQLALCHEMY_DATABASE_URI sqlite path from config/env, then local_database.db."
        ),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=2000,
        help="Rows to insert per batch. Default: 2000",
    )
    parser.add_argument(
        "--tables",
        nargs="+",
        default=DEFAULT_TABLES,
        help="Source table names to copy. Defaults to all [vapi] tables used by vintage dashboard.",
    )
    parser.add_argument(
        "--config-path",
        default=os.path.join("local-dev", "local_config.cfg"),
        help="Path to a cfg file for fallback values (default: local-dev/local_config.cfg).",
    )

    args = parser.parse_args()

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    cfg = parse_simple_cfg(args.config_path)
    postgres_url = (
        args.postgres_url
        or os.environ.get("PROD_DATABASE_URL")
        or os.environ.get("SQLALCHEMY_DATABASE_URI")
        or cfg.get("PROD_DATABASE_URL")
    )
    sqlite_path = (
        args.sqlite_path
        or os.environ.get("LOCAL_SQLITE_PATH")
        or parse_sqlite_path_from_uri(os.environ.get("SQLALCHEMY_DATABASE_URI", ""), project_root)
        or parse_sqlite_path_from_uri(cfg.get("SQLALCHEMY_DATABASE_URI", ""), project_root)
        or os.path.join(project_root, "instance", "local_database.db")
    )

    if not postgres_url:
        raise SystemExit(
            "No source Postgres URL provided. Set --postgres-url, env PROD_DATABASE_URL/SQLALCHEMY_DATABASE_URI, or PROD_DATABASE_URL in local config."
        )

    sqlite_dir = os.path.dirname(os.path.abspath(sqlite_path))
    if sqlite_dir and not os.path.exists(sqlite_dir):
        os.makedirs(sqlite_dir, exist_ok=True)

    src_engine = get_engine(postgres_url)
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.execute("PRAGMA journal_mode = WAL;")
    sqlite_conn.execute("PRAGMA synchronous = NORMAL;")

    total_rows = 0
    try:
        for table_name in args.tables:
            copied = copy_table(
                src_engine=src_engine,
                sqlite_conn=sqlite_conn,
                source_table_name=table_name,
                target_table_name=table_name,
                batch_size=args.batch_size,
            )
            sqlite_conn.commit()
            print(f"Copied {copied:8d} rows -> {table_name}")
            total_rows += copied
    finally:
        sqlite_conn.close()
        src_engine.dispose()

    print(f"Done. Total rows copied: {total_rows}")


if __name__ == "__main__":
    main()